#!/usr/bin/env python3
"""Turn a Blue Dots schema workbook into a normalized spec JSON.

Usage: extract_sheet.py <workbook.xlsx> [-o spec.json]

Sheets are recognised by their header row, not their names:
  profile sheets      header has "Fields" + "Required" + "Type"
  aggregator forms    header has "Field Name" + "Data Type"
  interaction rules   "User Interaction" + "Event" (A --> B blocks), or a flat
                      table with "Event" + "Sender" + "Receiver" (or From / To)
  domains / URLs      sheet titled "Domains"
Hidden sheets are skipped (they hold sample data, translations or notes).

The summary lists "warnings": columns not mapped, type values not recognised,
Yes/No cells carrying extra text, and visible sheets in no known format.
Nothing the extractor can't place is dropped silently.
"""
import json
import re
import sys

import openpyxl

# key -> header aliases. A header equal to an alias beats one that starts with it,
# which beats one that merely contains it, so "Fields" wins over "Fields Hindi Version".
PROFILE_COLUMNS = {
    "section": ["framework", "section"],
    "title": ["fields", "field name", "field"],
    "go_live": ["fields required to change profile status to live", "required to change profile status",
                "status to live", "required to go live"],
    "required": ["required", "mandatory"],
    "type": ["type", "data type"],
    "options": ["options", "values"],
    "dependency": ["dependency", "depends on", "child & parent association", "parent association",
                   "shown if", "condition", "visible if"],
    "map_discovery": ["map discovery"],
    "on_card": ["displayed on card", "shown on card"],
    "pii": ["pii field", "pii"],
    "masked": ["masked"],
    "unmask_event": ["unmask event"],
    "vectorize": ["vectorise", "vectorize"],
    "search": ["search field", "search"],
    "filter": ["filter field", "filter"],
    "usage": ["how is the information used"],
    "bots": ["in the bots", "fields in the bots"],
    "behaviour": ["behaviour and activity"],
    "review": ["accepted or needs review", "needs review"],
}
FORM_COLUMNS = {
    "number": ["#"],
    "section": ["purple dot structure", "structure", "section"],
    "title": ["field name"],
    "help": ["field explanation"],
    "type": ["data type"],
    "options": ["options"],
    "dependency": ["dependency", "depends on"],
    "required": ["mandatory"],
    "visibility": ["who can see"],
}
# Columns that are context, not schema; never reported as unmapped.
IGNORED_HEADERS = ["sample data", "hindi", "translation", "version", "comment", "notes"]
# Headers that must never be taken as the field title (translations).
NOT_A_TITLE = ["hindi", "kannada", "marathi", "tamil", "telugu", "bengali", "translation", "version"]

KNOWN_TYPES = [
    "string", "free text", "text", "number", "integer", "email", "url", "uri", "phone",
    "dropdown", "single select", "select", "array selection", "multi select", "multi-select", "array",
    "conditional dropdown", "dropdown with search", "geo", "location", "upload", "file",
    "boolean", "date", "date-time", "alpha numeric",
]
YES = {"yes", "y", "true"}
NO = {"no", "n", "false", ""}


def clean(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"[ \t]+", " ", str(v)).strip()


def header_text(h):
    return " ".join(re.sub(r"\[.*?\]", "", clean(h)).lower().split())


def header_map(header, spec):
    """Best column per key: exact alias (3) > starts with alias (2) > contains alias (1). Columns used once."""
    scored = []
    for i, h in enumerate(header):
        text = header_text(h)
        if not text:
            continue
        for key, aliases in spec.items():
            if key == "title" and any(w in text for w in NOT_A_TITLE):
                continue
            best = 0
            for a in aliases:
                if text == a:
                    best = max(best, 3)
                elif text.startswith(a):
                    best = max(best, 2)
                elif a in text:
                    best = max(best, 1)
            if best:
                # longer, more specific aliases win ties ("fields required to change …" over "required")
                specificity = max((len(a) for a in aliases if a in text), default=0)
                scored.append((best, specificity, -i, key, i))
    cols, used = {}, set()
    for best, _, _, key, i in sorted(scored, reverse=True):
        if key not in cols and i not in used:
            cols[key] = i
            used.add(i)
    return cols


def unmapped(header, cols):
    used = set(cols.values())
    out = []
    for i, h in enumerate(header):
        text = header_text(h)
        if text and i not in used and not any(w in text for w in IGNORED_HEADERS):
            out.append(clean(h).replace("\n", " "))
    return out


def options_listed(s):
    """Every option in the cell, in order, repeats included."""
    s = clean(s)
    if not s or s in {"—", "-", "number"}:
        return []
    parts = [p.strip(" ;") for p in re.split(r"[;\n]", s) if p.strip(" ;")]
    # One cell listing several options ("WFH/ Desk/ On-Field") -> split on "/" or ",".
    if len(parts) == 1 and re.search(r"[,/]", parts[0]) and len(parts[0]) < 300:
        split = [x.strip() for x in re.split(r"\s*[,/]\s*", parts[0]) if x.strip()]
        if len(split) > 1 and all(len(x) < 60 for x in split):
            parts = split
    return parts


