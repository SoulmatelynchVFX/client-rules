from pathlib import Path
import unittest
from scripts.validate_rules import validate


class ValidateRulesTest(unittest.TestCase):
    def test_repository_rules(self):
        path = Path(__file__).resolve().parents[1] / "rules.yaml"
        self.assertEqual(validate(path.read_text(encoding="utf-8")), [])

    def test_comments_crlf_and_unicode_policy(self):
        self.assertEqual(validate("# comment\r\nrules:\r\n  - DOMAIN-SUFFIX,cn,DIRECT # note\r\n  - MATCH,🔰 选择节点\r\n"), [])

    def test_douyu_uses_direct_before_fallbacks(self):
        path = Path(__file__).resolve().parents[1] / "rules.yaml"
        rules = [line.strip()[2:] for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip().startswith("- ")]
        url = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Douyu/Douyu.list"
        matcher = f"RULE-SET,{url},"
        self.assertEqual([rule for rule in rules if rule.startswith(matcher)], [matcher + "DIRECT"])
        position = rules.index(matcher + "DIRECT")
        for prefix in ("GEOIP,CN,", "DOMAIN-SUFFIX,cn,", "MATCH,"):
            self.assertLess(position, next(index for index, rule in enumerate(rules) if rule.startswith(prefix)))

    def test_invalid_structures(self):
        for text in ["", "rules:\n", "rules:\n  - MATCH,Proxy\n  - GEOIP,CN,DIRECT",
                     "rules:\n  - MATCH,Proxy\n  - MATCH,Proxy",
                     "rules:\n  - GEOIP,CN,\n  - MATCH,Proxy",
                     "rules:\n  - UNKNOWN,cn,DIRECT\n  - MATCH,Proxy",
                     "rules:\n- MATCH,Proxy", "other:\n  - MATCH,Proxy"]:
            with self.subTest(text=text):
                self.assertTrue(validate(text))

    def test_duplicate_matcher_with_different_policy(self):
        self.assertTrue(validate("rules:\n  - GEOIP,CN,DIRECT\n  - GEOIP,CN,Proxy\n  - MATCH,Proxy"))

    def test_remote_url_shape(self):
        for url in ["http://example.com/a.list", "https:///a.list", "https://example.com/a.yaml"]:
            with self.subTest(url=url):
                self.assertTrue(validate(f"rules:\n  - RULE-SET,{url},DIRECT\n  - MATCH,Proxy"))
        self.assertEqual(validate("rules:\n  - RULE-SET,https://example.com/a.list,DIRECT\n  - MATCH,Proxy"), [])


if __name__ == "__main__":
    unittest.main()
