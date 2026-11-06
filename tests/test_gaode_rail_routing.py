"""Domain samples inspected 2026-11-06; no live DNS/IP/UA or iOS replay."""
import unittest

from test_service_exceptions import ROOT, matches, rules_from

URL = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/GaoDe/GaoDe.list"
SUFFIXES = ("a-map.cn", "a-map.co", "a-map.link", "a-map.vip", "amap.com",
            "amapauto.com", "anav.com", "autonavi.com", "gaode.com")
RULE = f"RULE-SET,{URL},DIRECT"
CONFIGS = (("shadowrocket.conf", "PROXY"), ("rules.yaml", "🔰 选择节点"))


def route(host, rules):
    for rule in rules:
        parts = rule.split(",")
        if parts[0] == "DOMAIN-SUFFIX" and matches(host, parts[1]):
            return parts[-1], parts[1]
        if parts[:2] == ["RULE-SET", URL] and any(matches(host, suffix) for suffix in SUFFIXES):
            return parts[-1], URL
        if parts[0] in ("FINAL", "MATCH"):
            return parts[-1], parts[0]
    raise AssertionError("No terminal fallback")


class GaoDeRailRoutingTests(unittest.TestCase):
    def test_unique_direct_before_foreign_sets_and_fallback(self):
        for filename, proxy in CONFIGS:
            rules = rules_from(ROOT / filename)
            self.assertEqual(rules.count(RULE), 1)
            later = [r for r in rules if r.startswith("RULE-SET,") and r.endswith("," + proxy)
                     and "/BiliBiliIntl/" not in r]
            later += ["GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", rules[-1]]
            for other in later:
                self.assertLess(rules.index(RULE), rules.index(other))

    def test_apex_and_subdomains_use_gaode(self):
        for filename, _ in CONFIGS:
            for suffix in SUFFIXES:
                for host in (suffix, "api." + suffix, "cdn.api." + suffix):
                    with self.subTest(filename=filename, host=host):
                        self.assertEqual(route(host, rules_from(ROOT / filename)), ("DIRECT", URL))

    def test_lookalikes_keep_existing_fallback(self):
        for filename, proxy in CONFIGS:
            for suffix in SUFFIXES:
                for host in ("not" + suffix, suffix + ".example.org"):
                    policy, matched = route(host, rules_from(ROOT / filename))
                    self.assertNotEqual(matched, URL)
                    self.assertEqual(policy, "DIRECT" if host.endswith(".cn") else proxy)

    def test_removal_exposes_eight_new_suffixes(self):
        for filename, proxy in CONFIGS:
            rules = [r for r in rules_from(ROOT / filename) if r != RULE]
            for suffix in SUFFIXES:
                self.assertEqual(route(suffix, rules)[0], "DIRECT" if suffix.endswith(".cn") else proxy)

    def test_moving_after_fallback_loses_new_coverage(self):
        for filename, proxy in CONFIGS:
            rules = [r for r in rules_from(ROOT / filename) if r != RULE] + [RULE]
            self.assertEqual(route("amap.com", rules)[0], proxy)

    def test_12306_retains_cn_fallback_without_broad_additions(self):
        for filename, proxy in CONFIGS:
            rules = rules_from(ROOT / filename)
            self.assertFalse(any("/12306/" in r for r in rules))
            for host in ("12306.cn", "www.12306.cn", "kyfw.12306.cn"):
                self.assertEqual(route(host, rules), ("DIRECT", "cn"))
            for host in ("95572.com", "china-ric.com", "crct.com", "nntlj.com",
                         "peoplerail.com", "tdpress.com", "12306.cn.example.org"):
                self.assertEqual(route(host, rules)[0], proxy)


if __name__ == "__main__":
    unittest.main()
