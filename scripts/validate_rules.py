"""Validate this repository's restricted rules-list format (not a full YAML parser)."""
import argparse
from pathlib import Path
import re
from urllib.parse import urlsplit


def validate(text):
    errors = []
    rules = []
    header = False
    seen = set()
    for number, raw in enumerate(text.splitlines(), 1):
        line = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line == "rules:" and not header and not rules:
            header = True
            continue
        if not header or not raw.startswith("  - "):
            errors.append(f"line {number}: expected rules: followed by indented rule entries")
            continue
        parts = [part.strip() for part in line[2:].split(",")]
        kind = parts[0]
        expected = 2 if kind == "MATCH" else 3
        if kind not in {"RULE-SET", "DOMAIN-SUFFIX", "GEOIP", "MATCH"} or len(parts) != expected or not all(parts):
            errors.append(f"line {number}: unsupported or malformed rule")
            continue
        key = tuple(parts[:-1])
        if key in seen:
            errors.append(f"line {number}: duplicate matcher (possibly conflicting policy)")
        seen.add(key)
        if kind == "RULE-SET":
            url = urlsplit(parts[1])
            if url.scheme != "https" or not url.hostname or not url.path.endswith(".list"):
                errors.append(f"line {number}: RULE-SET must reference an HTTPS .list URL")
        rules.append(parts)
    if not header:
        errors.append("missing rules: header")
    if not rules or rules[-1][0] != "MATCH" or sum(rule[0] == "MATCH" for rule in rules) != 1:
        errors.append("exactly one MATCH fallback is required, at the end")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[1] / "rules.yaml")
    args = parser.parse_args()
    try:
        errors = validate(args.path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(1, f"Validation failed: {error}\n")
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    print("Rules structure validated (offline; client compatibility and URLs not checked).")


if __name__ == "__main__":
    main()
