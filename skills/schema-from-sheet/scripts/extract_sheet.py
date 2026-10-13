#!/usr/bin/env python3
"""Turn a Blue Dots schema workbook into a normalized spec JSON.

Usage: extract_sheet.py <workbook.xlsx> [-o spec.json]

Sheets are recognised by their header row, not their names:
  profile sheets      header has "Fields" + "Required" + "Type"
  aggregator forms    header has "Field Name" + "Data Type"
  interaction rules   header has "User Interaction" + "Event"
  domains / URLs      sheet titled "Domains"
Hidden sheets are skipped (they hold sample data / scratch notes).
"""
import json
import re
import sys

import openpyxl

PROFILE_COLUMNS = {
    "section": ["framework"],
    "title": ["fields"],
    "required": ["required"],
    "type": ["type"],
    "options": ["options"],
    "dependency": ["dependency"],
    "map_discovery": ["map discovery"],
    "on_card": ["displayed on card"],
    "pii": ["pii field"],
    "masked": ["masked"],
    "unmask_event": ["unmask event"],
    "vectorize": ["vectorise", "vectorize"],
    "search": ["search field"],
    "filter": ["filter field"],
    "usage": ["how is the information used"],
    "bots": ["in the bots"],
    "behaviour": ["behaviour and activity"],
    "review": ["accepted or needs review", "needs review"],
}
FORM_COLUMNS = {
    "number": ["#"],
    "title": ["field name"],
    "help": ["field explanation"],
    "type": ["data type"],
    "options": ["options"],
    "dependency": ["dependency"],
    "required": ["mandatory"],
}
YES = {"yes", "y", "true"}


def clean(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"[ \t]+", " ", str(v)).strip()


def header_map(header, spec):
    """Column index for each spec key, matched on a lowercase substring of the header."""
    out = {}
    for i, h in enumerate(header):
        h = re.sub(r"\[.*?\]", "", clean(h)).lower()
        for key, needles in spec.items():
            if key not in out and any(n in h for n in needles):
                out[key] = i
    return out


def split_options(s):
    s = clean(s)
    if not s or s in {"—", "-", "number"}:
        return []
    parts = re.split(r"[;\n]", s)
    return [p.strip(" ;") for p in parts if p.strip(" ;")]


def yes(v):
    return clean(v).lower().split(" ")[0].strip("()") in YES


def rows(ws):
    for i, r in enumerate(ws.iter_rows(values_only=True), 1):
        if any(clean(c) for c in r):
            yield i, list(r)


def find_header(ws, must):
    for i, r in rows(ws):
        low = [re.sub(r"\[.*?\]", "", clean(c)).lower() for c in r]
        if all(any(m in c for c in low) for m in must):
            return i, r
        if i > 5:
            return None, None
    return None, None


def profile_sheet(ws):
    hrow, header = find_header(ws, ["fields", "required", "type"])
    cols = header_map(header, PROFILE_COLUMNS)
    get = lambda r, k: clean(r[cols[k]]) if k in cols and cols[k] < len(r) else ""
    fields, section = [], ""
    for i, r in rows(ws):
        if i <= hrow:
            continue
        section = get(r, "section") or section
        raw_title = get(r, "title")
        entry = {
            "row": i,
            "section": section,
            "required": yes(get(r, "required")),
            "type": get(r, "type").lower(),
            "options": split_options(get(r, "options")),
            "options_raw": get(r, "options"),
            "dependency": get(r, "dependency"),
            "map_discovery": get(r, "map_discovery"),
            "on_card": yes(get(r, "on_card")),
            "pii": yes(get(r, "pii")),
            "masked": yes(get(r, "masked")),
            "unmask_event": get(r, "unmask_event"),
            "vectorize": yes(get(r, "vectorize")),
            "search": yes(get(r, "search")),
            "filter": yes(get(r, "filter")),
            "usage": get(r, "usage"),
            "bots": get(r, "bots"),
            "review": get(r, "review"),
        }
        if not raw_title and not entry["type"]:
            continue
        if not raw_title and fields:
            # Blank title: a conditional variant of the field above (e.g. per-qualification sub-dropdowns).
            fields[-1].setdefault("variants", []).append(entry)
            continue
        first, _, rest = raw_title.partition("\n")
        entry["title"] = first.strip().rstrip("*").strip()
        entry["title_marker"] = first.strip()[len(first.strip().rstrip("*")):]
        if rest.strip():
            entry["subtitle"] = " ".join(rest.split())
        fields.append(entry)
    return {"sheet": ws.title, "columns": sorted(cols), "fields": fields}


