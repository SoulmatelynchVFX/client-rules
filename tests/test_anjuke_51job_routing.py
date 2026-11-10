"""Upstream suffix samples inspected 2026-11-10; no DNS/IP/UA simulation."""
import unittest

from test_service_exceptions import ROOT, matches, rules_from

BASE = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket"
SAMPLES = {
    f"{BASE}/Anjuke/Anjuke.list": (
        "aifang.com", "aifcdn.com", "ajkinclude.com", "anjuke.cn", "anjuke.com",
        "anjukestatic.com", "jikejia.cn"),
    f"{BASE}/51Job/51Job.list": (
        "51hr.com", "51ideal.com", "51jingying.com", "51job.com", "51jobcdn.com",
        "51laiqiang.com", "51mdd.com", "51miduoduo.com", "coolping.com", "correlation-one.cn",
        "ibmcampus.com", "maketion.com", "myyjs.com", "wuyoudagong.com", "xinghua.org.cn",
        "yingjiesheng.com", "yingjiesheng.net", "yingjiesheng.org", "zhiding.com.cn"),
}
ADDITIONS = tuple(f"RULE-SET,{url},DIRECT" for url in SAMPLES)
CONFIGS = (("shadowrocket.conf", "PROXY"), ("rules.yaml", "🔰 选择节点"))


def route(host, rules):
    for rule in rules:
        parts = rule.split(",")
        if parts[0] == "DOMAIN-SUFFIX" and matches(host, parts[1]):
            return parts[-1], parts[1]
        if parts[0] == "RULE-SET" and parts[1] in SAMPLES and any(
                matches(host, suffix) for suffix in SAMPLES[parts[1]]):
            return parts[-1], parts[1]
        if parts[0] in ("FINAL", "MATCH"):
            return parts[-1], parts[0]
    raise AssertionError("Missing terminal fallback")


class Anjuke51JobRoutingTests(unittest.TestCase):
    def test_unique_direct_mapping_before_foreign_sets_and_fallbacks(self):
        for filename, proxy in CONFIGS:
            rules = rules_from(ROOT / filename)
            later = [r for r in rules if r.startswith("RULE-SET,") and r.endswith("," + proxy)
                     and "/BiliBiliIntl/" not in r]
            later += ["GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", rules[-1]]
            for addition in ADDITIONS:
                self.assertEqual(rules.count(addition), 1)
                for other in later:
                    self.assertLess(rules.index(addition), rules.index(other))

    def test_apex_and_nested_subdomains_use_intended_set(self):
        for filename, _ in CONFIGS:
            for url, suffixes in SAMPLES.items():
                for suffix in suffixes:
                    for host in (suffix, "api." + suffix, "cdn.api." + suffix):
                        with self.subTest(filename=filename, host=host):
                            self.assertEqual(route(host, rules_from(ROOT / filename)), ("DIRECT", url))

    def test_suffix_boundaries_keep_existing_fallback(self):
        for filename, proxy in CONFIGS:
            for suffixes in SAMPLES.values():
                for suffix in suffixes:
                    for host in ("not" + suffix, suffix + ".example.org"):
                        policy, matched = route(host, rules_from(ROOT / filename))
                        self.assertNotIn(matched, SAMPLES)
                        self.assertEqual(policy, "DIRECT" if host.endswith(".cn") else proxy)

    def test_removal_exposes_twenty_one_new_suffixes(self):
        for filename, proxy in CONFIGS:
            rules = [r for r in rules_from(ROOT / filename) if r not in ADDITIONS]
            new_count = 0
            for suffixes in SAMPLES.values():
                for suffix in suffixes:
                    if not suffix.endswith(".cn"):
                        new_count += 1
                    self.assertEqual(route(suffix, rules)[0], "DIRECT" if suffix.endswith(".cn") else proxy)
            self.assertEqual(new_count, 21)

    def test_moving_after_fallback_loses_coverage(self):
        for filename, proxy in CONFIGS:
            rules = [r for r in rules_from(ROOT / filename) if r not in ADDITIONS] + list(ADDITIONS)
            for host in ("anjuke.com", "51job.com", "51jobcdn.com"):
                self.assertEqual(route(host, rules)[0], proxy)

    def test_parent_and_unlisted_domains_not_added(self):
        for filename, proxy in CONFIGS:
            for host in ("58.com", "ibm.com", "job.com", "jobcdn.com", "example.org"):
                self.assertEqual(route(host, rules_from(ROOT / filename))[0], proxy)


if __name__ == "__main__":
    unittest.main()
