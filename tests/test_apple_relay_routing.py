"""Local policy contracts, not an iOS eligibility or full routing-engine test."""
from pathlib import Path
import re
import unittest

from scripts.validate_rules import validate


ROOT = Path(__file__).resolve().parents[1]
HOSTS = ("apple-relay.apple.com", "apple-relay.fastly-edge.com")


def read_rules(name):
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    if name.endswith(".yaml"):
        rules = [re.split(r"\s+#", line.strip()[2:])[0]
                 for line in lines if line.strip().startswith("- ")]
        return [rule.replace("🔰 选择节点", "PROXY").replace("MATCH,", "FINAL,")
                for rule in rules]
    return [line.strip() for line in lines
            if line.startswith(("DOMAIN,", "DOMAIN-", "RULE-SET,", "GEOIP,", "FINAL,"))]


def replay_local(host, rules, *, cn_ip):
    """Only local DOMAIN/SUFFIX and assumed GEOIP; skip remote rule sets."""
    for rule in rules:
        kind, *parts = rule.split(",")
        if kind == "DOMAIN" and host == parts[0]:
            return parts[-1]
        if kind == "DOMAIN-SUFFIX" and (host == parts[0] or host.endswith("." + parts[0])):
            return parts[-1]
        if kind == "GEOIP" and parts[0] == "CN" and cn_ip:
            return parts[-1]
        if kind == "FINAL":
            return parts[-1]
    raise AssertionError("Missing fallback")


class AppleRelayRoutingTest(unittest.TestCase):
    def test_exact_exceptions_are_first_in_both_configs(self):
        expected = [f"DOMAIN,{host},PROXY" for host in HOSTS]
        for name in ("shadowrocket.conf", "rules.yaml"):
            with self.subTest(name=name):
                rules = read_rules(name)
                self.assertEqual(rules[:2], expected)
                for rule in expected:
                    self.assertEqual(rules.count(rule), 1)

    def test_explicit_policy_precedes_assumed_cn_geoip(self):
        for name in ("shadowrocket.conf", "rules.yaml"):
            for host in HOSTS:
                for cn_ip in (False, True):
                    with self.subTest(name=name, host=host, cn_ip=cn_ip):
                        self.assertEqual(replay_local(host, read_rules(name), cn_ip=cn_ip), "PROXY")

    def test_removing_exceptions_exposes_conditional_geoip_fallback(self):
        rules = [rule for rule in read_rules("shadowrocket.conf")
                 if rule not in [f"DOMAIN,{host},PROXY" for host in HOSTS]]
        for host in HOSTS:
            self.assertEqual(replay_local(host, rules, cn_ip=True), "DIRECT")
            self.assertEqual(replay_local(host, rules, cn_ip=False), "PROXY")

    def test_no_expansion_to_other_apple_hosts_or_lookalikes(self):
        for name in ("shadowrocket.conf", "rules.yaml"):
            rules = read_rules(name)
            for host in ("apple.com", "icloud.com", "fastly-edge.com", "mesu.apple.com",
                         "apple-relay.cloudflare.com", "cp4.cloudflare.com",
                         "sub.apple-relay.apple.com", "notapple-relay.apple.com",
                         "apple-relay.apple.com.example.org",
                         "apple-relay.fastly-edge.com.example.org"):
                with self.subTest(name=name, host=host):
                    self.assertEqual(replay_local(host, rules, cn_ip=True), "DIRECT")

    def test_exact_domain_supported_by_offline_validator(self):
        self.assertEqual(validate("rules:\n  - DOMAIN,apple-relay.apple.com,PROXY\n"
                                  "  - MATCH,PROXY\n"), [])

    def test_exact_domain_malformed_and_duplicate_entries_rejected(self):
        for rule in ("DOMAIN,,PROXY", "DOMAIN,apple-relay.apple.com", "DOMAIN,a,PROXY,extra"):
            self.assertTrue(validate(f"rules:\n  - {rule}\n  - MATCH,PROXY\n"))
        self.assertTrue(validate("rules:\n  - DOMAIN,apple-relay.apple.com,PROXY\n"
                                 "  - DOMAIN,apple-relay.apple.com,DIRECT\n  - MATCH,PROXY\n"))


if __name__ == "__main__":
    unittest.main()
