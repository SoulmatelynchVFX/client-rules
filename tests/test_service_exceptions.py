from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
URL = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/ByteDance/ByteDance.list"
EXCEPTIONS = ("larksuite.com", "larksuitecdn.com")
# Minimal observed upstream subset, not a complete Shadowrocket engine.
OBSERVED = ("larksuite.com", "larksuitecdn.com", "feishu.cn", "feishucdn.com")

def rules_from(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if path.suffix == ".yaml":
        return [re.split(r"\s+#", line.strip()[2:])[0] for line in lines if line.strip().startswith("- ")]
    return [line.strip() for line in lines if line.startswith(("DOMAIN-", "RULE-SET,", "GEOIP,", "FINAL,"))]

def matches(host, suffix):
    return host == suffix or host.endswith("." + suffix)

def route_observed(host, rules):
    for rule in rules:
        parts = rule.split(",")
        if parts[0] == "DOMAIN-SUFFIX" and matches(host, parts[1]):
            return parts[-1]
        if parts[:2] == ["RULE-SET", URL] and any(matches(host, suffix) for suffix in OBSERVED):
            return parts[-1]
        if parts[0] in ("FINAL", "MATCH"):
            return parts[-1]
    return None

class ServiceExceptionTests(unittest.TestCase):
    def test_native_exceptions_precede_all_remote_sets(self):
        rules = rules_from(ROOT / "shadowrocket.conf")
        first_set = next(i for i, rule in enumerate(rules) if rule.startswith("RULE-SET,"))
        for suffix in EXCEPTIONS:
            rule = f"DOMAIN-SUFFIX,{suffix},PROXY"
            self.assertEqual(rules.count(rule), 1)
            self.assertLess(rules.index(rule), first_set)

    def test_legacy_mapping_and_order(self):
        rules = rules_from(ROOT / "rules.yaml")
        for suffix in EXCEPTIONS:
            rule = f"DOMAIN-SUFFIX,{suffix},🔰 选择节点"
            self.assertEqual(rules.count(rule), 1)
            self.assertLess(rules.index(rule), rules.index(f"RULE-SET,{URL},DIRECT"))

    def test_lark_apex_and_subdomains_proxy(self):
        for filename, policy in (("shadowrocket.conf", "PROXY"), ("rules.yaml", "🔰 选择节点")):
            rules = rules_from(ROOT / filename)
            for suffix in EXCEPTIONS:
                for host in (suffix, "api." + suffix):
                    with self.subTest(file=filename, host=host):
                        self.assertEqual(route_observed(host, rules), policy)

    def test_domestic_feishu_remains_direct(self):
        for filename in ("shadowrocket.conf", "rules.yaml"):
            rules = rules_from(ROOT / filename)
            for host in ("feishu.cn", "api.feishu.cn", "feishucdn.com", "static.feishucdn.com"):
                self.assertEqual(route_observed(host, rules), "DIRECT")

    def test_suffix_boundary_is_not_a_substring_match(self):
        for suffix in EXCEPTIONS:
            self.assertFalse(matches("not" + suffix, suffix))
            self.assertFalse(matches(suffix + ".example.org", suffix))
            self.assertTrue(matches("api." + suffix, suffix))

    def test_moving_exceptions_after_bytedance_reproduces_error(self):
        rules = rules_from(ROOT / "shadowrocket.conf")
        exceptions = [f"DOMAIN-SUFFIX,{suffix},PROXY" for suffix in EXCEPTIONS]
        for rule in exceptions:
            self.assertIn(rule, rules)
        reordered = [rule for rule in rules if rule not in exceptions]
        index = reordered.index(f"RULE-SET,{URL},DIRECT") + 1
        reordered[index:index] = exceptions
        for suffix in EXCEPTIONS:
            self.assertEqual(route_observed(suffix, reordered), "DIRECT")

if __name__ == "__main__":
    unittest.main()
