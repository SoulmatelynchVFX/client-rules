"""Local routing contracts with a dated subset of observed Baidu domain rules."""
import unittest
from test_apple_relay_routing import read_rules, replay_local


DOMAINS = ("hupu.com", "hupucdn.com")
ADDITIONS = tuple(f"DOMAIN-SUFFIX,{domain},DIRECT" for domain in DOMAINS)
CONFIGS = ("shadowrocket.conf", "rules.yaml")
BAIDU_URL = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Baidu/Baidu.list"
# Observed 2026-11-27; this subset exercises Tieba coverage, not a full engine.
BAIDU_SUFFIXES = ("baidu.com", "baidustatic.com", "bdimg.com", "bdstatic.com", "bcebos.com")


class HupuTiebaRoutingTests(unittest.TestCase):
    def test_hupu_domains_are_direct_before_fallbacks(self):
        for config in CONFIGS:
            rules = read_rules(config)
            for domain, addition in zip(DOMAINS, ADDITIONS):
                self.assertEqual(rules.count(addition), 1)
                for fallback in ("GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", "FINAL,PROXY"):
                    self.assertLess(rules.index(addition), rules.index(fallback))
                for host in (domain, "www." + domain, "api.media." + domain):
                    for cn_ip in (True, False):
                        self.assertEqual(replay_local(host, rules, cn_ip=cn_ip), "DIRECT")

    def test_removal_exposes_conditional_geoip_fallback(self):
        for config in CONFIGS:
            before = [r for r in read_rules(config) if r not in ADDITIONS]
            for domain in DOMAINS:
                self.assertEqual(replay_local(domain, before, cn_ip=False), "PROXY")
                self.assertEqual(replay_local(domain, before, cn_ip=True), "DIRECT")

    def test_boundaries_and_existing_policies_unchanged(self):
        hosts = [host for d in DOMAINS for host in ("not" + d, d + ".example.org")]
        hosts += ["hoopchina.com", "hupu.gg", "hupu.io", "shihuo.cn", "goalhi.cn",
                  "www.iq.com", "wetv.vip", "larksuite.com", "apple-relay.apple.com",
                  "www.zhihu.com", "www.douban.com"]
        for config in CONFIGS:
            rules = read_rules(config)
            before = [r for r in rules if r not in ADDITIONS]
            for host in hosts:
                for cn_ip in (True, False):
                    with self.subTest(config=config, host=host, cn_ip=cn_ip):
                        self.assertEqual(replay_local(host, rules, cn_ip=cn_ip),
                                         replay_local(host, before, cn_ip=cn_ip))

    def test_existing_baidu_ruleset_remains_direct_and_no_duplicate_tieba_rules_added(self):
        self.assertEqual(read_rules(CONFIGS[0]), read_rules(CONFIGS[1]))
        for config in CONFIGS:
            rules = read_rules(config)
            rule = f"RULE-SET,{BAIDU_URL},DIRECT"
            self.assertEqual(rules.count(rule), 1)
            self.assertFalse(any("/BaiDuTieBa/" in r for r in rules))
            self.assertNotIn("DOMAIN-SUFFIX,tieba.baidu.com,DIRECT", rules)
            self.assertLess(rules.index(rule), rules.index("GEOIP,CN,DIRECT"))
            expanded = []
            for r in rules:
                expanded.extend([f"DOMAIN-SUFFIX,{s},DIRECT" for s in BAIDU_SUFFIXES] if r == rule else [r])
            for host in ("tieba.baidu.com", "tiebapic.baidu.com", "cpro.baidustatic.com",
                         "ecma.bdimg.com", "tb1.bdstatic.com", "tieba-ares.cdn.bcebos.com"):
                self.assertEqual(replay_local(host, expanded, cn_ip=False), "DIRECT")