def split_options(s):
    return list(dict.fromkeys(options_listed(s)))


def repeated_options(s):
    listed = options_listed(s)
    return [x for x in dict.fromkeys(listed) if listed.count(x) > 1]


def yes_value(v):
    """(bool, extra text or "") for a Yes/No cell. "Yes (Limited to Area & City)" -> (True, "Limited to Area & City")."""
    t = clean(v)
    first = re.split(r"[\s(,;:-]", t.lower(), maxsplit=1)[0] if t else ""
    is_yes = first in YES
    extra = ""
    if t and first in YES | NO:
        extra = t[len(first):].strip(" ()-:;,")
    elif t:
        extra = t
    return is_yes, extra


def raw_rows(ws):
    for i, r in enumerate(ws.iter_rows(values_only=True), 1):
        yield i, list(r)


def find_header(ws, must):
    for i, r in raw_rows(ws):
        low = [header_text(c) for c in r]
        if not any(low):
            continue
        if all(any(m in c for c in low) for m in must):
            return i, r
        if i > 6:
            return None, None
    return None, None


def type_known(t):
    t = t.lower()
    return any(k in t for k in KNOWN_TYPES)


def profile_sheet(ws, warnings):
    hrow, header = find_header(ws, ["fields", "required", "type"])
    cols = header_map(header, PROFILE_COLUMNS)
    for h in unmapped(header, cols):
        warnings.append(f"{ws.title}: column not mapped: \"{h}\"")
    get = lambda r, k: clean(r[cols[k]]) if k in cols and cols[k] < len(r) else ""
    fields, section, started = [], "", False
    for i, r in raw_rows(ws):
        if i <= hrow:
            continue
        cells = [clean(c) for c in r]
        if not any(cells):
            if started:
                break  # end of the field table; anything below is notes
            continue
        first = next((c for c in cells if c), "")
        if started and re.match(r"^\s*(note|notes)\b", first, re.I):
            break
        section = get(r, "section") or section
        raw_title = get(r, "title")
        entry = {"row": i, "section": section, "type": get(r, "type").lower(),
                 "options": split_options(get(r, "options")), "options_raw": get(r, "options"),
                 "dependency": get(r, "dependency"), "map_discovery": get(r, "map_discovery"),
                 "unmask_event": get(r, "unmask_event"), "usage": get(r, "usage"),
                 "bots": get(r, "bots"), "review": get(r, "review")}
        notes = {}
        for k in ("required", "go_live", "on_card", "pii", "masked", "vectorize", "search", "filter"):
            val, extra = yes_value(get(r, k))
            entry[k] = val
            if extra:
                notes[k] = extra
        if "go_live" not in cols:
            entry.pop("go_live")
        if notes:
            entry["cell_notes"] = notes
        if not raw_title and not entry["type"]:
            continue
        started = True
        if entry["type"] and not type_known(entry["type"]):
            warnings.append(f"{ws.title} R{i}: type not recognised: \"{entry['type']}\"")
        for k, extra in notes.items():
            warnings.append(f"{ws.title} R{i}: {k} cell has extra text: \"{extra}\"")
        for x in repeated_options(get(r, "options")):
            warnings.append(f"{ws.title} R{i}: option listed more than once, kept once: \"{x}\"")
        if not raw_title and fields:
            # Blank title: a conditional variant of the field above (e.g. per-qualification sub-dropdowns).
            fields[-1].setdefault("variants", []).append(entry)
            continue
        first_line, _, rest = raw_title.partition("\n")
        entry["title"] = first_line.strip().rstrip("*").strip()
        entry["title_marker"] = first_line.strip()[len(first_line.strip().rstrip("*")):]
        if rest.strip():
            entry["subtitle"] = " ".join(rest.split())
        fields.append(entry)
    if "dependency" not in cols:
        warnings.append(f"{ws.title}: no dependency column found; conditional fields will have no x-show-if")
    return {"sheet": ws.title, "columns": sorted(cols), "fields": fields}


def form_sheet(ws, warnings):
    hrow, header = find_header(ws, ["field name", "data type"])
    cols = header_map(header, FORM_COLUMNS)
    for h in unmapped(header, cols):
        warnings.append(f"{ws.title}: column not mapped: \"{h}\"")
    get = lambda r, k: clean(r[cols[k]]) if k in cols and cols[k] < len(r) else ""
    fields, started = [], False
    for i, r in raw_rows(ws):
        if i <= hrow:
            continue
        cells = [clean(c) for c in r]
        if not any(cells):
            if started:
                break
            continue
        if not get(r, "title"):
            continue
        started = True
        req = get(r, "required")
        fields.append({"row": i, "section": get(r, "section"), "title": get(r, "title"), "help": get(r, "help"),
                       "type": get(r, "type"), "options": split_options(get(r, "options")),
                       "dependency": get(r, "dependency"), "required": req.upper().startswith("Y"),
                       "server_set": "server" in req.lower(), "visibility": get(r, "visibility")})
    return {"sheet": ws.title, "fields": fields}


