"""Offline community-domain policy contracts; remote sets are checked separately."""
import unittest
from test_apple_relay_routing import read_rules, replay_local


DOMAINS = ("zhihu.com", "zhimg.com", "douban.com", "douban.fm", "doubanio.com")
ADDITIONS = tuple(f"DOMAIN-SUFFIX,{domain},DIRECT" for domain in DOMAINS)
CONFIGS = ("shadowrocket.conf", "rules.yaml")


class CommunityRoutingTests(unittest.TestCase):
    def test_explicit_direct_policy_before_geoip_and_final_in_both_configs(self):
        for config in CONFIGS:
            rules = read_rules(config)
            for domain, addition in zip(DOMAINS, ADDITIONS):
                with self.subTest(config=config, domain=domain):
                    self.assertEqual(rules.count(addition), 1)
                    for fallback in ("GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", "FINAL,PROXY"):
                        self.assertLess(rules.index(addition), rules.index(fallback))
                    for host in (domain, "www." + domain, "api.media." + domain):
                        for cn_ip in (False, True):
                            self.assertEqual(replay_local(host, rules, cn_ip=cn_ip), "DIRECT")

    def test_removal_exposes_previous_conditional_geoip_fallback(self):
        for config in CONFIGS:
            before = [r for r in read_rules(config) if r not in ADDITIONS]
            for domain in DOMAINS:
                with self.subTest(config=config, domain=domain):
                    self.assertEqual(replay_local(domain, before, cn_ip=False), "PROXY")
                    self.assertEqual(replay_local(domain, before, cn_ip=True), "DIRECT")

    def test_lookalikes_and_existing_international_exceptions_keep_their_policy(self):
        hosts = [host for domain in DOMAINS
                 for host in ("not" + domain, domain + ".example.org")]
        hosts += ["www.iq.com", "wetv.vip", "larksuite.com", "larksuitecdn.com",
                  "apple-relay.apple.com", "apple-relay.fastly-edge.com", "www.youku.com"]
        for config in CONFIGS:
            rules = read_rules(config)
            before = [r for r in rules if r not in ADDITIONS]
            for host in hosts:
                for cn_ip in (False, True):
                    with self.subTest(config=config, host=host, cn_ip=cn_ip):
                        self.assertEqual(replay_local(host, rules, cn_ip=cn_ip),
                                         replay_local(host, before, cn_ip=cn_ip))

    def test_configs_stay_synchronized_and_do_not_add_community_ip_ranges(self):
        native, legacy = (read_rules(config) for config in CONFIGS)
        self.assertEqual(native, legacy)
        self.assertFalse(any(rule.startswith(("IP-CIDR,", "IP-CIDR6,")) for rule in native))
