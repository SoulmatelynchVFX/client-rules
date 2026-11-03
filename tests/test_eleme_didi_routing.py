"""Upstream domain samples fetched 2026-11-03; no DNS/GEOIP/UA simulation."""
import unittest

from test_service_exceptions import ROOT, matches, rules_from

BASE = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket"
ELEME_URL = f"{BASE}/Eleme/Eleme.list"
ELEME = ("ele.me", "ele.to", "eleme.cn", "eleme.com.cn", "eleme.io",
         "elemecdn.cn", "elemecdn.com", "elenet.me", "fengniaopaotui.cn",
         "fengniaozhongbao.cn", "xingxuanwaimai.com", "xyzele.com", "youcaishop.cn")
ADDITIONS = (f"RULE-SET,{ELEME_URL},DIRECT", "DOMAIN-SUFFIX,didichuxing.com,DIRECT")
CONFIGS = (("shadowrocket.conf", "PROXY"), ("rules.yaml", "🔰 选择节点"))
INTERNATIONAL = ("didi-food.com", "didiaustralia.blog", "didiglobal.com",
                 "didimobility.co.jp", "didimobility.com")


def route(host, rules):
    for rule in rules:
        parts = rule.split(",")
        if parts[0] == "DOMAIN-SUFFIX" and matches(host, parts[1]):
            return parts[-1], parts[1]
        if parts[:2] == ["RULE-SET", ELEME_URL] and any(matches(host, suffix) for suffix in ELEME):
            return parts[-1], ELEME_URL
        if parts[0] in ("FINAL", "MATCH"):
            return parts[-1], parts[0]
    return None, None


class ElemeDidiRoutingTests(unittest.TestCase):
    def test_unique_mapping_before_foreign_sets_and_fallbacks(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            later = [rule for rule in rules if rule.startswith("RULE-SET,")
                     and rule.endswith("," + policy) and "/BiliBiliIntl/" not in rule]
            later += ["GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", rules[-1]]
            for addition in ADDITIONS:
                self.assertEqual(rules.count(addition), 1)
                for other in later:
                    self.assertLess(rules.index(addition), rules.index(other))

    def test_apex_and_subdomains_hit_intended_rule(self):
        for filename, _ in CONFIGS:
            rules = rules_from(ROOT / filename)
            for suffix in (*ELEME, "didichuxing.com"):
                for host in (suffix, "api." + suffix, "cdn.shop." + suffix):
                    with self.subTest(file=filename, host=host):
                        expected = "didichuxing.com" if suffix == "didichuxing.com" else ELEME_URL
                        self.assertEqual(route(host, rules), ("DIRECT", expected))

    def test_suffix_boundaries_do_not_capture_unrelated_hosts(self):
        for filename, policy in CONFIGS:
            for suffix in (*ELEME, "didichuxing.com"):
                for host in ("not" + suffix, suffix + ".example.org"):
                    with self.subTest(file=filename, host=host):
                        # A lookalike ending in .cn still uses the existing .cn fallback.
                        expected = ("DIRECT", "cn") if host.endswith(".cn") else (policy, "FINAL" if filename.endswith("conf") else "MATCH")
                        self.assertEqual(route(host, rules_from(ROOT / filename)), expected)

    def test_international_and_shared_services_not_added_to_direct(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            self.assertFalse(any("/DiDi/DiDi.list" in rule for rule in rules))
            for suffix in INTERNATIONAL:
                for host in (suffix, "www." + suffix):
                    self.assertEqual(route(host, rules)[0], policy)

    def test_removal_exposes_new_domain_coverage(self):
        for filename, policy in CONFIGS:
            rules = [rule for rule in rules_from(ROOT / filename) if rule not in ADDITIONS]
            for host in (*ELEME, "didichuxing.com"):
                expected = "DIRECT" if host.endswith(".cn") else policy
                self.assertEqual(route(host, rules)[0], expected)

    def test_existing_cn_fallback_preserved(self):
        for filename, _ in CONFIGS:
            self.assertEqual(route("example.cn", rules_from(ROOT / filename)), ("DIRECT", "cn"))

    def test_rules_after_terminal_fallback_no_longer_cover_domains(self):
        for filename, policy in CONFIGS:
            rules = rules_from(ROOT / filename)
            moved = [rule for rule in rules if rule not in ADDITIONS] + list(ADDITIONS)
            for host in ("ele.me", "elemecdn.com", "didichuxing.com"):
                self.assertEqual(route(host, moved)[0], policy)


if __name__ == "__main__":
    unittest.main()
