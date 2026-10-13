---
name: schema-from-sheet
description: Turn a Blue Dots schema workbook (Excel) into a network.json and the aggregator registration form schemas. Use when the user gives a schema .xlsx (profile sheets per domain, aggregator owner/coordinator sheets, interaction rules) and wants the Blue Dots / Signals schema files created, or wants to compare the workbook with a network.json they already have.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/*.py *)
---

# Schema from sheet

Converts a programme's schema workbook into the files a Blue Dots (Signals) deployment reads:

- `network.json`: domains, item schemas (fields), interactions
- aggregator registration forms: `org-registration.v1.json` + `org-registration.v1.ui.json` (organisation / owner) and `registration.v1.json` + `registration.v1.ui.json` (coordinator)

Workbooks are written by people: rows carry review notes ("Needs Review: …"), options sometimes sit in one comma- or slash-separated cell, and conditional sub-fields appear as rows with a blank field name. The scripts extract and check; **you** make the judgement calls and **ask the user** about every ambiguous or "Needs Review" row. Never resolve one silently.

Scripts live in `${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/`.

## Before starting

1. Check Python 3 and openpyxl: `python3 -c "import openpyxl"`. If missing: `python3 -m pip install -r ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/requirements.txt`.
2. Ask which mode:
   - **Create** (normal): build new files from the workbook.
   - **Compare**: the user already has a `network.json` and wants to see how the workbook differs. Read-only: report, don't edit.
3. Ask for what the workbook doesn't hold: network id (e.g. `blue_dot`), display name, domain ids per profile sheet (defaults: `*Seeker*` → `seeker`, `*JobProvider*` → `provider`, `*ServiceProvider*` → `service_provider`), and the output folder (default `./schema-output/<network>/<instance>/`).
4. Never write outside the output folder the user named. Never copy rows from hidden sheets: they usually hold sample personal data.

## Steps

1. **Extract** (local, read-only):
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/extract_sheet.py "<workbook.xlsx>" -o <output>/spec.json
   ```
   Prints field counts per sheet, interaction blocks and skipped (hidden) sheets. Show the counts to the user and confirm they match the workbook.

2. **List the decisions.** From `spec.json`, collect for the user:
   - every row with a "Needs Review" note
   - rule conflicts (e.g. PII + Vectorise, see Fixed rules)
   - options that need splitting or are not literal options ("State-specific trade list", "Dropdown of colleges")
   - unsupported types (upload)
   - field keys: propose camelCase keys from the titles and confirm
   Ask them in one go, numbered, and wait for answers.

3. **Generate** the files in the output folder using the mapping below. Keep 2-space indentation.

4. **Check**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/check_schema.py <output>/network.json
   ```
   Must report 0 problems. Also confirm every aggregator form field appears in its `.ui.json` `ui:order`.

5. **Report**: files written, decisions taken, anything still open. Suggest the user loads the files in a local Signals / aggregator setup and opens each profile form and registration form before using them.

**Compare mode** replaces steps 2–4 with:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/diff_network.py <output>/spec.json <their-network.json> [SheetName=domain ...]
```
It prints per field: `same`, `CHANGED` (required, private, vectorize, filterable, enum, missing `x-show-if`), `NEW`, `ORPHAN` (in the JSON, no sheet row), `SKIP` (unsupported). A `NEW` + `ORPHAN` pair with a similar title is usually a label rename. Report; don't edit their file.

## Mapping: profile sheets → `domains[].item_schemas.<type>.properties`

| Sheet column | network.json |
|---|---|
| **Framework** (WHO I AM / WHAT I HAVE / WHAT I WANT) | `x-form-layout.sections[]` (section title + field order) |
| **Fields** | `title` (strip trailing `*`). A second line in the cell becomes `description` |
| **Required** = Yes | key in the schema's `required` array |
| **Type** `string` / `free text` | `"type": "string"` (`minLength: 1` if required) |
| **Type** `number` | `integer` for counts/age (with `minimum`/`maximum`); a phone number stays `string` with a `pattern` and `x-error-message` |
| **Type** `email` | `"type": "string", "format": "email"` |
| **Type** `url` | `"type": "string", "x-uri": true` |
| **Type** `dropdown` | `"type": "string", "enum": [...]` |
| **Type** `array selection` / `array` | `"type": "array", "items": {"type": "string", "enum": [...]}, "uniqueItems": true` |
| **Type** `conditional dropdown` (+ blank-title rows below) | one property per variant, each with its own `enum` and `x-show-if` |
| **Type** `dropdown with search` | `x-reference-source` (e.g. `{"source": "colleges"}`) instead of an inline enum |
| **Type** `geo` | `"type": "string", "location": "primary"` for the map pin ("Map Discovery" column), else `"secondary"` |
| **Type** `upload` | not supported: flag it, don't create a field |
| Min/Max amount fields | `"type": "number", "minimum": 0` |
| **Options** | `enum`, split on `;` or newline; confirm splits of `,` / `/` cells |
| An option named **Other** | add a companion free-text `<key>Other` with `x-show-if: {<key>: ["Other"]}` |
| **Dependency** "Shown if X = 'a' or 'b'" | `"x-show-if": {"<xKey>": ["a", "b"]}` |
| **PII Field** = Yes | `"private": true` |
| **Unmask event** ("… → Connection Request Accepted") | the interaction's `reveals_pii_on_status`, e.g. `["accepted"]` |
| **Vectorise** = Yes | `"vectorize": true`; `vector_weight: 2` for the main matching field (e.g. job roles) |
| **Search Field** = Yes | no marker: text search covers every non-private field, ranked search follows `vectorize` |
| **Filter Field** = Yes | `"filterable": true` only if the user's Signals version supports schema-driven filters; ask |
| **Displayed on card** = Yes | domain `card.default_fields` |
| **How it's used / In the bots** | not stored; context only |

## Fixed rules (apply, don't ask; list them in the report)

- **PII wins over Vectorise.** A field marked both is `private: true` with no `vectorize`. Private values are stored masked, so there is nothing to embed, and the search indexer would skip every item of that type.
- Numbers and locations are never vectorized.
- Server-set fields (consent timestamps) are not form fields.

## Other sheets

- **Interaction rules** → `actions`. Each `A --> B` block is an interaction (`from_domain`, `to_domain`). `Apply` → action `apply`, `Connect` → `connect`. Status values: Connect/Apply → `created`, Accept/Shortlist → `accepted`, Reject → `rejected`, Cancel → `cancelled`.
- **Aggregator Owner sheet** → `org-registration.v1.json` (+ `.ui.json`); **Aggregator Coordinator sheet** → `registration.v1.json` (+ `.ui.json`).
  - `Text (min 2, max 200 chars)` → `minLength`/`maxLength`; `URI` → `"format": "uri"`; email → `"format": "email"`; phone → `pattern`.
  - Enum / array selection → snake_case `enum` values with readable `enumNames`.
  - Dependency → `x-show-if`. Boolean consent → a `consent` object with a required `value`.
  - Every field must appear in the `.ui.json` `ui:order`, or the form won't show it.
- **Domains / URLs sheet** → informational only (web URLs); not the API `instance_url`.
