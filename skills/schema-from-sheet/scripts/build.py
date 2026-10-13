#!/usr/bin/env python3
"""Build network.json and the aggregator form schemas from a spec and decisions.

Usage: build.py <spec.json> <decisions.json> <output-folder>

Deterministic: the same spec + decisions always give the same files.
  spec.json       extract_sheet.py output (what the workbook says)
  decisions.json  init_decisions.py output, edited by a person or Claude
                  (keys, short titles, overrides; everything the sheet doesn't decide)
Everything else (domain settings, actions, instances, form layouts) comes from
references/ so the files always have the structure Signals and the aggregator
portal read.
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(HERE, "..", "references")
PHONE = re.compile(r"\b(phone|mobile|contact number|whatsapp)\b", re.I)
FORM_FILES = ["org-registration.v1.json", "org-registration.v1.ui.json",
              "registration.v1.json", "registration.v1.ui.json"]


def load(path):
    with open(path) as f:
        return json.load(f)


def rows_of(profile):
    """Sheet rows, conditional variants inlined after their parent."""
    out = []
    for f in profile["fields"]:
        out.append(f)
        for v in f.get("variants", []):
            out.append(dict(f, **{**v, "title": f["title"]}))
    return out


def kind(row):
    t = (row.get("type") or "").lower()
    if "upload" in t or t == "file":
        return "upload"
    if "geo" in t or "location" in t:
        return "geo_array" if "array" in t else "geo"
    if "email" in t:
        return "email"
    if t in ("url", "uri") or "url" in t or "uri" in t:
        return "url"
    if "boolean" in t:
        return "boolean"
    if "with search" in t:
        return "search"
    if "array" in t or "multi" in t:
        return "array"
    if "dropdown" in t or "select" in t:
        return "select"
    if "number" in t or "integer" in t:
        return "phone" if PHONE.search(row.get("title", "")) else "number"
    return "string"


def rule_property(row):
    """Sheet row -> JSON Schema property, by the mapping rules alone (no decisions)."""
    k, opts = kind(row), row.get("options") or []
    p = {}
    if k in ("string", "upload"):
        p["type"] = "string"
    elif k == "email":
        p.update({"type": "string", "format": "email"})
    elif k == "url":
        p.update({"type": "string", "x-uri": True, "maxLength": 2048})
    elif k == "phone":
        p.update({"type": "string", "pattern": "^[0-9]{10}$"})
    elif k == "number":
        p["type"] = "integer"
    elif k == "boolean":
        p["type"] = "boolean"
    elif k == "select":
        p["type"] = "string"
        if opts:
            p["enum"] = list(opts)
    elif k == "search":
        p.update({"type": "string", "x-reference-source": {"source": "colleges"}})
    elif k == "array":
        p.update({"type": "array", "items": {"type": "string"}})
        if opts:
            p["items"]["enum"] = list(opts)
    elif k == "geo":
        p["type"] = "string"
    elif k == "geo_array":
        p.update({"type": "array", "items": {"type": "string", "minLength": 1}})
    if row.get("required") and not row.get("dependency"):
        if p.get("type") == "string" and k not in ("email", "phone", "url"):
            p["minLength"] = 1
        if p.get("type") == "array":
            p["minItems"] = 1
    if row.get("pii"):
        p["private"] = True
    if row.get("vectorize") and not row.get("pii") and k in ("string", "select", "array", "search"):
        p["vectorize"] = True
    return p


def apply_overrides(p, d):
    p = copy.deepcopy(p)
    if d.get("property") is not None:
        p = copy.deepcopy(d["property"])
    for key in d.get("unset", []):
        p.pop(key, None)
    for key, val in (d.get("set") or {}).items():
        p[key] = copy.deepcopy(val)
    if d.get("title"):
        p["title"] = d["title"]
    if d.get("description"):
        p["description"] = d["description"]
    return p


def ordered(p, order):
    """Stable key order: the decisions' order first, the rest after."""
    out = {k: p[k] for k in order if k in p}
    out.update({k: v for k, v in p.items() if k not in out})
    return out


