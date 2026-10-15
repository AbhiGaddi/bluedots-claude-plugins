#!/usr/bin/env python3
"""Draft decisions.json for build.py.

Usage:
  init_decisions.py <spec.json> -o decisions.json [--network-id ID] [--display-name NAME]
                    [--existing network.json] [--existing-forms DIR] [--key-style snake|camel]

Without --existing (a new network): keys from the titles, rule defaults, and a
TODO list (decisions.md) of what a person should look at.

With --existing (the network already exists, e.g. a later version of a deployed
schema): each sheet row is matched to an existing field and keeps its key,
title and description; only real differences are recorded (as "set"/"unset"
pins for what the existing file does differently from the rules). Domain
settings, layout, card, actions, instances are copied from the existing file.
With these decisions, build.py reproduces the existing file exactly, and every
sheet change shows up as a TODO to accept or reject.
"""
import argparse
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import dependency_clauses, kind, match_values, rule_property, rows_of  # noqa: E402
from match import match_all, norm  # noqa: E402

DEFAULT_MAP = [("seeker", "seeker"), ("jobprovider", "provider"), ("serviceprovider", "service_provider")]
SHEET_ONLY = ("x-show-if", "location")  # build.py derives these; pin them only when they differ


def make_key(title, style, taken):
    words = re.findall(r"[a-z0-9]+", title.lower())
    stop = {"what", "is", "your", "the", "a", "an", "do", "you", "which", "of", "to", "for", "in", "and", "or",
            "are", "if", "select", "that", "applies", "please", "share", "any"}
    words = [w for w in words if w not in stop][:4] or words[:3] or ["field"]
    key = "_".join(words) if style == "snake" else words[0] + "".join(w.title() for w in words[1:])
    base, i = key, 2
    while key in taken:
        key, i = f"{base}{'_' if style == 'snake' else ''}{i}", i + 1
    taken.add(key)
    return key


def short_title(question):
    stop = {"what", "is", "your", "the", "a", "an", "do", "you", "which", "of", "to", "for", "in", "are", "please",
            "share", "select", "that", "applies", "where", "can", "how"}
    words = re.findall(r"[A-Za-z0-9%][A-Za-z0-9%'-]*", question)
    title = " ".join(w if w.isupper() else w[0].upper() + w[1:] for w in words if w.lower() not in stop)
    if len(title) > 40:
        title = title[:41].rsplit(" ", 1)[0]
    return title or question


def condition_label(dependency):
    """"if highest qualification = ITI / Other Vocational Training" -> "ITI / Other Vocational Training"."""
    parts = []
    for _, text in dependency_clauses(dependency):
        vals, _ = match_values(text, [])
        parts.append(" / ".join(vals))
    return ", ".join(p for p in parts if p) or "conditional"


def domain_id(sheet, existing_ids):
    key = norm(sheet)
    for needle, dom in DEFAULT_MAP:
        if needle in key:
            if dom in existing_ids or not existing_ids:
                return dom
    if "provider" in key and "provider" in existing_ids:
        return "provider"
    if "seeker" in key and "seeker" in existing_ids:
        return "seeker"
    return re.sub(r"_?(profile|schema|myservices|sche)+.*$", "", re.sub(r"(?<!^)(?=[A-Z])", "_", sheet).lower()).strip("_")


