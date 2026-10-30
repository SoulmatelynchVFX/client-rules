"""Offline checks at CLI/file/HTTP boundaries; never fetch real upstreams."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import ssl
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts import check_upstream as checker

URL = "https://raw.githubusercontent.com/example/rules/main/App.list"
BODY = b"# sample\nDOMAIN-SUFFIX,example.com\nIP-CIDR,10.0.0.0/8,no-resolve\n"


def response(body=BODY, status=200, headers=None):
    stream = io.BytesIO(body)
    stream.status = status
    stream.headers = headers or {"Content-Type": "text/plain", "Content-Length": str(len(body))}
    return stream


class UpstreamTests(unittest.TestCase):
    def test_native_section_dedup_and_comment_handling(self):
        text = f"[General]\nRULE-SET,{URL},DIRECT\n[Rule]\n# ignored\nRULE-SET,{URL},DIRECT # note\nRULE-SET,{URL},PROXY\n[Other]\nRULE-SET,https://bad.invalid/a.list,DIRECT"
        self.assertEqual(checker.extract_urls(text), [URL])

    def test_invalid_config_and_unsafe_urls_rejected(self):
        for text in ("", "rules:\n  - RULE-SET," + URL + ",DIRECT", "[Rule]\nRULE-SET,broken", "[Rule]\nRULE-SET," + URL + ","):
            with self.subTest(text=text), self.assertRaises(ValueError):
                checker.extract_urls(text)
        for url in ("http://raw.githubusercontent.com/a.list", "https://localhost/a.list",
                    "https://user:secret@raw.githubusercontent.com/a.list", URL + "?token=secret",
                    URL + "#fragment", URL + "\n", "https://raw.githubusercontent.com/a.txt"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                checker.validate_url(url)

    def test_url_limit(self):
        text = "[Rule]\n" + "\n".join(f"RULE-SET,{URL[:-5]}{i}.list,DIRECT" for i in range(257))
        with self.assertRaises(ValueError):
            checker.extract_urls(text)

    def test_supported_content_and_bom(self):
        data = ("\ufeff# list\r\nDOMAIN,example.com\nDOMAIN-SUFFIX,example.org\n"
                "DOMAIN-KEYWORD,example\nUSER-AGENT,Example*\nIP-ASN,123,no-resolve\n"
                "IP-CIDR,10.0.0.0/8\nIP-CIDR6,2001:db8::/32,no-resolve\nIP6-CIDR,::1/128\n").encode("utf-8")
        status, count, _ = checker.inspect_content(data, "text/plain")
        self.assertEqual((status, count), ("ok", 8))

    def test_empty_html_encoding_and_malformed_content(self):
        for body in (b"", b"# only comments\n", b"<html>Error</html>", b"\xff", b"access denied",
                     b"DOMAIN-SUFFIX,", b"DOMAIN,invalid domain", b"DOMAIN,a.com,PROXY",
                     b"IP-CIDR,999.1.1.1/8", b"IP-CIDR6,10.0.0.0/8", b"IP-ASN,abc", b"IP-ASN,0"):
            with self.subTest(body=body):
                self.assertEqual(checker.inspect_content(body, "text/plain")[0], "invalid_content")
        self.assertEqual(checker.inspect_content(BODY, "text/html; charset=utf-8")[0], "invalid_content")

    def test_unknown_types_need_review_not_false_success_or_invalid(self):
        self.assertEqual(checker.inspect_content(BODY + b"NEW-TYPE,value\n", "text/plain")[0], "content_unverified")

    def test_observed_shadowrocket_ip_cidr_ipv6_samples(self):
        # Actual 2026-10-30 Alibaba, Google/YouTube and Telegram upstream entries.
        for network in ("2400:b200::/32", "2620:120:e000::/40", "2001:67c:4e8::/48"):
            with self.subTest(network=network):
                data = f"IP-CIDR,{network},no-resolve\n".encode("ascii")
                self.assertEqual(checker.inspect_content(data, "text/plain")[:2], ("ok", 1))

    def test_get_timeout_digest_and_closed_response(self):
        stream = response()
        with patch("urllib.request.OpenerDirector.open", return_value=stream) as opened:
            result = checker.check_url(URL, 3)
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(opened.call_args.kwargs["timeout"], 3)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["rule_count"], 2)
        self.assertEqual(result["sha256"], hashlib.sha256(BODY).hexdigest())
        self.assertTrue(stream.closed)

    def test_http_errors_are_distinguished_and_closed(self):
        for code, status in ((404, "not_found"), (410, "not_found"), (401, "access_denied"),
                             (403, "access_denied"), (429, "rate_limited"), (503, "http_error"), (302, "redirect")):
            body = io.BytesIO(b"private server body")
            error = HTTPError(URL, code, "error", {}, body)
            with self.subTest(code=code), patch("urllib.request.OpenerDirector.open", side_effect=error):
                result = checker.check_url(URL, 2)
                self.assertEqual((result["status"], result["http_status"]), (status, code))
                self.assertTrue(body.closed)
                self.assertNotIn("private", result["detail"])

    def test_network_tls_and_read_failures_not_dead_links(self):
        for error, status in ((URLError(TimeoutError()), "timeout"), (TimeoutError(), "timeout"),
                              (URLError(ssl.SSLCertVerificationError()), "tls_error"),
                              (ssl.SSLError(), "tls_error"), (URLError("secret proxy"), "network_error"),
                              (IncompleteRead(b"partial", 100), "network_error")):
            with self.subTest(error=type(error)), patch("urllib.request.OpenerDirector.open", side_effect=error):
                result = checker.check_url(URL, 2)
                self.assertEqual(result["status"], status)
                self.assertNotIn("secret", result["detail"])
        stream = response()
        with patch("urllib.request.OpenerDirector.open", return_value=stream), patch.object(stream, "read", side_effect=TimeoutError()):
            self.assertEqual(checker.check_url(URL, 2)["status"], "timeout")
        self.assertTrue(stream.closed)

    def test_oversize_truncated_and_non_200_responses(self):
        for stream, status in ((response(b"x" * (checker.MAX_BYTES + 1)), "too_large"),
                               (response(headers={"Content-Length": "999"}), "network_error"),
                               (response(status=204), "http_error"),
                               (response(b"<html>error</html>"), "invalid_content")):
            with self.subTest(status=status), patch("urllib.request.OpenerDirector.open", return_value=stream):
                self.assertEqual(checker.check_url(URL, 2)["status"], status)

    def test_redirects_not_followed(self):
        self.assertIsNone(checker.NoRedirect().redirect_request(None, None, 302, "", {}, "http://localhost/secret"))

    def run_cli(self, text, *args):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.conf"
            path.write_text(text, encoding="utf-8")
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                status = checker.main(["--config", str(path), *args])
            self.assertEqual(path.read_text(encoding="utf-8"), text)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            return status, output.getvalue(), errors.getvalue()

    def test_cli_json_dedup_and_success_exit(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=lambda *a, **k: response()) as opened:
            status, output, errors = self.run_cli(f"[Rule]\nRULE-SET,{URL},DIRECT\nRULE-SET,{URL},PROXY", "--json")
        report = json.loads(output)
        self.assertEqual((status, report["total"], report["passed"], report["needs_attention"]), (0, 1, 1, 0))
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(errors, "")
        self.assertIn("checked_at", report)

    def test_cli_failure_and_config_exit_codes(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=lambda *a, **k: response(b"# empty")):
            status, output, _ = self.run_cli(f"[Rule]\nRULE-SET,{URL},DIRECT")
        self.assertEqual(status, 1)
        self.assertIn("invalid_content", output)
        with patch("urllib.request.OpenerDirector.open") as opened:
            status, output, errors = self.run_cli("[Rule]\nFINAL,PROXY")
        self.assertEqual((status, output), (2, ""))
        self.assertIn("Configuration error", errors)
        opened.assert_not_called()

    def test_cli_rejects_invalid_resource_limits_before_network(self):
        for args in (("--workers", "0"), ("--workers", "9"), ("--timeout", "nan"),
                     ("--timeout", "inf"), ("--timeout", "0"), ("--timeout", "61")):
            with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                checker.main(list(args))
            self.assertEqual(caught.exception.code, 2)

    def test_bounded_parallelism_and_stable_output_order(self):
        barrier = threading.Barrier(2, timeout=3)
        lock = threading.Lock()
        active = peak = 0
        def open_response(*args, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait()
            with lock:
                active -= 1
            return response()
        urls = [URL.replace("App.list", f"App{i}.list") for i in range(4)]
        text = "[Rule]\n" + "\n".join(f"RULE-SET,{url},DIRECT" for url in urls)
        with patch("urllib.request.OpenerDirector.open", side_effect=open_response):
            status, output, _ = self.run_cli(text, "--workers", "2", "--json")
        self.assertEqual(status, 0)
        self.assertEqual(peak, 2)
        self.assertEqual([r["url"] for r in json.loads(output)["results"]], urls)


if __name__ == "__main__":
    unittest.main()