def find_parent(row, fields):
    """Parent field + values for a dependency like "visible only if category chosen is RCI"."""
    dep = row.get("dependency") or ""
    m = re.search(r"(?:if|when)\s+(.+?)\s*(?:=|\bchosen is\b|\bselected is\b|\bis\b)\s*(.+)$", dep, re.I | re.S)
    if not m:
        return None, []
    words = [w for w in re.findall(r"[a-z]+", m.group(1).lower()) if w not in ("the", "made", "visible", "only", "should", "be")]
    best, score = None, 0
    for key, prop, src in fields:
        hay = " ".join([key.replace("_", " "), prop.get("title", ""), prop.get("description", ""), src.get("title", "")]).lower()
        s = sum(1 for w in words if w in hay)
        if s > score:
            best, score = (key, prop), s
    if not best:
        return None, []
    enum = best[1].get("enum") or (best[1].get("items") or {}).get("enum") or []
    vals = [v for v in re.split(r"\s*(?:,|/|\bor\b)\s*", m.group(2).strip(" .'\"")) if v]
    vals = [next((e for e in enum if e.lower() == v.lower()), v) for v in vals]
    return best[0], vals


def build_domain(prof, dd, tpl, network_id):
    rows = rows_of(prof)
    by_row = {d["row"]: d for d in dd.get("fields", [])}
    props, sources, required, conditional = {}, {}, [], []
    for row in rows:
        d = by_row.get(row["row"], {})
        if d.get("skip") or (kind(row) == "upload" and d.get("property") is None):
            continue
        key = d["key"]
        p = apply_overrides(rule_property(row), d)
        props[key] = p
        sources[key] = row
        req = d.get("required", row.get("required"))
        if req and row.get("dependency"):
            conditional.append((key, row))
        elif req:
            required.append(key)
    for key, p in (dd.get("extra_properties") or {}).items():
        props[key] = copy.deepcopy(p)
        sources[key] = {}
    # Locations: the sheet's primary, else the first location field.
    locs = [k for k, r in sources.items() if r and kind(r) in ("geo", "geo_array")]
    primary = [k for k in locs if "primary" in (sources[k].get("map_discovery") or "").lower()]
    for i, k in enumerate(locs):
        if "location" not in props[k]:
            props[k]["location"] = "primary" if (k in primary or (not primary and i == 0)) else "secondary"
    # Conditions from the sheet's dependency text (unless decided otherwise).
    fields = [(k, props[k], sources[k]) for k in props]
    all_of = []
    for key, row in [(k, sources[k]) for k in props if sources[k] and sources[k].get("dependency")]:
        if "x-show-if" in props[key] or by_row.get(row["row"], {}).get("no_condition"):
            continue
        parent, vals = find_parent(row, [f for f in fields if f[0] != key])
        if parent and vals:
            props[key]["x-show-if"] = {parent: vals}
    for key, row in conditional:
        show = props[key].get("x-show-if") or {}
        if len(show) == 1:
            parent, vals = next(iter(show.items()))
            all_of.append((parent, vals[0], key))
    if dd.get("all_of") is not None:
        all_of_json = dd["all_of"]
    else:
        grouped = {}
        for parent, val, key in all_of:
            grouped.setdefault((parent, val), []).append(key)
        all_of_json = [{"if": {"properties": {p: {"const": v}}, "required": [p]}, "then": {"required": ks}}
                       for (p, v), ks in grouped.items()]
    order = dd.get("order") or list(props)
    props = {**{k: props[k] for k in order if k in props}, **{k: v for k, v in props.items() if k not in order}}
    if dd.get("required") is not None:
        required = dd["required"]
    schema = {"$schema": tpl["item_schema"]["$schema"], "title": dd.get("schema_title", f"{dd['id'].replace('_', ' ').title()} Profile 1.0")}
    if dd.get("display_name_field"):
        schema["display_name_field"] = dd["display_name_field"]
    schema.update({"type": "object", "additionalProperties": False})
    schema["x-form-layout"] = dd.get("layout") or default_layout(sources, props)
    schema["required"] = required
    if all_of_json:
        schema["allOf"] = all_of_json
    schema["properties"] = {k: ordered(v, dd.get("property_key_order", [])) for k, v in props.items()}
    domain = {}
    settings = copy.deepcopy(tpl["domain_defaults"])
    settings.update(copy.deepcopy(dd.get("settings") or {}))
    for k, v in settings.items():
        domain[k] = v
    domain["item_schemas"] = {dd.get("item_type", tpl["item_type"]): schema}
    domain["id"] = dd["id"]
    domain["card"] = dd.get("card") or default_card(sources, props)
    domain["contact_fields"] = dd.get("contact_fields") or default_contact(props)
    key_order = dd.get("domain_key_order")
    if key_order:
        domain = {**{k: domain[k] for k in key_order if k in domain}, **{k: v for k, v in domain.items() if k not in key_order}}
    return domain


def default_layout(sources, props):
    sections = []
    for key in props:
        title = (sources[key].get("section") if sources[key] else "") or "More Details"
        title = title.title()
        if not sections or sections[-1]["title"] != title:
            sections.append({"title": title, "fields": []})
        sections[-1]["fields"].append(key)
    return {"sections": sections}


