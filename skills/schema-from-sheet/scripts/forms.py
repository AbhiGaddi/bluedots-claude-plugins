"""Aggregator form schemas and aggregator.config.yaml from the workbook (used by build.py).

Forms start from the reference forms in references/aggregator/ (the keys the
portal and its API read) and take from the "Aggregator Owner" / "Aggregator
Coordinator" sheets only what those keys allow:
  - Aggregator Type: the network's domains, labelled as the sheet labels them
  - Organisation Type, its Sub-type variants and Management Type: options and
    required flags from the sheet (organisation form)
  - optional reference fields with no sheet row are dropped (e.g. state)
The aggregator API accepts organisation_sub_type_<type> keys only for the
educational / non_educational types; other values are written but flagged in
decisions.md by the skill.
"""
import copy
import os
import re

ORG, ORG_UI = "org-registration.v1.json", "org-registration.v1.ui.json"
COORD, COORD_UI = "registration.v1.json", "registration.v1.ui.json"

# Reference keys -> sheet title pattern. Keys marked core are kept even
# without a sheet row (the portal cannot register without them).
ORG_KEYS = [("display_name", r"organi[sz]ation name", True), ("website", r"website", False),
            ("aggregator_type", r"aggregator type", False), ("organisation_type", r"organi[sz]ation type", False),
            ("management_type", r"management type", False), ("address", r"street|address", False),
            ("state", r"^state$", False), ("owner", r"owner", True), ("consent", r"consent", True)]
COORD_KEYS = [("name", r"organi[sz]ation", True), ("type", r"aggregator type", True), ("url", r"website", False),
              ("sub_org_name", r"sub-?org|division|institution", False), ("contact", r"contact|phone|email", True),
              ("locations", r"street|address", False), ("consent", r"consent", True)]
SUB_TYPE = re.compile(r"organi[sz]ation sub-?type", re.I)
WHEN = re.compile(r"=\s*(.+)$")


