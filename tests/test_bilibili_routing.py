"""Replay a minimal observed upstream subset, not the Shadowrocket engine.

GET verified 2026-10-27: BiliBili contains bilibili.tv and bilibili.com;
BiliBiliIntl contains only DOMAIN-SUFFIX,bilibili.tv. No network in tests.
"""
import unittest

from test_service_exceptions import ROOT, matches, rules_from

BASE = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket"
DOMESTIC = f"{BASE}/BiliBili/BiliBili.list"
INTERNATIONAL = f"{BASE}/BiliBiliIntl/BiliBiliIntl.list"
OBSERVED = {DOMESTIC: ("bilibili.tv", "bilibili.com"), INTERNATIONAL: ("bilibili.tv",)}
CONFIGS = (("shadowrocket.conf", "PROXY"), ("rules.yaml", "🔰 选择节点"))


def route(host, rules):
    for rule in rules:
        parts = rule.split(",")
        if parts[0] == "DOMAIN-SUFFIX" and matches(host, parts[1]):
            return parts[-1]
        if parts[0] == "RULE-SET" and any(matches(host, suffix) for suffix in OBSERVED.get(parts[1], ())):
            return parts[-1]
        if parts[0] in ("FINAL", "MATCH"):
            return parts[-1]
    return None


class BiliBiliRoutingTests(unittest.TestCase):
    def test_international_set_precedes_every_domestic_set(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            exception = f"RULE-SET,{INTERNATIONAL},{policy}"
            with self.subTest(file=filename):
                self.assertEqual(rules.count(exception), 1)
                first_direct = next(i for i, rule in enumerate(rules) if rule.startswith("RULE-SET,") and rule.endswith(",DIRECT"))
                self.assertLess(rules.index(exception), first_direct)

    def test_international_apex_and_subdomains_proxy(self):
        for filename, policy in CONFIGS:
            for host in ("bilibili.tv", "www.bilibili.tv", "api.bilibili.tv"):
                with self.subTest(file=filename, host=host):
                    self.assertEqual(route(host, rules_from(ROOT / filename)), policy)

    def test_domestic_apex_and_subdomains_stay_direct(self):
        for filename, _ in CONFIGS:
            for host in ("bilibili.com", "www.bilibili.com", "api.bilibili.com"):
                with self.subTest(file=filename, host=host):
                    self.assertEqual(route(host, rules_from(ROOT / filename)), "DIRECT")

    def test_suffix_boundary(self):
        for host in ("notbilibili.tv", "bilibili.tv.example.org"):
            self.assertFalse(matches(host, "bilibili.tv"))
        self.assertTrue(matches("api.bilibili.tv", "bilibili.tv"))

    def test_removing_exception_reproduces_wrong_direct_route(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            exception = f"RULE-SET,{INTERNATIONAL},{policy}"
            self.assertIn(exception, rules)
            rules.remove(exception)
            self.assertEqual(route("bilibili.tv", rules), "DIRECT")

    def test_moving_exception_after_domestic_reproduces_wrong_route(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            exception = f"RULE-SET,{INTERNATIONAL},{policy}"
            self.assertIn(exception, rules)
            rules.remove(exception)
            rules.insert(rules.index(f"RULE-SET,{DOMESTIC},DIRECT") + 1, exception)
            self.assertEqual(route("api.bilibili.tv", rules), "DIRECT")


if __name__ == "__main__":
    unittest.main()
