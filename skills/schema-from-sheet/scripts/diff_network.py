#!/usr/bin/env python3
"""Compare an extracted sheet spec with an existing network.json.

Usage: diff_network.py <spec.json> <network.json> [sheet=domain ...]
  Default mapping: *Seeker* -> seeker, *JobProvider* -> provider, *ServiceProvider* -> service_provider.

Fields are matched by normalised title (property "title"). Reports, per domain:
  NEW      sheet field with no matching property
  CHANGED  matched, but required / private / vectorize / filterable / enum differ
  ORPHAN   property in network.json that no sheet row matches (removed from the sheet?)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match import match_all  # noqa: E402

DEFAULT_MAP = [("seeker", "seeker"), ("jobprovider", "provider"), ("serviceprovider", "service_provider")]


def norm(t):
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def domain_for(sheet, overrides):
    if sheet in overrides:
        return overrides[sheet]
    key = norm(sheet)
    for needle, dom in DEFAULT_MAP:
        if needle in key:
            return dom
    return None


def enum_of(p):
    if "enum" in p:
        return p["enum"]
    if isinstance(p.get("items"), dict):
        return p["items"].get("enum")
    return None


def compare(f, key, p, required):
    diffs = []
    checks = [
        ("required", f["required"], key in required),
        ("private (PII)", f["pii"], p.get("private") is True),
        ("vectorize", f["vectorize"], p.get("vectorize") is True),
        ("filterable", f["filter"], p.get("filterable") is True),
    ]
    for name, sheet_v, json_v in checks:
        if sheet_v != json_v:
            diffs.append(f"{name}: sheet={sheet_v} json={json_v}")
    sheet_opts = f["options"]
    json_opts = enum_of(p)
    if sheet_opts and json_opts is not None and [norm(o) for o in sheet_opts] != [norm(o) for o in json_opts]:
        added = [o for o in sheet_opts if norm(o) not in {norm(x) for x in json_opts}]
        removed = [o for o in json_opts if norm(o) not in {norm(x) for x in sheet_opts}]
        if added or removed:
            diffs.append(f"enum: +{added} -{removed}")
        else:
            diffs.append("enum: same values, different order")
    if f["dependency"] and "x-show-if" not in p:
        diffs.append(f"dependency in sheet ({f['dependency'][:60]}) but no x-show-if")
    if f["pii"] and f["vectorize"]:
        diffs.append("PII + vectorize in sheet -> PII wins: private=true, no vectorize")
    return diffs


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    spec, net = json.load(open(a[0])), json.load(open(a[1]))
    overrides = dict(x.split("=", 1) for x in a[2:])
    domains = {d["id"]: d for d in net.get("domains", [])}
    for prof in spec["profiles"]:
        dom = domain_for(prof["sheet"], overrides)
        print(f"\n## {prof['sheet']} -> domain '{dom}'")
        if dom not in domains:
            print(f"  domain '{dom}' not in network.json (new domain, or pass {prof['sheet']}=<domain>)")
            continue
        schemas = domains[dom]["item_schemas"]
        props, required, all_props = {}, set(), []
        for t, s in schemas.items():
            required |= set(s.get("required", []))
            for k, p in s.get("properties", {}).items():
                props.setdefault(norm(p.get("title", k)), []).append((t, k, p))
                all_props.append((k, p))
        type_of = {k: t for t, s in schemas.items() for k in s.get("properties", {})}
        rows = [v for f in prof["fields"] for v in [f] + [dict(f, **{**x, "title": f["title"]}) for x in f.get("variants", [])]]
        found = match_all(rows, all_props)
        matched = set()
        for i, v in enumerate(rows):
            label = f'R{v["row"]} "{v["title"]}"' + (f' [{v["dependency"][:40]}]' if v["dependency"] else "")
            if v["type"] == "upload":
                print(f"  SKIP     {label}  upload fields are not supported by Signals")
                continue
            if i not in found:
                print(f"  NEW      {label}  type={v['type']} opts={len(v['options'])}" + (f"  review={v['review'][:60]!r}" if v["review"] else ""))
                continue
            (k, p), how = found[i]
            t = type_of[k]
            matched.add((t, k))
            d = compare(v, k, p, required)
            if how != "title" and norm(p.get("title", "")) != norm(v["title"]):
                d.insert(0, f'title: "{p.get("title", "")}" -> "{v["title"]}" (matched by {how}; keep key {k})')
            if v["review"] and "review" in v["review"].lower():
                d.append(f"REVIEW NOTE: {v['review'][:160]}")
            print(f"  {'CHANGED ' if d else 'same    '} {label} -> {t}.{k}" + "".join(f"\n             - {x}" for x in d))
        for norm_title, hits in props.items():
            for t, k, p in hits:
                if (t, k) not in matched:
                    print(f"  ORPHAN   {t}.{k} \"{p.get('title', '')}\"")


if __name__ == "__main__":
    main()
