"""Replay the observed local music-domain policy, without live network calls."""
import unittest

from test_apple_relay_routing import read_rules, replay_local


CONFIGS = ("shadowrocket.conf", "rules.yaml")
DOMAINS = ("music.163.com", "music.126.net", "music.126.com", "kugou.com")
ADDITIONS = tuple(f"DOMAIN-SUFFIX,{domain},DIRECT" for domain in DOMAINS)


class MusicRoutingTests(unittest.TestCase):
    def test_direct_domains_and_nested_subdomains_precede_fallbacks(self):
        for config in CONFIGS:
            rules = read_rules(config)
            for domain, addition in zip(DOMAINS, ADDITIONS):
                with self.subTest(config=config, domain=domain):
                    self.assertEqual(rules.count(addition), 1)
                    for fallback in ("GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", "FINAL,PROXY"):
                        self.assertLess(rules.index(addition), rules.index(fallback))
                    for host in (domain, "www." + domain, "api.media." + domain):
                        self.assertEqual(replay_local(host, rules, cn_ip=False), "DIRECT")

    def test_removal_exposes_original_domain_fallback(self):
        for config in CONFIGS:
            before = [rule for rule in read_rules(config) if rule not in ADDITIONS]
            for domain in DOMAINS:
                with self.subTest(config=config, domain=domain):
                    self.assertEqual(replay_local(domain, before, cn_ip=False), "PROXY")
                    self.assertEqual(replay_local(domain, before, cn_ip=True), "DIRECT")

    def test_parent_domains_cdn_and_suffix_boundaries_keep_original_policy(self):
        hosts = ("163.com", "126.net", "126.com", "kgimg.com", "kugou.net", "koowo.com",
                 "notkugou.com", "kugou.com.example.org", "notmusic.163.com",
                 "music.163.com.163jiasu.com", "music.126.net.example.org",
                 "www.iq.com", "www.youku.tv", "www.kuwo.cn", "kwcdn.kuwo.cn")
        for config in CONFIGS:
            rules = read_rules(config)
            before = [rule for rule in rules if rule not in ADDITIONS]
            for host in hosts:
                for cn_ip in (False, True):
                    with self.subTest(config=config, host=host, cn_ip=cn_ip):
                        self.assertEqual(replay_local(host, rules, cn_ip=cn_ip),
                                         replay_local(host, before, cn_ip=cn_ip))

    def test_kuwo_already_direct_via_cn_suffix(self):
        for config in CONFIGS:
            rules = read_rules(config)
            for host in ("kuwo.cn", "www.kuwo.cn", "kwcdn.kuwo.cn"):
                self.assertEqual(replay_local(host, rules, cn_ip=False), "DIRECT")
            self.assertNotIn("DOMAIN-SUFFIX,kuwo.cn,DIRECT", rules)
