"""Minimal upstream samples verified by GET on 2026-10-27.

Offline domain-only replay, not a full Shadowrocket engine or device test.
"""
import unittest

from test_service_exceptions import ROOT, matches, rules_from

BASE = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket"
SETS = {name: f"{BASE}/{name}/{name}.list" for name in ("Pinduoduo", "SuNing", "Google")}
SAMPLES = {
    SETS["Pinduoduo"]: ("pinduoduo.com", "yangkeduo.com", "pddpic.com"),
    SETS["SuNing"]: ("suning.com", "suningcdn.com", "suningcdn.net", "suningmail.com", "suning.cn"),
}
CONFIGS = (("shadowrocket.conf", "PROXY"), ("rules.yaml", "🔰 选择节点"))


def route(host, rules):
    for rule in rules:
        parts = rule.split(",")
        if parts[0] == "DOMAIN-SUFFIX" and matches(host, parts[1]):
            return parts[-1]
        if parts[0] == "RULE-SET":
            if any(matches(host, suffix) for suffix in SAMPLES.get(parts[1], ())):
                return parts[-1]
            # Google currently has DOMAIN-KEYWORD,gmail, also matching suningmail.com.
            if parts[1] == SETS["Google"] and "gmail" in host:
                return parts[-1]
        if parts[0] in ("FINAL", "MATCH"):
            return parts[-1]
    return None


class ShoppingRoutingTests(unittest.TestCase):
    def test_unique_direct_mapping_before_google_and_fallbacks(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            for name in ("Pinduoduo", "SuNing"):
                with self.subTest(file=filename, service=name):
                    rule = f"RULE-SET,{SETS[name]},DIRECT"
                    self.assertEqual(rules.count(rule), 1)
                    for later in (f"RULE-SET,{SETS['Google']},{policy}", "GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", rules[-1]):
                        self.assertLess(rules.index(rule), rules.index(later))

    def test_shopping_apex_and_subdomains_direct(self):
        for filename, _ in CONFIGS:
            rules = rules_from(ROOT / filename)
            for suffixes in SAMPLES.values():
                for suffix in suffixes:
                    for host in (suffix, "api." + suffix):
                        with self.subTest(file=filename, host=host):
                            self.assertEqual(route(host, rules), "DIRECT")

    def test_suffix_boundaries_do_not_capture_unrelated_domains(self):
        for filename, policy in CONFIGS:
            for host in ("notpinduoduo.com", "pinduoduo.com.example.org", "notsuning.com", "suning.com.example.org"):
                with self.subTest(file=filename, host=host):
                    self.assertEqual(route(host, rules_from(ROOT / filename)), policy)

    def test_gmail_still_proxy(self):
        for filename, policy in CONFIGS:
            for host in ("gmail.com", "mail.gmail.com"):
                self.assertEqual(route(host, rules_from(ROOT / filename)), policy)

    def test_removing_shopping_sets_exposes_missing_domain_coverage(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            for name in ("Pinduoduo", "SuNing"):
                rules.remove(f"RULE-SET,{SETS[name]},DIRECT")
            for host in ("pinduoduo.com", "pddpic.com", "suning.com", "suningmail.com"):
                self.assertEqual(route(host, rules), policy)
            # Existing .cn fallback is preserved, not counted as new coverage.
            self.assertEqual(route("suning.cn", rules), "DIRECT")

    def test_suning_after_google_reproduces_keyword_collision(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            suning = f"RULE-SET,{SETS['SuNing']},DIRECT"
            rules.remove(suning)
            rules.insert(rules.index(f"RULE-SET,{SETS['Google']},{policy}") + 1, suning)
            self.assertEqual(route("suningmail.com", rules), policy)


if __name__ == "__main__":
    unittest.main()
