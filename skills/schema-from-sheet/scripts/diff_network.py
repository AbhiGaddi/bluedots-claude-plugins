#!/usr/bin/env python3
"""Compare an extracted sheet spec with an existing network.json (read-only).

Usage: diff_network.py <spec.json> <network.json> [SheetName=domain ...]
  Default mapping: *Seeker* -> seeker, *JobProvider* -> provider, *ServiceProvider* -> service_provider.

Per sheet row:
  same / CHANGED   matched; CHANGED lists differences in required, private,
                   vectorize, enum values, conditions
  NEW              no property matched (a "closest" hint is shown, never auto-paired)
  ORPHAN           property in network.json that no sheet row matched
  SKIP             type Signals does not support (upload)
Notes, not differences:
  - Signals makes every declared, non-private field filterable; there is no
    filterable marker. "Filter Field = Yes" on a private field is flagged,
    because it can never be filtered.
  - An enum value that differs from an existing one only by case, quotes,
    punctuation or spacing is flagged: changing it would break stored data.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match import closest, match_all, norm  # noqa: E402

DEFAULT_MAP = [("seeker", "seeker"), ("jobprovider", "provider"), ("serviceprovider", "service_provider")]


def domain_for(sheet, overrides, available):
    if sheet in overrides:
        return overrides[sheet]
    key = norm(sheet)
    for needle, dom in DEFAULT_MAP:
        if needle in key and dom in available:
            return dom
    # e.g. "ServiceProvider…" when the network calls that domain "provider"
    if "provider" in key and "provider" in available:
        return "provider"
    return None


def enum_of(p):
    if "enum" in p:
        return p["enum"]
    if isinstance(p.get("items"), dict):
        return p["items"].get("enum")
    return None


def loose(v):
    return re.sub(r"[\s'\"‘’“”.,;:()\-_/]+", "", (v or "").lower())


def required_somewhere(key, schema):
    if key in schema.get("required", []):
        return True
    for clause in schema.get("allOf", []):
        if key in (clause.get("then") or {}).get("required", []):
            return True
    return False


def conditional(key, p, schema):
    if "x-show-if" in p:
        return True
    return any(key in (c.get("then") or {}).get("required", []) for c in schema.get("allOf", []))


def compare(f, key, p, schema):
    diffs = []
    if f["required"] != required_somewhere(key, schema):
        diffs.append(f"required: sheet={f['required']} json={required_somewhere(key, schema)}")
    if f["pii"] != (p.get("private") is True):
        diffs.append(f"private (PII): sheet={f['pii']} json={p.get('private') is True}")
    want_vec = f["vectorize"] and not f["pii"]
    if want_vec != (p.get("vectorize") is True):
        diffs.append(f"vectorize: sheet={f['vectorize']}{' (PII wins -> no)' if f['vectorize'] and f['pii'] else ''} json={p.get('vectorize') is True}")
    if f["filter"] and f["pii"]:
        diffs.append("Filter Field = Yes on a PII field: private fields can never be filtered")
    sheet_opts, json_opts = f["options"], enum_of(p)
    if sheet_opts and json_opts is not None:
        jl = {loose(x): x for x in json_opts}
        near = [(o, jl[loose(o)]) for o in sheet_opts if loose(o) in jl and o != jl[loose(o)]]
        added = [o for o in sheet_opts if loose(o) not in jl]
        removed = [x for x in json_opts if loose(x) not in {loose(o) for o in sheet_opts}]
        for o, x in near:
            diffs.append(f"enum value differs only in case/punctuation: sheet \"{o}\" vs json \"{x}\" (keep json; changing it breaks stored data)")
        if added or removed:
            diffs.append(f"enum: +{added} -{removed}")
    if f["dependency"] and not conditional(key, p, schema):
        diffs.append(f"dependency in sheet ({f['dependency'][:60]}) but no x-show-if / if-then")
    return diffs


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    spec, net = json.load(open(a[0])), json.load(open(a[1]))
    overrides = dict(x.split("=", 1) for x in a[2:])
    domains = {d["id"]: d for d in net.get("domains", [])}
    for prof in spec["profiles"]:
        dom = domain_for(prof["sheet"], overrides, domains)
        print(f"\n## {prof['sheet']} -> domain '{dom}'")
        if dom not in domains:
            print(f"  domain not found in network.json; pass {prof['sheet']}=<domain id>")
            continue
        schemas = domains[dom]["item_schemas"]
        all_props = [(k, p) for s in schemas.values() for k, p in s.get("properties", {}).items()]
        type_of = {k: t for t, s in schemas.items() for k in s.get("properties", {})}
        rows = [v for f in prof["fields"] for v in [f] + [dict(f, **{**x, "title": f["title"]}) for x in f.get("variants", [])]]
        found = match_all(rows, all_props)
        taken = {found[i][0][0] for i in found}
        for i, v in enumerate(rows):
            label = f'R{v["row"]} "{v["title"]}"' + (f' [{v["dependency"][:40]}]' if v["dependency"] else "")
            if v["type"] == "upload":
                print(f"  SKIP     {label}  upload fields are not supported")
                continue
            if i not in found:
                hint = closest(v, all_props, taken)
                print(f"  NEW      {label}  type={v['type']}" + (f"  closest: {hint[1]} \"{hint[2].get('title', '')}\"" if hint else ""))
                continue
            (k, p), how = found[i]
            schema = schemas[type_of[k]]
            d = compare(v, k, p, schema)
            if how != "title" and norm(p.get("title", "")) != norm(v["title"]):
                d.insert(0, f'title: "{p.get("title", "")}" -> "{v["title"]}" (matched by {how}; keep key {k})')
            if "needs review" in (v.get("review") or "").lower():
                d.append(f"REVIEW NOTE: {v['review'][:160]}")
            print(f"  {'CHANGED ' if d else 'same    '} {label} -> {type_of[k]}.{k}" + "".join(f"\n             - {x}" for x in d))
        for k, p in all_props:
            if k not in taken:
                print(f"  ORPHAN   {type_of[k]}.{k} \"{p.get('title', '')}\"")


if __name__ == "__main__":
    main()
