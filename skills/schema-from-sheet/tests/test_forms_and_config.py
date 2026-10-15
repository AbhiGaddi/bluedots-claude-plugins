#!/usr/bin/env python3
"""Create mode reads the aggregator form sheets and writes aggregator.config.yaml.

Usage: python3 tests/test_forms_and_config.py

Builds the Immersion Day (Aug 2026, three domains) workbook in create mode and checks:
1. Organisation form: Aggregator Type lists the three domains with the sheet's
   labels; Organisation Type, both Sub-type variants and Management Type come
   from the sheet; no `state` field, because the sheet has none.
2. Coordinator form: Aggregator Type lists the three domains.
3. aggregator.config.yaml: identity fields and labels for every domain.
4. check_schema.py reports 0 problems.
Exit 1 on any failure.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
SPEC = os.path.join(HERE, "fixtures", "blue-dots-aug-2026.spec.json")
DOMAINS = ["seeker", "provider", "service_provider"]
LABELS = ["Seekers", "Job Providers", "Service Providers"]

failures = []


def expect(cond, message):
    if not cond:
        failures.append(message)


def run(*args):
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"FAIL {' '.join(os.path.basename(a) for a in args[:1])}: {r.stderr.strip()}")
        sys.exit(1)
    return r.stdout


with tempfile.TemporaryDirectory() as out:
    decisions = os.path.join(out, "decisions.json")
    run(os.path.join(SCRIPTS, "init_decisions.py"), SPEC, "-o", decisions)
    run(os.path.join(SCRIPTS, "build.py"), SPEC, decisions, out)
    load = lambda name: json.load(open(os.path.join(out, name)))

    org, org_ui = load("org-registration.v1.json"), load("org-registration.v1.ui.json")
    props = org["properties"]
    expect(props["aggregator_type"]["items"]["enum"] == DOMAINS,
           f"org aggregator_type enum: {props['aggregator_type']['items']['enum']}")
    expect(org_ui["aggregator_type"]["ui:enumNames"] == LABELS,
           f"org aggregator_type labels: {org_ui['aggregator_type'].get('ui:enumNames')}")
    expect(props["organisation_type"]["enum"] == ["educational", "non_educational"],
           f"organisation_type enum: {props['organisation_type'].get('enum')}")
    edu = props.get("organisation_sub_type_educational", {})
    expect(edu.get("enum", [])[:2] == ["school", "pu_college"] and edu.get("x-show-if") == {"organisation_type": ["educational"]},
           f"educational sub-type: {edu}")
    non = props.get("organisation_sub_type_non_educational", {})
    expect(non.get("x-show-if") == {"organisation_type": ["non_educational"]} and "employment_exchange" in non.get("enum", []),
           f"non-educational sub-type: {non}")
    expect(props.get("management_type", {}).get("enum") == ["private", "government", "ngo", "other"],
           f"management_type: {props.get('management_type')}")
    expect("management_type" in org["required"], f"org required: {org['required']}")
    expect("state" not in props and "state" not in org_ui["ui:order"], "org form still has a state field")
    expect(set(org_ui["ui:order"]) == set(props), f"org ui:order {org_ui['ui:order']} vs properties {list(props)}")
    order = org_ui["ui:order"]
    expect("management_type" in order and order.index("management_type") > order.index("organisation_type"),
           f"org ui:order: {order}")

    coord, coord_ui = load("registration.v1.json"), load("registration.v1.ui.json")
    expect(coord["properties"]["type"]["enum"] == DOMAINS, f"coordinator type enum: {coord['properties']['type']['enum']}")
    # Singular, as in the deployed UP-GZB coordinator form ("Seeker", not "Seekers").
    expect(coord_ui["type"]["ui:enumNames"] == ["Seeker", "Job Provider", "Service Provider"],
           f"coordinator type labels: {coord_ui['type'].get('ui:enumNames')}")
    expect("sub_org_name" in coord["properties"], "coordinator form lost sub_org_name")

    config_path = os.path.join(out, "aggregator.config.yaml")
    expect(os.path.isfile(config_path), "aggregator.config.yaml not written")
    if os.path.isfile(config_path):
        text = open(config_path).read()
        network = load("network.json")
        for d in network["domains"]:
            cf = d["contact_fields"]
            block = f"      {d['id']}:\n        name: {cf['name']}\n        phone: {cf['phone']}\n        email: {cf['email']}\n"
            expect(block in text, f"field_overrides for {d['id']} missing or wrong")
            expect(f"    {d['id']}:\n      singular: " in text, f"domain_labels for {d['id']} missing")
        expect("      singular: Service Provider\n      plural: Service Providers\n" in text, "service_provider labels")

    check = subprocess.run([sys.executable, os.path.join(SCRIPTS, "check_schema.py"), os.path.join(out, "network.json"), out],
                           capture_output=True, text=True)
    expect("0 problem(s)" in check.stdout, f"check_schema: {check.stdout.strip()[-400:]}")

for f in failures:
    print(f"FAIL {f}")
print("FAIL" if failures else "PASS")
sys.exit(1 if failures else 0)
