"""Domain-only replay for the Tencent Video and iQIYI policy."""
import unittest

from test_apple_relay_routing import read_rules, replay_local


CONFIGS = ("shadowrocket.conf", "rules.yaml")
DOMESTIC = ("v.qq.com", "video.qq.com", "qqvideo.gtimg.com", "iqiyi.com", "qiyi.com")
INTERNATIONAL_SUFFIXES = (
    "iq.com", "inter.iqiyi.com", "intl-rcd.iqiyi.com", "intl-subscription.iqiyi.com",
    "intl.iqiyi.com", "vv.video.qq.com", "wetv.vip", "wetvinfo.com",
)
INTERNATIONAL_HOSTS = ("cache.video.iqiyi.com", "wetv.qq.com")


class VideoRoutingTests(unittest.TestCase):
    def test_domestic_domains_are_direct_even_with_a_non_cn_ip(self):
        for config in CONFIGS:
            rules = read_rules(config)
            for suffix in DOMESTIC:
                for host in (suffix, "media." + suffix):
                    with self.subTest(config=config, host=host):
                        self.assertIn(f"DOMAIN-SUFFIX,{suffix},DIRECT", rules)
                        self.assertEqual(replay_local(host, rules, cn_ip=False), "DIRECT")

    def test_international_domains_are_proxy_even_with_a_cn_ip(self):
        for config in CONFIGS:
            rules = read_rules(config)
            first_direct = next(i for i, rule in enumerate(rules) if rule.endswith(",DIRECT"))
            for suffix in INTERNATIONAL_SUFFIXES:
                self.assertLess(rules.index(f"DOMAIN-SUFFIX,{suffix},PROXY"), first_direct)
                for host in (suffix, "media." + suffix):
                    with self.subTest(config=config, host=host):
                        self.assertEqual(replay_local(host, rules, cn_ip=True), "PROXY")
            for host in INTERNATIONAL_HOSTS:
                with self.subTest(config=config, host=host):
                    self.assertLess(rules.index(f"DOMAIN,{host},PROXY"), first_direct)
                    self.assertEqual(replay_local(host, rules, cn_ip=True), "PROXY")

    def test_reordering_exceptions_reproduces_the_suffix_conflicts(self):
        overlapping = (
            "DOMAIN-SUFFIX,intl.iqiyi.com,PROXY",
            "DOMAIN-SUFFIX,vv.video.qq.com,PROXY",
            "DOMAIN,cache.video.iqiyi.com,PROXY",
        )
        for config in CONFIGS:
            rules = read_rules(config)
            reordered = [rule for rule in rules[:-1] if rule not in overlapping]
            reordered += [*overlapping, rules[-1]]
            for rule in overlapping:
                host = rule.split(",")[1]
                with self.subTest(config=config, host=host):
                    self.assertEqual(replay_local(host, reordered, cn_ip=False), "DIRECT")

    def test_exact_hosts_and_suffixes_keep_their_boundaries(self):
        for config in CONFIGS:
            rules = read_rules(config)
            self.assertEqual(replay_local("sub.cache.video.iqiyi.com", rules, cn_ip=False), "DIRECT")
            self.assertEqual(replay_local("sub.wetv.qq.com", rules, cn_ip=True), "DIRECT")
            self.assertEqual(replay_local("notiq.com", rules, cn_ip=True), "DIRECT")
            self.assertEqual(replay_local("iq.com.example.net", rules, cn_ip=True), "DIRECT")
            for host in ("qq.com", "gtimg.com", "notiqiyi.com", "v.qq.com.example.net", "iqiyipic.com"):
                with self.subTest(config=config, host=host):
                    self.assertEqual(replay_local(host, rules, cn_ip=False), "PROXY")


if __name__ == "__main__":
    unittest.main()
