---
name: schema-from-sheet
description: Turn a Blue Dots schema workbook (Excel) into a network.json and the aggregator registration form schemas. Use when the user gives a schema .xlsx (profile sheets per domain, aggregator owner/coordinator sheets, interaction rules) and wants the Blue Dots / Signals schema files created or updated, or wants to compare the workbook with a network.json they already have.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/*.py *)
compatibility: Requires Python 3.9 or newer (tested on 3.9 and 3.14) and the openpyxl package (3.1+), installed automatically if missing.
---

# Schema from sheet

Turns a programme's schema workbook into the files a Blue Dots (Signals) deployment reads:

- `network.json`: domains, item schemas (fields), interactions
- aggregator registration forms: `org-registration.v1.json` + `.ui.json` (organisation / owner) and `registration.v1.json` + `.ui.json` (coordinator)

**The files are written by scripts, never by hand.** `build.py` combines the workbook (`.spec.json`), the human choices (`decisions.json`) and the reference templates in `references/` (structure taken from a deployed network), so the output always has the structure Signals and the aggregator portal read, and the same inputs always give the same files. Your job is to fill in `decisions.json`, not to write JSON schemas.

Scripts: `${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/` (written `$S` below).

## Don't ask: decide and report

Integrators should get files, not a questionnaire. Don't ask questions; resolve every TODO with the defaults below, write what you decided in `decisions.md`, and list the main assumptions at the end. Stop to ask only if the workbook can't be read.

## Steps

1. **Check Python** (yourself, no questions):
   - `python3 --version` must be **3.9+** (Windows: `py -3`). Missing or older: tell the user to install Python 3.9+ from python.org; don't install system software.
   - `python3 -c "import openpyxl"`. If missing, try in order: `python3 -m pip install -r ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/requirements.txt`, the same with `--user`, then a venv in the output folder (`python3 -m venv <out>/.venv`, run the scripts with `<out>/.venv/bin/python`). If all fail, say installs are blocked.

2. **Extract**:
   ```bash
   python3 $S/extract_sheet.py "<workbook.xlsx>" -o <out>/.spec.json
   ```
   Its `warnings` (unmapped columns, unknown types, Yes/No cells with extra text, unrecognised sheets) go into `decisions.md`.

3. **Draft decisions**:
   - **Existing network** (the user has a `network.json` for this network, or the workbook is a newer version of a deployed schema): pass it, plus their four aggregator form files if they have them. Keys, titles, settings and everything the sheet doesn't define are kept; only real differences become TODOs.
     ```bash
     python3 $S/init_decisions.py <out>/.spec.json -o <out>/decisions.json --existing <their network.json> [--existing-forms <folder with the 4 form files>]
     ```
   - **New network**:
     ```bash
     python3 $S/init_decisions.py <out>/.spec.json -o <out>/decisions.json [--network-id <id>] [--display-name "<name>"]
     ```

4. **Resolve the TODOs** in `decisions.json` (its `todo` list), by editing `decisions.json` only:
   - per field (`domains[].fields[]`, by sheet `row`): `key`, `title` (short label, 2–4 words), `description` (the sheet's question), `set` / `unset` (property attributes), `required` (true/false), `skip`, or `property` (a full property, e.g. an upload row kept as a URL field)
   - per domain: `id`, `layout` (`x-form-layout`), `card`, `contact_fields`, `settings` (domain-level keys), `extra_properties` (fields with no sheet row), `required`, `order`
   - network: `id`, `display_name`, `description`, `instance_url` / `instances`
   - forms: `forms` (a JSON merge patch per form file, e.g. option labels) or `forms_full`

   Defaults when unsure: keep the existing value; for a new network keep what the rules produced. Pairings "matched by elimination / fuzzy" are usually right; confirm by reading both titles. Note each resolution in `decisions.md` (one line: row, field, decision, why).

5. **Build**:
   ```bash
   python3 $S/build.py <out>/.spec.json <out>/decisions.json <out>
   ```

6. **Check** (must print `0 problem(s)`; otherwise fix `decisions.json` and rebuild):
   ```bash
   python3 $S/check_schema.py <out>/network.json <out>
   ```
   It mirrors Signals' network config validation and the portal's form keys, plus: no private+vectorize field, no dangling `x-show-if` / `allOf` / card / layout references, `enum`/`enumNames` lengths, a primary map location per domain.

7. **Report** (short): files written, field counts per domain, check result, top assumptions from `decisions.md`.

8. **Clean up**: delete `<out>/.spec.json` (and `<out>/.venv`). Keep `decisions.json`: with it the files can be regenerated after a workbook update.

**Compare only** (the user just wants the differences): run step 2, then `python3 $S/diff_network.py <out>/.spec.json <their network.json>`, report, delete `.spec.json`. Never edit their file.

## What the rules do (build.py), for reading decisions

| Sheet | network.json |
|---|---|
| Fields | `title`; a question goes in `description` with a short `title` (decisions) |
| Required = Yes | in `required`; strings get `minLength: 1`, arrays `minItems: 1` |
| Required + Depends On | not in `required`; `x-show-if` plus an `allOf` if/then rule |
| Depends On ("visible only if category is RCI", "X = a") | `x-show-if: {<parent key>: [<value>]}` |
| Type string / free text | `"type": "string"` |
| number (phone / mobile in the title) | `"type": "string", "pattern": "^[0-9]{10}$"` |
| number (other) | `"type": "integer"` |
| email / url | `format: email` / `x-uri: true, maxLength: 2048` |
| dropdown / single select | `"type": "string", "enum": [...]` |
| array selection / array / multi select | `"type": "array", "items": {"enum": [...]}` |
| dropdown with search | `x-reference-source` |
| geo / geo, array | `location`: the sheet's "primary", else the first location field per domain is `primary`, the rest `secondary` |
| upload | skipped, unless decisions map it to a field (e.g. a catalog URL) |
| PII = Yes | `private: true` (PII wins over Vectorise: never both) |
| Vectorise = Yes | `vectorize: true` (not on numbers, locations or PII) |
| Search / Filter Field | no marker: every declared non-private field is searchable and filterable |
| Interaction rules | `actions.connect.interactions` with the reference event schema, statuses and `reveals_pii_on_status: ["accepted","completed"]` |
| Domain settings, status rules, dashboard, instances | `references/network.template.json` (or the existing network) |
| Aggregator forms | `references/aggregator/` (the keys the portal's code reads); changes via `decisions.forms` |

## Accuracy

`tests/run_golden.py` rebuilds the Purple Dots (ALIMCO) schema from its Oct 2026 workbook and must match the deployed reference exactly (5/5 files); create mode must pass `check_schema.py`. Run it after any change to the scripts.