def interaction_blocks(ws):
    """Layout 1: "User Interaction | Event | Direction" with "A --> B" block rows."""
    out, current = [], None
    for i, r in raw_rows(ws):
        r = [clean(c) for c in r] + ["", "", "", ""]
        a, ev, direction, comment = r[0], r[1], r[2], r[3]
        if a.lower().startswith("user interaction"):
            continue
        if re.search(r"-+>", a):
            src, dst = [s.strip() for s in re.split(r"-+>", a, maxsplit=1)]
            current = {"from": src, "to": dst, "events": []}
            out.append(current)
        elif a and not ev:
            current = None
            continue
        if current is not None and ev:
            current["events"].append({"event": ev, "direction": direction, "comment": comment})
    return out


def interaction_table(ws, hrow, header):
    """Layout 2: flat "Event | Sender | Receiver | Comment" table, grouped per sender -> receiver."""
    h = [header_text(c) for c in header]
    idx = lambda *names: next((i for i, t in enumerate(h) if any(n == t or t.startswith(n) for n in names)), None)
    ce, cs, cr, cc = idx("event", "action"), idx("sender", "from"), idx("receiver", "to"), idx("comment", "notes")
    groups = {}
    for i, r in raw_rows(ws):
        if i <= hrow:
            continue
        r = [clean(c) for c in r]
        get = lambda c: r[c] if c is not None and c < len(r) else ""
        ev, s, t = get(ce), get(cs), get(cr)
        if not (ev and s and t):
            continue
        groups.setdefault((s, t), {"from": s, "to": t, "events": []})["events"].append(
            {"event": ev, "direction": f"{s} --> {t}", "comment": get(cc)})
    return list(groups.values())


def domains_sheet(ws):
    out, block = [], None
    for i, r in raw_rows(ws):
        r = [clean(c) for c in r] + ["", "", ""]
        a, b, c = r[0], r[1], r[2]
        if not (a or b or c):
            continue
        looks_url = lambda x: x.startswith("http") or re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", x or "")
        if a and not looks_url(b) and not looks_url(c):
            block = {"instance": a, "links": []}
            out.append(block)
        elif (b or c):
            if block is None:
                block = {"instance": "", "links": []}
                out.append(block)
            block["links"].append({"role": a, "production": b, "uat": c})
    return [b for b in out if b["links"]]


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    out_path = args[args.index("-o") + 1] if "-o" in args else None
    wb = openpyxl.load_workbook(args[0], data_only=True)
    warnings = []
    spec = {"workbook": args[0], "profiles": [], "forms": [], "interactions": [], "domains": [],
            "skipped_sheets": [], "warnings": warnings}
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            spec["skipped_sheets"].append(f"{ws.title} (hidden)")
            continue
        if ws.title.strip().lower() == "domains":
            spec["domains"] = domains_sheet(ws)
            continue
        if find_header(ws, ["fields", "required", "type"])[0]:
            spec["profiles"].append(profile_sheet(ws, warnings))
            continue
        if find_header(ws, ["field name", "data type"])[0]:
            spec["forms"].append(form_sheet(ws, warnings))
            continue
        if find_header(ws, ["user interaction", "event"])[0]:
            spec["interactions"] += interaction_blocks(ws)
            continue
        hrow, header = find_header(ws, ["event"])
        if hrow and any(t in [header_text(c) for c in header] for t in ("sender", "from", "receiver", "to")):
            spec["interactions"] += interaction_table(ws, hrow, header)
            continue
        spec["skipped_sheets"].append(f"{ws.title} (unrecognised format)")
        warnings.append(f"{ws.title}: sheet not recognised; nothing extracted from it")
    text = json.dumps(spec, indent=2, ensure_ascii=False)
    if out_path:
        open(out_path, "w").write(text + "\n")
        summary = {p["sheet"]: len(p["fields"]) for p in spec["profiles"]}
        summary.update({f["sheet"]: len(f["fields"]) for f in spec["forms"]})
        print(json.dumps({"written": out_path, "fields": summary,
                          "interactions": sum(len(x["events"]) for x in spec["interactions"]),
                          "domains": len(spec["domains"]), "skipped": spec["skipped_sheets"],
                          "warnings": warnings}, indent=2, ensure_ascii=False))
    else:
        print(text)


if __name__ == "__main__":
    main()