def diff_property(rule, want):
    """set/unset that turn the rule's property into the wanted one."""
    sets = {k: v for k, v in want.items() if k not in ("title", "description") and rule.get(k) != v}
    unset = [k for k in rule if k not in want and k not in ("title", "description")]
    return sets, unset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--existing")
    ap.add_argument("--existing-forms")
    ap.add_argument("--network-id")
    ap.add_argument("--display-name")
    ap.add_argument("--key-style", choices=["snake", "camel"])
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    ex = json.load(open(a.existing)) if a.existing else None
    ex_domains = {d["id"]: d for d in (ex or {}).get("domains", [])}
    style = a.key_style or ("snake" if ex and any("_" in k for d in ex["domains"] for s in d["item_schemas"].values() for k in s["properties"]) else "camel" if not ex else "camel")
    todo = []
    wb = os.path.basename(spec.get("workbook", ""))
    net_id = a.network_id or (ex or {}).get("id") or re.sub(r"[^a-z0-9]+", "_", re.sub(r"\[.*?\]|schema.*$", "", wb, flags=re.I).lower()).strip("_") or "network"
    dec = {"network": {"id": net_id,
                       "display_name": a.display_name or (ex or {}).get("display_name") or net_id.replace("_", " ").title(),
                       "description": (ex or {}).get("description", "")},
           "domains": []}
    if ex:
        dec["network"]["instances"] = ex.get("instances")
        dec["actions"] = ex.get("actions")
        dec["dashboard_buckets"] = ex.get("dashboard_buckets")
    else:
        todo.append(f"network id '{net_id}' and display name derived from the workbook name; confirm")
        todo.append("instance_url defaults to http://localhost:2742; set the real API URL")
    for prof in spec["profiles"]:
        did = domain_id(prof["sheet"], set(ex_domains))
        exd = ex_domains.get(did)
        rows = [r for r in rows_of(prof)]
        dd = {"sheet": prof["sheet"], "id": did, "fields": []}
        taken = set()
        if exd:
            item_type, schema = next(iter(exd["item_schemas"].items()))
            props = list(schema["properties"].items())
            found = match_all([dict(r) for r in rows], props)
            # By elimination: an unmatched row and an unmatched existing field that are the
            # only ones of their kind (same JSON type and same private flag) are the same field.
            taken_keys = {found[i][0][0] for i in found}
            sig = lambda p: (p.get("type"), bool(p.get("private")), "location" in p)
            free_rows = [i for i, r in enumerate(rows) if i not in found and kind(r) != "upload"]
            free_props = [(k, p) for k, p in props if k not in taken_keys]
            for i in free_rows:
                rs = sig({**rule_property(rows[i]), **({"location": 1} if kind(rows[i]).startswith("geo") else {})})
                cands = [kp for kp in free_props if sig(kp[1]) == rs]
                same_kind_rows = [j for j in free_rows if sig({**rule_property(rows[j]), **({"location": 1} if kind(rows[j]).startswith("geo") else {})}) == rs]
                if len(cands) == 1 and len(same_kind_rows) == 1:
                    found[i] = (cands[0], "elimination")
                    free_props.remove(cands[0])
            req_all = set(schema.get("required", []))
            for c in schema.get("allOf", []):
                req_all |= set((c.get("then") or {}).get("required", []))
            used = set()
            for i, r in enumerate(rows):
                if i in found:
                    (key, want), how = found[i]
                    used.add(key)
                    rule = rule_property(r)
                    sets, unset = diff_property(rule, want)
                    f = {"row": r["row"], "key": key, "title": want.get("title"), "description": want.get("description")}
                    if kind(r) == "upload":
                        # Signals has no upload field; keep the existing field the row stands for.
                        f = {"row": r["row"], "key": key, "property": want}
                        dd["fields"].append(f)
                        used.add(key)
                        todo.append(f"{prof['sheet']} R{r['row']} '{r['title']}': upload row kept as existing field '{key}'")
                        continue
                    if sets:
                        f["set"] = sets
                    if unset:
                        f["unset"] = unset
                    sheet_req = bool(r.get("required"))
                    json_req = key in req_all
                    if sheet_req != json_req:
                        f["required"] = json_req
                        todo.append(f"{prof['sheet']} R{r['row']} {key}: sheet says required={sheet_req}, existing schema {json_req} (kept existing)")
                    if r.get("dependency") and "x-show-if" not in want:
                        f["no_condition"] = True
                    for k, v in sets.items():
                        if k in ("private", "vectorize", "enum", "items", "type"):
                            todo.append(f"{prof['sheet']} R{r['row']} {key}: '{k}' differs from the sheet; kept existing {json.dumps(v)[:80]}")
                    if how != "title":
                        todo.append(f"{prof['sheet']} R{r['row']} '{r['title']}' matched to existing '{key}' by {how}; confirm")
                    dd["fields"].append({k: v for k, v in f.items() if v is not None})
                else:
                    if kind(r) == "upload":
                        dd["fields"].append({"row": r["row"], "skip": True})
                        todo.append(f"{prof['sheet']} R{r['row']} '{r['title']}': upload not supported, skipped")
                        continue
                    key = make_key(r["title"], style, set(k for k, _ in props) | taken)
                    dd["fields"].append({"row": r["row"], "key": key})
                    todo.append(f"{prof['sheet']} R{r['row']} '{r['title']}': NEW field '{key}' (no existing match); confirm key, title, or pair it with an existing field")
            extra = {k: p for k, p in props if k not in used}
            if extra:
                dd["extra_properties"] = extra
                for k in extra:
                    todo.append(f"{did}.{k}: in the existing schema but no sheet row; kept as is")
            dd["item_type"] = item_type
            dd["schema_title"] = schema.get("title")
            if schema.get("display_name_field"):
                dd["display_name_field"] = schema["display_name_field"]
            dd["order"] = [k for k, _ in props] + [f["key"] for f in dd["fields"] if f.get("key") and f["key"] not in dict(props)]
            dd["required"] = [k for k in schema.get("required", [])] + [f["key"] for f in dd["fields"] if f.get("key") not in dict(props) and next((r for r in rows if r["row"] == f["row"]), {}).get("required") and not next((r for r in rows if r["row"] == f["row"]), {}).get("dependency")]
            dd["all_of"] = schema.get("allOf", [])
            dd["layout"] = schema.get("x-form-layout")
            dd["card"] = exd.get("card")
            dd["contact_fields"] = exd.get("contact_fields")
            dd["settings"] = {k: v for k, v in exd.items() if k not in ("item_schemas", "id", "card", "contact_fields")}
            dd["domain_key_order"] = list(exd)
        else:
            repeated = {t for t in (r["title"] for r in rows) if [x["title"] for x in rows].count(t) > 1}
            for r in rows:
                if kind(r) == "upload":
                    dd["fields"].append({"row": r["row"], "skip": True})
                    todo.append(f"{prof['sheet']} R{r['row']} '{r['title']}': upload not supported, skipped")
                    continue
                key = make_key(r["title"], style, taken)
                f = {"row": r["row"], "key": key, "title": r["title"]}
                if len(r["title"]) > 40 or r["title"].endswith("?"):
                    f["description"] = r["title"]
                    f["title"] = short_title(r["title"])
                    todo.append(f"{prof['sheet']} R{r['row']}: short title '{f['title']}' proposed for the question; adjust")
                if r["title"] in repeated and r.get("dependency"):
                    # Conditional variants share the sheet title; tell them apart by their condition.
                    f["title"] = f"{f['title']} ({condition_label(r['dependency'])})"
                dd["fields"].append(f)
            todo.append(f"{did}: card, layout and contact fields use defaults; review")
        dec["domains"].append(dd)
    if a.existing_forms:
        dec["forms_full"] = {}
        for name in ("org-registration.v1.json", "org-registration.v1.ui.json", "registration.v1.json", "registration.v1.ui.json"):
            path = os.path.join(a.existing_forms, name)
            if os.path.exists(path):
                dec["forms_full"][name] = json.load(open(path))
    for w in spec.get("warnings", []):
        todo.append(f"extractor: {w}")
    dec["todo"] = todo
    with open(a.out, "w") as f:
        f.write(json.dumps(dec, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"written": a.out, "domains": [d["id"] for d in dec["domains"]], "todo": len(todo)}, indent=2))


if __name__ == "__main__":
    main()