def slug(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "_".join(words) or "other"


def domain_for(name, domain_ids, alias=None):
    """Domain id a sheet name refers to ("Job Providers" -> provider); longest id wins."""
    if alias and name in alias:
        return alias[name]
    flat = re.sub(r"[^a-z]", "", name.lower()).rstrip("s")
    hits = [d for d in domain_ids if d.replace("_", "") in flat or flat in d.replace("_", "")]
    return max(hits, key=len) if hits else None


def _rows(sheet):
    return [r for r in sheet["fields"]] if sheet else []


def _find(rows, pattern):
    return next((r for r in rows if re.search(pattern, r["title"], re.I) and not SUB_TYPE.search(r["title"])), None)


def _sheet(spec, word):
    return next((f for f in spec.get("forms", []) if word in f["sheet"].lower()), None)


def _type_options(row, domain_ids, alias):
    """Sheet's Aggregator Type options mapped to domains, in sheet order; all domains if none map."""
    pairs = []
    for label in (row or {}).get("options", []):
        d = domain_for(label, domain_ids, alias)
        if d and d not in [p[0] for p in pairs]:
            pairs.append((d, label))
    return pairs or [(d, d.replace("_", " ").title()) for d in domain_ids]


def _enum_with_labels(options):
    return [slug(o) for o in options], list(options)


def _drop(form, ui, keys_present, keys):
    for key, _, core in keys:
        if not core and key not in keys_present and key in form["properties"]:
            form["properties"].pop(key)
            ui.pop(key, None)
            form["required"] = [k for k in form.get("required", []) if k != key]
    ui["ui:order"] = [k for k in ui["ui:order"] if k in form["properties"]]


def build_org_form(form, ui, sheet, domain_ids, alias=None):
    rows = _rows(sheet)
    present = {key for key, pattern, _ in ORG_KEYS if _find(rows, pattern)}
    props = form["properties"]
    type_row = _find(rows, r"aggregator type")
    if type_row:
        pairs = _type_options(type_row, domain_ids, alias)
        props["aggregator_type"]["items"]["enum"] = [d for d, _ in pairs]
        props["aggregator_type"]["examples"] = [[d] for d, _ in pairs]
        ui.setdefault("aggregator_type", {})["ui:enumNames"] = [label for _, label in pairs]
    org_row = _find(rows, r"organi[sz]ation type")
    if org_row and org_row.get("options"):
        props["organisation_type"]["enum"], labels = _enum_with_labels(org_row["options"])
        ui.setdefault("organisation_type", {})["ui:enumNames"] = labels
    added = []
    for row in rows:
        if not SUB_TYPE.search(row["title"]) or not row.get("options"):
            continue
        when = WHEN.search(row.get("dependency") or "")
        parent = slug(when.group(1)) if when else None
        key = f"organisation_sub_type_{parent}" if parent else "organisation_sub_type"
        values, labels = _enum_with_labels(row["options"])
        prop = {"type": "string", "title": "Organisation Sub-Type", "description": "Select the type that best applies."}
        if parent:
            prop["x-show-if"] = {"organisation_type": [parent]}
        prop["enum"] = values
        props[key] = prop
        ui[key] = {"ui:widget": "select", "ui:placeholder": "Select sub-type", "ui:enumNames": labels}
        added.append(key)
    mgmt = _find(rows, r"management type")
    if mgmt and mgmt.get("options"):
        values, labels = _enum_with_labels(mgmt["options"])
        props["management_type"] = {"type": "string", "title": "Management Type",
                                    "description": "Whether the organisation is privately run, government-operated, or an NGO.",
                                    "enum": values}
        ui["management_type"] = {"ui:widget": "select", "ui:placeholder": "Select management type", "ui:enumNames": labels}
        added.append("management_type")
    for key, pattern, core in ORG_KEYS:
        row = _find(rows, pattern)
        if row and not core and key in props:
            req = form.setdefault("required", [])
            if row.get("required") and key not in req:
                req.append(key)
            elif not row.get("required") and key in req and key != "aggregator_type":
                req.remove(key)
    _drop(form, ui, present | set(added), ORG_KEYS)
    order = ui["ui:order"]
    anchor = order.index("organisation_type") + 1 if "organisation_type" in order else len(order)
    for key in added:
        if key not in order:
            order.insert(anchor, key)
            anchor += 1
    # Properties and required keys follow the form's display order.
    form["properties"] = {k: props[k] for k in order}
    form["required"] = [k for k in order if k in form.get("required", [])]
    return form, ui


def build_coordinator_form(form, ui, sheet, domain_ids, alias=None):
    rows = _rows(sheet)
    present = {key for key, pattern, _ in COORD_KEYS if _find(rows, pattern)}
    pairs = _type_options(_find(rows, r"aggregator type"), domain_ids, alias)
    form["properties"]["type"]["enum"] = [d for d, _ in pairs]
    ui.setdefault("type", {})["ui:enumNames"] = [label.rstrip("s") if label.endswith("s") else label for _, label in pairs]
    if rows:
        _drop(form, ui, present, COORD_KEYS)
    return form, ui


def build_forms(spec, refs, domain_ids, alias=None):
    """The four form files, keyed by file name."""
    forms = {name: copy.deepcopy(refs[name]) for name in (ORG, ORG_UI, COORD, COORD_UI)}
    build_org_form(forms[ORG], forms[ORG_UI], _sheet(spec, "owner"), domain_ids, alias)
    build_coordinator_form(forms[COORD], forms[COORD_UI], _sheet(spec, "coordinator"), domain_ids, alias)
    return forms


def domain_labels(spec, domain_ids, alias=None):
    """{domain: (singular, plural)}, from the sheet's Aggregator Type labels where they map."""
    labels = {}
    for word in ("owner", "coordinator"):
        for d, label in _type_options(_find(_rows(_sheet(spec, word)), r"aggregator type"), domain_ids, alias):
            labels.setdefault(d, label)
    out = {}
    for d in domain_ids:
        plural = labels.get(d) or d.replace("_", " ").title() + "s"
        plural = plural if plural.endswith("s") else plural + "s"
        out[d] = (plural[:-1], plural)
    return out


def aggregator_config(template, network, spec, alias=None):
    """aggregator.config.yaml text: identity fields and labels per domain."""
    ids = [d["id"] for d in network["domains"]]
    overrides = []
    for d in network["domains"]:
        cf = d.get("contact_fields") or {}
        overrides.append(f"      {d['id']}:")
        overrides += [f"        {k}: {cf[k]}" for k in ("name", "phone", "email") if cf.get(k)]
    labels = []
    for d, (singular, plural) in domain_labels(spec, ids, alias).items():
        labels += [f"    {d}:", f"      singular: {singular}", f"      plural: {plural}", f"      tab_label: {plural}"]
    base = f"https://raw.githubusercontent.com/Blue-Dots-Economy/bluedots-schemas/refs/heads/main/{network['id']}"
    values = {"display_name": network["display_name"], "url_slug": slug(network["display_name"]).replace("_", "-"),
              "network_source": f"{base}/network.json", "consent_source": f"{base}/consent.json",
              "field_overrides": "\n".join(overrides), "domain_labels": "\n".join(labels)}
    text = template
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def load_refs(refs_dir, load):
    return {name: load(os.path.join(refs_dir, "aggregator", name)) for name in (ORG, ORG_UI, COORD, COORD_UI)}


def page_labels(spec, domain_ids, alias=None):
    """{domain: page name} from the first "Page Name" table (Interaction_Rules)."""
    tables = spec.get("page_names") or []
    if not tables:
        return {}
    out = {}
    for label, name in tables[0]["pages"].items():
        d = domain_for(label, domain_ids, alias)
        if d:
            out.setdefault(d, name)
    return out


def deployments_env(spec, network, alias=None):
    """Per-deployment env values from the Domains sheet (production links), or "" if none."""
    ids = [d["id"] for d in network["domains"]]
    blocks = []
    for inst in spec.get("domains") or []:
        ui, portal = {}, None
        for link in inst["links"]:
            url = (link.get("production") or "").strip().rstrip("/")
            if not url.startswith("http"):
                continue
            if re.search(r"aggregator", link["role"], re.I):
                portal = url
                continue
            d = domain_for(link["role"], ids, alias)
            if d:
                ui.setdefault(d, url)
        served = [d for d in ids if d in ui]
        lines = [f"# {inst['instance'] or 'Deployment'}"]
        if served:
            lines.append("SIGNALS_SERVED_DOMAINS=" + ",".join(f"{network['id']}/{d}" for d in served))
            lines.append("SIGNALS_UI_URLS=" + ",".join(f"{d}={ui[d]}/auth/login" for d in served))
        if portal:
            lines.append(f"PUBLIC_PORTAL_URL={portal}")
        if len(lines) > 1:
            blocks.append("\n".join(lines))
    if not blocks:
        return ""
    head = ("# Per-deployment settings from the workbook's Domains sheet (production links).\n"
            "# Signals: SIGNALS_SERVED_DOMAINS. Aggregator: SIGNALS_UI_URLS, PUBLIC_PORTAL_URL.\n")
    return head + "\n" + "\n\n".join(blocks) + "\n"
