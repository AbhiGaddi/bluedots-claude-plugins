#!/usr/bin/env python3
"""Packaging test: the standalone skill zip must work outside the plugin.

Usage: python3 tests/test_package.py

1. tools/package_skill.py builds dist/schema-from-sheet-v<version>.zip.
2. The zip holds one top-level folder, schema-from-sheet/, with SKILL.md,
   scripts/, references/ and requirements.txt; no tests, caches or workbooks.
3. SKILL.md does not depend on ${CLAUDE_PLUGIN_ROOT} (unset outside a plugin).
4. The unzipped check_schema.py validates the golden network: the scripts
   run from the zip alone.
Exit 1 on any failure.
"""
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
VERSION = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))["version"]
ZIP = os.path.join(ROOT, "dist", f"schema-from-sheet-v{VERSION}.zip")
EXPECTED = os.path.join(ROOT, "skills", "schema-from-sheet", "tests", "expected")

failures = []

build = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "package_skill.py")],
                       capture_output=True, text=True)
if build.returncode != 0 or not os.path.isfile(ZIP):
    print(f"FAIL build: {build.stderr.strip() or 'no zip at ' + ZIP}")
    sys.exit(1)

names = zipfile.ZipFile(ZIP).namelist()
for required in ["schema-from-sheet/SKILL.md", "schema-from-sheet/requirements.txt",
                 "schema-from-sheet/scripts/build.py", "schema-from-sheet/scripts/check_schema.py",
                 "schema-from-sheet/references/network.template.json"]:
    if required not in names:
        failures.append(f"missing {required}")
for name in names:
    if not name.startswith("schema-from-sheet/"):
        failures.append(f"outside the skill folder: {name}")
    if "/tests/" in name or "__pycache__" in name or name.endswith((".pyc", ".xlsx", ".xls", ".xlsm", ".csv")):
        failures.append(f"should not ship: {name}")

with tempfile.TemporaryDirectory() as tmp:
    zipfile.ZipFile(ZIP).extractall(tmp)
    skill = os.path.join(tmp, "schema-from-sheet")
    if "CLAUDE_PLUGIN_ROOT" in open(os.path.join(skill, "SKILL.md")).read():
        failures.append("SKILL.md uses ${CLAUDE_PLUGIN_ROOT}, which is unset outside a plugin")
    check = subprocess.run([sys.executable, os.path.join(skill, "scripts", "check_schema.py"),
                            os.path.join(EXPECTED, "network.json"), os.path.join(EXPECTED, "aggregator")],
                           capture_output=True, text=True)
    if "0 problem(s)" not in check.stdout:
        failures.append(f"unzipped check_schema.py failed: {check.stdout.strip()} {check.stderr.strip()}")

for f in failures:
    print(f"FAIL {f}")
print(f"{'FAIL' if failures else 'PASS'}: {os.path.relpath(ZIP, ROOT)} ({len(names)} files)")
sys.exit(1 if failures else 0)