def form_sheet(ws):
    hrow, header = find_header(ws, ["field name", "data type"])
    cols = header_map(header, FORM_COLUMNS)
    get = lambda r, k: clean(r[cols[k]]) if k in cols and cols[k] < len(r) else ""
    fields = []
    for i, r in rows(ws):
        if i <= hrow or not get(r, "title"):
            continue
        req = get(r, "required")
        fields.append({
            "row": i,
            "title": get(r, "title"),
            "help": get(r, "help"),
            "type": get(r, "type"),
            "options": split_options(get(r, "options")),
            "dependency": get(r, "dependency"),
            "required": req.upper().startswith("Y"),
            "server_set": "server" in req.lower(),
        })
    return {"sheet": ws.title, "fields": fields}


def interaction_sheet(ws):
    out, current = [], None
    for i, r in rows(ws):
        a, ev, direction = clean(r[0]), clean(r[1]) if len(r) > 1 else "", clean(r[2]) if len(r) > 2 else ""
        comment = clean(r[3]) if len(r) > 3 else ""
        if a.lower().startswith("user interaction"):
            continue
        if "-->" in a or "--->" in a:
            src, dst = [s.strip() for s in re.split(r"-+>", a)]
            current = {"from": src, "to": dst, "events": []}
            out.append(current)
        elif a and not ev:
            current = None  # another block (e.g. page names) starts
            continue
        if current is not None and ev:
            current["events"].append({"event": ev, "direction": direction, "comment": comment})
    return out


def domains_sheet(ws):
    out, block = [], None
    for i, r in rows(ws):
        a = clean(r[0])
        b = clean(r[1]) if len(r) > 1 else ""
        c = clean(r[2]) if len(r) > 2 else ""
        if a and not b.startswith("http") and not c.startswith("http"):
            block = {"instance": a, "links": []}
            out.append(block)
        elif block is not None and (b or c):
            block["links"].append({"role": a, "production": b, "uat": c})
    return [b for b in out if b["links"]]


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    out_path = args[args.index("-o") + 1] if "-o" in args else None
    wb = openpyxl.load_workbook(args[0], data_only=True)
    spec = {"workbook": args[0], "profiles": [], "forms": [], "interactions": [], "domains": [], "skipped_sheets": []}
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            spec["skipped_sheets"].append(f"{ws.title} (hidden)")
            continue
        if ws.title.strip().lower() == "domains":
            spec["domains"] = domains_sheet(ws)
        elif find_header(ws, ["fields", "required", "type"])[0]:
            spec["profiles"].append(profile_sheet(ws))
        elif find_header(ws, ["field name", "data type"])[0]:
            spec["forms"].append(form_sheet(ws))
        elif find_header(ws, ["user interaction", "event"])[0]:
            spec["interactions"] = interaction_sheet(ws)
        else:
            spec["skipped_sheets"].append(ws.title)
    text = json.dumps(spec, indent=2, ensure_ascii=False)
    if out_path:
        open(out_path, "w").write(text + "\n")
        summary = {p["sheet"]: len(p["fields"]) for p in spec["profiles"]}
        summary.update({f["sheet"]: len(f["fields"]) for f in spec["forms"]})
        print(json.dumps({"written": out_path, "fields": summary, "interactions": len(spec["interactions"]),
                          "domains": len(spec["domains"]), "skipped": spec["skipped_sheets"]}, indent=2))
    else:
        print(text)


if __name__ == "__main__":
    main()
