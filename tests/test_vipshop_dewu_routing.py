"""Domain-only samples checked on 2026-10-30; not a device/network test."""
import unittest

from test_service_exceptions import ROOT, matches, rules_from

VIP_URL = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/VipShop/VipShop.list"
VIP_DOMAINS = ("appsimg.com", "appvipshop.com", "vip.com", "vipstatic.com")
ADDITIONS = (f"RULE-SET,{VIP_URL},DIRECT", "DOMAIN-SUFFIX,dewu.com,DIRECT")
CONFIGS = (("shadowrocket.conf", "PROXY"), ("rules.yaml", "🔰 选择节点"))


def route_sample(host, rules):
    # Only the verified VipShop sample and literal suffix rules are evaluated.
    # No DNS/GEOIP, other remote sets, IP, UA or complex rule simulation.
    for rule in rules:
        parts = rule.split(",")
        if parts[0] == "DOMAIN-SUFFIX" and matches(host, parts[1]):
            return parts[-1]
        if parts[:2] == ["RULE-SET", VIP_URL]:
            if any(matches(host, suffix) for suffix in VIP_DOMAINS):
                return parts[-1]
        if parts[0] in ("FINAL", "MATCH"):
            return parts[-1]
    return None


class VipShopDewuRoutingTests(unittest.TestCase):
    def test_unique_direct_rules_before_foreign_sets_and_fallbacks(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            later = [r for r in rules if r.startswith("RULE-SET,") and r.endswith("," + policy)
                     and "/BiliBiliIntl/" not in r]
            later += ["GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", rules[-1]]
            for addition in ADDITIONS:
                with self.subTest(file=filename, rule=addition):
                    self.assertEqual(rules.count(addition), 1)
                    for other in later:
                        self.assertLess(rules.index(addition), rules.index(other))

    def test_verified_apex_and_subdomains_direct(self):
        for filename, _ in CONFIGS:
            for suffix in (*VIP_DOMAINS, "dewu.com"):
                for host in (suffix, "www." + suffix, "api.shop." + suffix):
                    with self.subTest(file=filename, host=host):
                        self.assertEqual(route_sample(host, rules_from(ROOT / filename)), "DIRECT")

    def test_suffix_boundaries_do_not_capture_unrelated_domains(self):
        for filename, policy in CONFIGS:
            for suffix in (*VIP_DOMAINS, "dewu.com"):
                for host in ("not" + suffix, suffix + ".example.org"):
                    with self.subTest(file=filename, host=host):
                        self.assertEqual(route_sample(host, rules_from(ROOT / filename)), policy)

    def test_international_site_not_added_to_direct(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            self.assertFalse(any("poizon.com" in rule for rule in rules))
            for host in ("poizon.com", "www.poizon.com"):
                self.assertEqual(route_sample(host, rules), policy)

    def test_removal_exposes_domain_coverage_gap_without_geoip(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            for rule in ADDITIONS:
                rules.remove(rule)
            for host in (*VIP_DOMAINS, "dewu.com"):
                self.assertEqual(route_sample(host, rules), policy)
            self.assertEqual(route_sample("example.cn", rules), "DIRECT")


if __name__ == "__main__":
    unittest.main()
