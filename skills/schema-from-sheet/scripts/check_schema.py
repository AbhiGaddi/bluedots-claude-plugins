#!/usr/bin/env python3
"""Quick safety checks on a generated network.json.

Usage: check_schema.py <network.json>

Fails (exit 1) on:
  - a property that is both private and vectorized (PII is never vectorized)
  - an enum whose enumNames list has a different length
  - an x-show-if that names a field the schema does not declare
"""
import json
import sys


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    net = json.load(open(sys.argv[1]))
    problems = []
    for d in net.get("domains", []):
        for t, s in d.get("item_schemas", {}).items():
            props = s.get("properties", {})
            for k, p in props.items():
                where = f"{d.get('id')}/{t}.{k}"
                if p.get("private") is True and p.get("vectorize") is True:
                    problems.append(f"{where}: private and vectorize (PII must not be vectorized)")
                enum, names = p.get("enum"), p.get("enumNames")
                if enum is not None and names is not None and len(enum) != len(names):
                    problems.append(f"{where}: enum has {len(enum)} values but enumNames has {len(names)}")
                for dep in (p.get("x-show-if") or {}):
                    if dep not in props:
                        problems.append(f"{where}: x-show-if refers to unknown field '{dep}'")
    for line in problems:
        print(line)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
