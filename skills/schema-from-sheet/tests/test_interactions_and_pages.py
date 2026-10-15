#!/usr/bin/env python3
"""Page names, interaction verbs, export and deployments from the workbook.

Usage: python3 tests/test_interactions_and_pages.py

Builds the Blue Dots Aug 2026 workbook (three domains) in create mode and checks,
against the deployed UP-GZB network.json:
1. my_items_label per domain from the Interaction_Rules "Page Name" table.
2. Seeker -> Job Provider is an `apply` action (status "submitted"); Job Provider ->
   Seeker is a `connect` with status "invited" (Shortlist); the rest are `connect`.
3. export.requester_domains on every interaction (the non-seeker side exports).
4. deployments.env: per deployment, SIGNALS_SERVED_DOMAINS, SIGNALS_UI_URLS and
   PUBLIC_PORTAL_URL from the Domains sheet.
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

# Deployed UP-GZB (bluedots-schemas blue_dot/up-gzb/network.json): action, statuses, export.
DEPLOYED = {
    ("seeker", "provider"): ("apply", ["created", "submitted", "accepted", "completed", "rejected", "cancelled"], ["provider"]),
    ("provider", "seeker"): ("connect", ["created", "invited", "accepted", "completed", "rejected", "cancelled"], ["provider"]),
    ("seeker", "service_provider"): ("connect", ["created", "accepted", "completed", "rejected", "cancelled"], ["service_provider"]),
    ("service_provider", "seeker"): ("connect", ["created", "accepted", "completed", "rejected", "cancelled"], ["service_provider"]),
    ("provider", "service_provider"): ("connect", ["created", "accepted", "completed", "rejected", "cancelled"], ["provider", "service_provider"]),
    ("service_provider", "provider"): ("connect", ["created", "accepted", "completed", "rejected", "cancelled"], ["provider", "service_provider"]),
}

failures = []


def expect(cond, message):
    if not cond:
        failures.append(message)


def run(*args):
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"FAIL {os.path.basename(args[0])}: {r.stderr.strip()}")
        sys.exit(1)


with tempfile.TemporaryDirectory() as out:
    decisions = os.path.join(out, "decisions.json")
    run(os.path.join(SCRIPTS, "init_decisions.py"), SPEC, "-o", decisions, "--network-id", "blue_dot")
    run(os.path.join(SCRIPTS, "build.py"), SPEC, decisions, out)
    network = json.load(open(os.path.join(out, "network.json")))

    labels = {d["id"]: d.get("my_items_label") for d in network["domains"]}
    expect(labels == {"seeker": "My Actions", "provider": "My Jobs", "service_provider": "My Services"},
           f"my_items_label: {labels}")

    got = {}
    for action, body in network["actions"].items():
        for it in body["interactions"]:
            statuses = it["event_schema"]["properties"]["status"]["enum"]
            got[(it["from_domain"], it["to_domain"])] = (action, statuses, (it.get("export") or {}).get("requester_domains"))
    for pair, want in DEPLOYED.items():
        expect(got.get(pair) == want, f"{pair[0]} -> {pair[1]}: got {got.get(pair)}, want {want}")
    expect(set(got) == set(DEPLOYED), f"interaction pairs: {sorted(got)}")
    for action, body in network["actions"].items():
        for it in body["interactions"]:
            creates = it["metric_categories"]["create"]
            first = it["event_schema"]["properties"]["status"]["enum"][1]
            if first in ("submitted", "invited"):
                expect(first in creates, f"{action} {it['from_domain']} -> {it['to_domain']}: '{first}' not in metric create")
    expect(network["actions"].get("apply", {}).get("description"), "apply action has no description")

    env_path = os.path.join(out, "deployments.env")
    expect(os.path.isfile(env_path), "deployments.env not written")
    if os.path.isfile(env_path):
        env = open(env_path).read()
        for prefix in ("dharwad", "gzb"):
            expect("SIGNALS_SERVED_DOMAINS=blue_dot/seeker,blue_dot/provider,blue_dot/service_provider" in env,
                   "SIGNALS_SERVED_DOMAINS missing")
            urls = (f"SIGNALS_UI_URLS=seeker=https://{prefix}-seekers.bluedotseconomy.org/auth/login,"
                    f"provider=https://{prefix}-providers.bluedotseconomy.org/auth/login,"
                    f"service_provider=https://{prefix}-services.bluedotseconomy.org/auth/login")
            expect(urls in env, f"SIGNALS_UI_URLS for {prefix} missing; got:\n{env}")
            expect(f"PUBLIC_PORTAL_URL=https://{prefix}-aggregators.bluedotseconomy.org" in env, f"PUBLIC_PORTAL_URL for {prefix}")

    check = subprocess.run([sys.executable, os.path.join(SCRIPTS, "check_schema.py"), os.path.join(out, "network.json"), out],
                           capture_output=True, text=True)
    expect("0 problem(s)" in check.stdout, f"check_schema: {check.stdout.strip()[-400:]}")

for f in failures:
    print(f"FAIL {f}")
print("FAIL" if failures else "PASS")
sys.exit(1 if failures else 0)
