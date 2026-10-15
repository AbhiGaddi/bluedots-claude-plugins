#!/usr/bin/env python3
"""Check generated files have the structure Signals and the aggregator portal read.

Usage: check_schema.py <network.json> [<folder with org-registration.v1(.ui).json, registration.v1(.ui).json>]

Exit 1 on any problem. network.json checks mirror Signals' network config
validation (top level, domains, item schemas, actions/interactions, instances)
plus the rules Signals doesn't enforce at boot but that break things later
(private + vectorize, dangling x-show-if / allOf / card / layout references,
x-show-if on a field with no options, enum/enumNames length, repeated options,
fields with no title, no primary map location, a domain no interaction reaches).
Form checks require the keys
the aggregator portal's code reads, and that every field is placed in its
.ui.json ui:order.
"""
import json
import os
import re
import sys

ITEM_TYPE = re.compile(r"^[A-Za-z0-9_]+_\d+\.\d+$")
FORM_CONTRACT = {
    "org-registration.v1.json": ["display_name", "aggregator_type", "organisation_type", "owner", "consent"],
    "registration.v1.json": ["name", "type", "contact", "consent"],
}


def check_network(net, problems):
    p = problems.append
    for k in ("id", "display_name", "domains", "instances", "actions"):
        if k not in net:
            p(f"network: missing '{k}'")
    if not isinstance(net.get("domains"), list) or not net.get("domains"):
        p("network: 'domains' must be a non-empty list")
        return
    if not isinstance(net.get("instances"), list):
        p("network: 'instances' must be a list of {instance_name, instance_url, domain_id}")
    if not isinstance(net.get("actions"), dict):
        p("network: 'actions' must be an object keyed by action name ({description, interactions: [...]})")
    ids = set()
    for d in net["domains"]:
        did = d.get("id", "?")
        ids.add(did)
        for k in ("id", "item_schemas", "status_rules", "go_live_required"):
            if k not in d:
                p(f"{did}: missing '{k}'")
        if not isinstance(d.get("status_rules", []), list):
            p(f"{did}: status_rules must be a list")
        for t, s in (d.get("item_schemas") or {}).items():
            where = f"{did}/{t}"
            if not ITEM_TYPE.match(t):
                p(f"{where}: item type must be versioned like 'profile_1.0'")
            if s.get("type") != "object" or not isinstance(s.get("properties"), dict):
                p(f"{where}: item schema must be an object schema with 'properties'")
                continue
            props = s["properties"]
            for k, prop in props.items():
                w = f"{where}.{k}"
                if prop.get("private") is True and prop.get("vectorize") is True:
                    p(f"{w}: private and vectorize (PII must not be vectorized)")
                if "reveals_pii_on_status" in prop:
                    p(f"{w}: reveals_pii_on_status belongs on the interaction, not on a field")
                if not prop.get("title"):
                    p(f"{w}: no title (the form would show the raw key)")
                enum, names = prop.get("enum"), prop.get("enumNames")
                if enum is not None and names is not None and len(enum) != len(names):
                    p(f"{w}: enum has {len(enum)} values but enumNames has {len(names)}")
                options = enum or (prop.get("items") or {}).get("enum") or []
                for v in {v for v in options if options.count(v) > 1}:
                    p(f"{w}: option '{v}' is listed more than once")
                for dep, vals in (prop.get("x-show-if") or {}).items():
                    if dep not in props:
                        p(f"{w}: x-show-if refers to unknown field '{dep}'")
                        continue
                    allowed = props[dep].get("enum") or (props[dep].get("items") or {}).get("enum")
                    if not allowed:
                        p(f"{w}: x-show-if depends on '{dep}', which has no options to choose from")
                    for v in vals if isinstance(vals, list) else [vals]:
                        if allowed and v not in allowed:
                            p(f"{w}: x-show-if value '{v}' is not an option of '{dep}'")
            for k in s.get("required", []):
                if k not in props:
                    p(f"{where}: required field '{k}' is not declared")
            for c in s.get("allOf", []):
                for k in list((c.get("if") or {}).get("properties", {})) + (c.get("then") or {}).get("required", []):
                    if k not in props:
                        p(f"{where}: allOf refers to unknown field '{k}'")
            for sec in (s.get("x-form-layout") or {}).get("sections", []):
                for k in sec.get("fields", []):
                    if k not in props:
                        p(f"{where}: form layout lists unknown field '{k}'")
            if not any(prop.get("location") == "primary" for prop in props.values()):
                p(f"{where}: no field has location 'primary' (nothing to put on the map)")
            card = d.get("card") or {}
            for k in [card.get("title_field"), card.get("avatar_from")] + card.get("default_fields", []) + card.get("extra_fields", []):
                if k and k not in props:
                    p(f"{did}: card refers to unknown field '{k}'")
            for role, k in (d.get("contact_fields") or {}).items():
                if k not in props:
                    p(f"{did}: contact_fields.{role} refers to unknown field '{k}'")
    for inst in net.get("instances") or []:
        if inst.get("domain_id") not in ids:
            p(f"instances: domain_id '{inst.get('domain_id')}' is not a domain")
        if not inst.get("instance_url"):
            p("instances: missing instance_url")
    linked = {it.get(k) for a in (net.get("actions") or {}).values() if isinstance(a, dict)
              for it in a.get("interactions", []) for k in ("from_domain", "to_domain")}
    for did in sorted(ids - linked):
        p(f"{did}: no interaction from or to this domain (nobody can connect with it)")
    for name, action in (net.get("actions") or {}).items() if isinstance(net.get("actions"), dict) else []:
        for i, it in enumerate(action.get("interactions", [])):
            w = f"actions.{name}[{i}]"
            for k in ("from_network", "from_domain", "to_network", "to_domain", "event_schema"):
                if k not in it:
                    p(f"{w}: missing '{k}'")
            for k in ("from_domain", "to_domain"):
                if it.get(k) and it[k] not in ids:
                    p(f"{w}: {k} '{it[k]}' is not a domain")
            statuses = (((it.get("event_schema") or {}).get("properties") or {}).get("status") or {}).get("enum") or []
            for st in it.get("reveals_pii_on_status", []):
                if st not in statuses:
                    p(f"{w}: reveals_pii_on_status '{st}' is not an event status")


def check_forms(folder, problems):
    for name, keys in FORM_CONTRACT.items():
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            problems.append(f"{name}: missing")
            continue
        form = json.load(open(path))
        props = form.get("properties", {})
        for k in keys:
            if k not in props:
                problems.append(f"{name}: the aggregator portal reads '{k}', but the form doesn't declare it")
        ui_path = path.replace(".json", ".ui.json")
        if os.path.exists(ui_path):
            order = json.load(open(ui_path)).get("ui:order", [])
            if order and "*" not in order:
                for k in props:
                    if k not in order:
                        problems.append(f"{os.path.basename(ui_path)}: '{k}' not in ui:order, so the form won't show it")
        else:
            problems.append(f"{os.path.basename(ui_path)}: missing")


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    problems = []
    check_network(json.load(open(sys.argv[1])), problems)
    if len(sys.argv) == 3:
        check_forms(sys.argv[2], problems)
    for line in problems:
        print(line)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
