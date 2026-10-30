"""Read-only GET checks for the RULE-SET URLs in a Shadowrocket config."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import ipaddress
import json
import math
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 2 * 1024 * 1024
MAX_URLS = 256


def validate_url(url):
    # Scope this maintenance tool to public GitHub raw lists, not arbitrary hosts.
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com"
            or parsed.query or parsed.fragment or not parsed.path.endswith(".list")
            or any(c.isspace() or ord(c) < 32 for c in url)):
        raise ValueError("expected an HTTPS raw.githubusercontent.com .list URL without credentials/query/fragment")


def extract_urls(text):
    section = None
    urls = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = re.split(r"\s+#", raw.strip(), maxsplit=1)[0]
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "Rule" or not line.startswith("RULE-SET"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3 or parts[0] != "RULE-SET" or not all(parts):
            raise ValueError(f"line {number}: malformed RULE-SET")
        validate_url(parts[1])
        if parts[1] not in urls:
            urls.append(parts[1])
        if len(urls) > MAX_URLS:
            raise ValueError(f"at most {MAX_URLS} distinct URLs are allowed")
    if not urls:
        raise ValueError("no RULE-SET URLs in [Rule]; supply a native .conf, not rules.yaml")
    return urls


def inspect_content(data, content_type):
    if "html" in content_type.lower():
        return "invalid_content", 0, "HTML response, not a rule list"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        return "invalid_content", 0, "response is not UTF-8"
    count = 0
    unknown = False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "<html" in line.lower() or "<!doctype" in line.lower():
            return "invalid_content", count, "HTML response, not a rule list"
        parts = [part.strip() for part in line.split(",")]
        kind = parts[0]
        if len(parts) < 2 or not all(parts) or any(ord(c) < 32 for c in line):
            return "invalid_content", count, f"line {number}: malformed rule"
        known = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "USER-AGENT",
                 "IP-CIDR", "IP-CIDR6", "IP6-CIDR", "IP-ASN"}
        if kind not in known:
            unknown = True
            count += 1
            continue
        ip_rule = kind.startswith("IP")
        if not (len(parts) == 2 or (ip_rule and len(parts) == 3 and parts[2] == "no-resolve")):
            return "invalid_content", count, f"line {number}: unexpected fields"
        value = parts[1]
        try:
            if kind in {"DOMAIN", "DOMAIN-SUFFIX"}:
                labels = value.rstrip(".").split(".")
                if len(value) > 253 or any(not re.fullmatch(r"[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?", label) for label in labels):
                    raise ValueError("invalid domain")
            elif kind in {"IP-CIDR", "IP-CIDR6", "IP6-CIDR"}:
                network = ipaddress.ip_network(value, strict=False)
                # The current Shadowrocket upstream uses IP-CIDR for both families.
                if "/" not in value or (kind != "IP-CIDR" and network.version != 6):
                    raise ValueError("invalid network family")
            elif kind == "IP-ASN":
                if not value.isascii() or not value.isdigit() or not 0 < int(value) <= 4294967295:
                    raise ValueError("invalid ASN")
        except ValueError:
            return "invalid_content", count, f"line {number}: invalid {kind} value"
        count += 1
    if not count:
        return "invalid_content", 0, "empty or comments-only list"
    if unknown:
        return "content_unverified", count, "contains rule types outside this checker; manual review required"
    return "ok", count, "basic rule structure passed; not a client or routing test"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_category(code):
    if code in (404, 410):
        return "not_found"
    if code in (401, 403):
        return "access_denied"
    if code == 429:
        return "rate_limited"
    if 300 <= code < 400:
        return "redirect"
    return "http_error"


def check_url(url, timeout):
    validate_url(url)
    result = {"url": url, "status": None, "http_status": None, "rule_count": 0,
              "bytes": 0, "sha256": None, "detail": ""}
    try:
        request = Request(url, headers={"User-Agent": "client-rules-upstream-check/1"}, method="GET")
        # Default certificate validation and system proxy handling remain enabled.
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            result["http_status"] = response.status
            if response.status != 200:
                result.update(status=http_category(response.status), detail=f"HTTP {response.status}; observed response only")
                return result
            data = response.read(MAX_BYTES + 1)
            result["bytes"] = len(data)
            if len(data) > MAX_BYTES:
                result.update(status="too_large", detail=f"response exceeds {MAX_BYTES} bytes; not fully checked")
                return result
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isdigit() or int(length) != len(data)):
                result.update(status="network_error", detail="incomplete or inconsistent Content-Length")
                return result
            result["sha256"] = hashlib.sha256(data).hexdigest()
            status, count, detail = inspect_content(data, response.headers.get("Content-Type", ""))
            result.update(status=status, rule_count=count, detail=detail)
    except HTTPError as error:
        result.update(status=http_category(error.code), http_status=error.code,
                      detail=f"HTTP {error.code}; observed response only, not proof a service is unavailable")
        error.close()
    except (URLError, OSError, HTTPException) as error:
        reason = error.reason if isinstance(error, URLError) else error
        status = "timeout" if isinstance(reason, TimeoutError) else "tls_error" if isinstance(reason, ssl.SSLError) else "network_error"
        # Do not echo proxy credentials, server bodies or arbitrary exception text.
        result.update(status=status, detail=f"{type(reason).__name__}; reachability unresolved, not a dead-link verdict")
    return result


def bounded_timeout(value):
    number = float(value)
    if not math.isfinite(number) or not 0.1 <= number <= 60:
        raise argparse.ArgumentTypeError("timeout must be finite and between 0.1 and 60 seconds")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "shadowrocket.conf")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--timeout", type=bounded_timeout, default=15.0,
                        help="socket blocking-operation timeout; not a whole-run deadline (default: 15)")
    parser.add_argument("--json", action="store_true", help="emit one JSON report instead of text")
    args = parser.parse_args(argv)
    try:
        urls = extract_urls(args.config.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda url: check_url(url, args.timeout), urls))
    except KeyboardInterrupt:
        print("Check interrupted; no complete report.", file=sys.stderr)
        return 130
    passed = sum(result["status"] == "ok" for result in results)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "total": len(results),
              "passed": passed, "needs_attention": len(results) - passed, "results": results}
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        for result in results:
            print(f"{result['status']} HTTP={result['http_status']} rules={result['rule_count']} {result['url']} | {result['detail']}")
        print(f"Checked {len(results)}: {passed} passed basic checks, {len(results) - passed} need attention.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