def default_card(sources, props):
    shown = [k for k in props if sources[k] and sources[k].get("on_card") and not props[k].get("private")]
    title = next((k for k in props if "name" in k.lower() and not props[k].get("private")), None) \
        or next((k for k in props if "name" in k.lower()), list(props)[0])
    return {"title_field": title, "avatar_from": title, "default_fields": shown[:5]}


def default_contact(props):
    pick = lambda test: next((k for k, p in props.items() if p.get("private") and test(k, p)), None)
    out = {"name": pick(lambda k, p: "name" in k.lower()),
           "phone": pick(lambda k, p: "pattern" in p or "phone" in k.lower() or "mobile" in k.lower()),
           "email": pick(lambda k, p: p.get("format") == "email")}
    return {k: v for k, v in out.items() if v}


def build_actions(spec, dec, tpl, domains):
    if dec.get("actions") is not None:
        return copy.deepcopy(dec["actions"])
    net = dec["network"]["id"]
    by_name = {d["sheet"]: d["id"] for d in dec["domains"]}
    alias = dict((dec.get("interaction_domains") or {}))
    def dom(name):
        if name in alias:
            return alias[name]
        low = name.lower()
        for d in domains:
            if d["id"].replace("_", " ") in low or low.rstrip("s") in d["id"].replace("_", " "):
                return d["id"]
        return low.replace(" ", "_")
    interactions = []
    for block in spec.get("interactions", []):
        frm, to = dom(block["from"]), dom(block["to"])
        it = copy.deepcopy(tpl["interaction_defaults"])
        it = {"from_network": net, "from_domain": frm, "to_network": net, "to_domain": to, **it}
        cards = {d["id"]: d["card"].get("default_fields", []) for d in domains}
        it = dict(list(it.items())[:4] + [("column_fields", {"from": cards.get(frm, []), "to": cards.get(to, [])})] + list(it.items())[4:])
        title = f"{frm.replace('_', ' ').title()} To {to.replace('_', ' ').title()} Connect Event"
        it["event_schema"]["title"] = title
        interactions.append(it)
    return {"connect": {"description": tpl["action_description"], "interactions": interactions}}


def build_network(spec, dec, tpl):
    profiles = {p["sheet"]: p for p in spec["profiles"]}
    domains = [build_domain(profiles[d["sheet"]], d, tpl, dec["network"]["id"]) for d in dec["domains"]]
    n = dec["network"]
    out = {"display_name": n["display_name"], "description": n.get("description", ""),
           "schema_standard": tpl["schema_standard"], "domains": domains}
    if n.get("instances") is not None:
        out["instances"] = copy.deepcopy(n["instances"])
    else:
        inst = tpl["instance"]
        out["instances"] = [{"instance_name": inst["instance_name"].replace("{Network}", n["display_name"]).replace(
            "{Domain}", d["id"].replace("_", " ").title()), "instance_url": n.get("instance_url", inst["instance_url"]),
            "custom_item_schema_urls": {}, "domain_id": d["id"]} for d in domains]
    out["actions"] = build_actions(spec, dec, tpl, domains)
    out["id"] = n["id"]
    out["dashboard_buckets"] = copy.deepcopy(dec.get("dashboard_buckets") or tpl["dashboard_buckets"])
    return out


def merge(base, patch):
    """JSON merge patch (RFC 7386): null deletes a key."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    out = copy.deepcopy(base) if isinstance(base, dict) else {}
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = merge(out.get(k), v)
    return out


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    spec, dec = load(sys.argv[1]), load(sys.argv[2])
    out_dir = sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    tpl = load(os.path.join(REFS, "network.template.json"))
    network = build_network(spec, dec, tpl)
    with open(os.path.join(out_dir, "network.json"), "w") as f:
        f.write(json.dumps(network, indent=2, ensure_ascii=False) + "\n")
    for name in FORM_FILES:
        full = (dec.get("forms_full") or {}).get(name)
        form = copy.deepcopy(full) if full is not None else merge(
            load(os.path.join(REFS, "aggregator", name)), (dec.get("forms") or {}).get(name) or {})
        with open(os.path.join(out_dir, name), "w") as f:
            f.write(json.dumps(form, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"written": out_dir, "files": ["network.json"] + FORM_FILES,
                      "domains": {d["id"]: len(next(iter(d["item_schemas"].values()))["properties"]) for d in network["domains"]}}, indent=2))


if __name__ == "__main__":
    main()
