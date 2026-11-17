"""Replay the local domain changes for Youku and Migu Video."""
import unittest

from test_apple_relay_routing import read_rules, replay_local


CONFIGS = ("shadowrocket.conf", "rules.yaml")
DOMESTIC = ("youku.com", "miguvideo.com")
RULES = [f"DOMAIN-SUFFIX,{domain},DIRECT" for domain in DOMESTIC]


class YoukuMiguRoutingTests(unittest.TestCase):
    def test_new_rules_precede_fallbacks_and_cover_subdomains(self):
        for filename in CONFIGS:
            rules = read_rules(filename)
            for domain, rule in zip(DOMESTIC, RULES):
                with self.subTest(config=filename, domain=domain):
                    self.assertEqual(rules.count(rule), 1)
                    for fallback in ("GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", "FINAL,PROXY"):
                        self.assertLess(rules.index(rule), rules.index(fallback))
                    for host in (domain, f"www.{domain}", f"media.api.{domain}"):
                        self.assertEqual(replay_local(host, rules, cn_ip=False), "DIRECT")

    def test_removing_new_rules_exposes_the_previous_fallback(self):
        for filename in CONFIGS:
            before = [rule for rule in read_rules(filename) if rule not in RULES]
            for host in DOMESTIC:
                with self.subTest(config=filename, host=host):
                    self.assertEqual(replay_local(host, before, cn_ip=False), "PROXY")
                    self.assertEqual(replay_local(host, before, cn_ip=True), "DIRECT")

    def test_other_video_domains_keep_their_previous_routes(self):
        for filename in CONFIGS:
            rules = read_rules(filename)
            before = [rule for rule in rules if rule not in RULES]
            for host in ("youku.tv", "m.ykimg.com", "img.alicdn.com", "tudou.com",
                         "notyouku.com", "miguvideo.com.example.net",
                         "cmvideo.cn", "migu.cn", "youku.com.cn",
                         "www.iq.com", "vv.video.qq.com"):
                for cn_ip in (False, True):
                    with self.subTest(config=filename, host=host, cn_ip=cn_ip):
                        self.assertEqual(replay_local(host, rules, cn_ip=cn_ip),
                                         replay_local(host, before, cn_ip=cn_ip))
