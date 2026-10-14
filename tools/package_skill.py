#!/usr/bin/env python3
"""Build the standalone skill zip: dist/schema-from-sheet-v<version>.zip.

Usage: python3 tools/package_skill.py

The zip holds one folder, schema-from-sheet/, ready to unzip into
~/.claude/skills/ (or a project's .claude/skills/). Tests, caches and any
workbooks or CSVs are left out. The version comes from .claude-plugin/plugin.json.
"""
import json
import os
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SKILL = "schema-from-sheet"
SKILL_DIR = os.path.join(ROOT, "skills", SKILL)
EXCLUDED_DIRS = {"tests", "__pycache__", ".venv"}
EXCLUDED_SUFFIXES = (".pyc", ".xlsx", ".xls", ".xlsm", ".csv", ".DS_Store")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def skill_files():
    for dirpath, dirnames, filenames in os.walk(SKILL_DIR):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            if not name.endswith(EXCLUDED_SUFFIXES):
                yield os.path.join(dirpath, name)


def main():
    version = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))["version"]
    out = os.path.join(ROOT, "dist", f"{SKILL}-v{version}.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in skill_files():
            arcname = os.path.join(SKILL, os.path.relpath(path, SKILL_DIR))
            info = zipfile.ZipInfo(arcname, FIXED_TIME)
            info.external_attr = (0o755 if path.endswith(".py") else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, open(path, "rb").read())
    print(os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
