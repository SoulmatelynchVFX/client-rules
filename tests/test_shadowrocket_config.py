from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


class ShadowrocketConfigTest(unittest.TestCase):
    def setUp(self):
        self.sections = {}
        section = None
        for raw in (ROOT / "shadowrocket.conf").read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                self.assertNotIn(section, self.sections)
                self.sections[section] = []
            else:
                self.assertIsNotNone(section)
                self.sections[section].append(line)
        self.rules = self.sections["Rule"]

    def test_sections_and_no_embedded_nodes(self):
        self.assertEqual(set(self.sections), {"General", "Rule"})
        self.assertIn("bypass-system = true", self.sections["General"])

    def test_matches_existing_application_mapping_in_order(self):
        expected = []
        for raw in (ROOT / "rules.yaml").read_text(encoding="utf-8").splitlines():
            line = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
            if not line.startswith("- "):
                continue
            parts = [part.strip() for part in line[2:].split(",")]
            if parts[0] == "MATCH":
                parts[0] = "FINAL"
            if parts[-1] == "🔰 选择节点":
                parts[-1] = "PROXY"
            expected.append(",".join(parts))
        self.assertTrue(expected)
        self.assertEqual(self.rules, expected)

    def test_builtin_policies_unique_matchers_and_terminal_fallback(self):
        seen = set()
        for rule in self.rules:
            parts = rule.split(",")
            self.assertIn(parts[0], {"RULE-SET", "DOMAIN-SUFFIX", "GEOIP", "FINAL"})
            self.assertEqual(len(parts), 2 if parts[0] == "FINAL" else 3)
            self.assertTrue(all(parts))
            self.assertIn(parts[-1], {"DIRECT", "PROXY"})
            matcher = tuple(parts[:-1])
            self.assertNotIn(matcher, seen)
            seen.add(matcher)
        self.assertEqual(self.rules[-1], "FINAL,PROXY")
        self.assertEqual(sum(rule.startswith("FINAL,") for rule in self.rules), 1)

    def test_remote_rules_use_shadowrocket_lists(self):
        remote = [rule.split(",")[1] for rule in self.rules if rule.startswith("RULE-SET,")]
        self.assertTrue(remote)
        for value in remote:
            url = urlsplit(value)
            self.assertEqual(url.scheme, "https")
            self.assertEqual(url.netloc, "raw.githubusercontent.com")
            self.assertTrue(url.path.startswith(
                "/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/"))
            self.assertTrue(url.path.endswith(".list"))

    def test_douyu_direct_before_fallbacks(self):
        rule = ("RULE-SET,https://raw.githubusercontent.com/blackmatrix7/"
                "ios_rule_script/master/rule/Shadowrocket/Douyu/Douyu.list,DIRECT")
        self.assertEqual(self.rules.count(rule), 1)
        for fallback in ("GEOIP,CN,DIRECT", "DOMAIN-SUFFIX,cn,DIRECT", "FINAL,PROXY"):
            self.assertLess(self.rules.index(rule), self.rules.index(fallback))


if __name__ == "__main__":
    unittest.main()
