#!/usr/bin/env python3
"""Golden tests: workbooks must rebuild their expected schemas exactly.

Usage: python3 tests/run_golden.py

1. Purple Dots (ALIMCO), update mode: init_decisions (spec + existing ALIMCO schema)
   -> build -> must equal tests/expected/ (network.json and the four aggregator form
   files), byte-for-byte in content.
2. The committed ALIMCO decisions fixture -> build -> must equal tests/expected/ too.
3. ALIMCO create mode (no existing schema) must pass check_schema.py.
4. Blue Dots (Aug 2026), create mode: init_decisions -> build -> must equal
   tests/expected-blue-dots/ (titles, conditions, interactions as the sheet says).
5. Every expected folder must pass check_schema.py.
Exit 1 on any failure. Run before every plugin release.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
SPEC = os.path.join(HERE, "fixtures", "purple-dots-oct-2026.spec.json")
DECISIONS = os.path.join(HERE, "fixtures", "purple-dots-alimco.decisions.json")
EXPECTED = os.path.join(HERE, "expected")
BLUE_SPEC = os.path.join(HERE, "fixtures", "blue-dots-aug-2026.spec.json")
BLUE_EXPECTED = os.path.join(HERE, "expected-blue-dots")
FILES = ["network.json", "org-registration.v1.json", "org-registration.v1.ui.json",
         "registration.v1.json", "registration.v1.ui.json"]


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True)


def same(out_dir, expected=EXPECTED):
    bad = []
    for name in FILES:
        exp = os.path.join(expected, name if name == "network.json" else os.path.join("aggregator", name))
        if json.load(open(os.path.join(out_dir, name))) != json.load(open(exp)):
            bad.append(name)
    return bad


def main():
    failures = []
    with tempfile.TemporaryDirectory() as t:
        dec = os.path.join(t, "decisions.json")
        r = run(os.path.join(SCRIPTS, "init_decisions.py"), SPEC, "-o", dec, "--existing",
                os.path.join(EXPECTED, "network.json"), "--existing-forms", os.path.join(EXPECTED, "aggregator"))
        if r.returncode:
            failures.append(f"init_decisions failed: {r.stderr.strip()}")
        for label, decisions in (("init_decisions -> build", dec), ("committed decisions -> build", DECISIONS)):
            out = os.path.join(t, label.split()[0])
            r = run(os.path.join(SCRIPTS, "build.py"), SPEC, decisions, out)
            if r.returncode:
                failures.append(f"{label}: build failed: {r.stderr.strip()}")
                continue
            bad = same(out)
            print(f"{label}: {'IDENTICAL to reference (5/5 files)' if not bad else 'DIFFERENT: ' + ', '.join(bad)}")
            failures += [f"{label}: {b} differs" for b in bad]
        new_dec, new_out = os.path.join(t, "new.json"), os.path.join(t, "new")
        run(os.path.join(SCRIPTS, "init_decisions.py"), SPEC, "-o", new_dec, "--network-id", "purple_dot",
            "--display-name", "Purple Dots")
        run(os.path.join(SCRIPTS, "build.py"), SPEC, new_dec, new_out)
        blue_dec, blue_out = os.path.join(t, "blue.json"), os.path.join(t, "blue")
        run(os.path.join(SCRIPTS, "init_decisions.py"), BLUE_SPEC, "-o", blue_dec, "--network-id", "blue_dot",
            "--display-name", "Blue Dots")
        r = run(os.path.join(SCRIPTS, "build.py"), BLUE_SPEC, blue_dec, blue_out)
        if r.returncode:
            failures.append(f"Blue Dots create mode: build failed: {r.stderr.strip()}")
        else:
            bad = same(blue_out, BLUE_EXPECTED)
            print(f"Blue Dots create mode -> build: {'IDENTICAL to expected (5/5 files)' if not bad else 'DIFFERENT: ' + ', '.join(bad)}")
            failures += [f"Blue Dots create mode: {b} differs" for b in bad]
        for label, net, forms in (("create mode", os.path.join(new_out, "network.json"), new_out),
                                  ("reference", os.path.join(EXPECTED, "network.json"), os.path.join(EXPECTED, "aggregator")),
                                  ("Blue Dots expected", os.path.join(BLUE_EXPECTED, "network.json"), os.path.join(BLUE_EXPECTED, "aggregator"))):
            r = run(os.path.join(SCRIPTS, "check_schema.py"), net, forms)
            print(f"check_schema ({label}): {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()}")
            if r.returncode:
                failures.append(f"check_schema ({label}): {r.stdout.strip()}")
    print("PASS" if not failures else "FAIL\n  " + "\n  ".join(failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
