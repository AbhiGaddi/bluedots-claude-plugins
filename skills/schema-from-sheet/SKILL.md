---
name: schema-from-sheet
description: Turn a Blue Dots schema workbook (Excel) into a network.json and the aggregator registration form schemas. Use when the user gives a schema .xlsx (profile sheets per domain, aggregator owner/coordinator sheets, interaction rules) and wants the Blue Dots / Signals schema files created, or wants to compare the workbook with a network.json they already have.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/*.py *)
---

# Schema from sheet

Converts a programme's schema workbook into the files a Blue Dots (Signals) deployment reads:

- `network.json`: domains, item schemas (fields), interactions
- aggregator registration forms: `org-registration.v1.json` + `org-registration.v1.ui.json` (organisation / owner) and `registration.v1.json` + `registration.v1.ui.json` (coordinator)

Workbooks are written by people: rows carry review notes ("Needs Review: …"), options sometimes sit in one comma- or slash-separated cell, and conditional sub-fields appear as rows with a blank field name. The scripts extract and check; you apply the defaults and rules below and **record every judgement call in `decisions.md`** rather than asking.

Scripts live in `${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/`.

## Don't ask: decide and report

Integrators should get files, not a questionnaire. Do **not** ask questions before or during generation. Apply the defaults below, record every assumption in `<output>/decisions.md`, and finish with a short list of the assumptions the user may want to change. Only stop to ask if the workbook can't be read at all.

| Needed | Default (no question) |
|---|---|
| Mode | **Create**. Use compare mode only if the user explicitly gives an existing `network.json` to compare with |
| Network id / display name | From the user's request if given; else from the workbook name (e.g. `Blue Dots Schema …` → `blue_dot`, "Blue Dot") |
| Domain per profile sheet | `*Seeker*` → `seeker`, `*JobProvider*` → `provider`, `*ServiceProvider*` → `service_provider`; otherwise snake_case of the sheet name without `_Profile_Schema` |
| Instance API URL | `http://localhost:2742` (local), noted in decisions |
| Output folder | `./schema-output/<network>/` |
| Field keys | camelCase of the title (first line of the cell), unique per schema |
| "Needs Review" rows | Resolve with the fixed rules (PII wins; no vectorize on numbers, amounts, counts or locations; upload skipped). Otherwise keep the sheet's own values. Note each one in decisions |
| Options in one cell | Already split by the extractor on `/` or `,`; noted in decisions |
| Non-literal options ("State-specific trade list", "Dropdown of … colleges", notes) | Free-text field (`"type": "string"`), or `x-reference-source` for a college/institution search; noted in decisions |
| Filter Field = Yes | Not emitted (only works on Signals builds with schema-driven filters); listed in decisions as "filterable candidates" |
| Upload fields | Skipped; noted |

Never write outside the output folder. Never copy rows from hidden sheets (they usually hold sample personal data).

## Steps

1. **Check Python**: `python3 -c "import openpyxl"`. If missing, install it: `python3 -m pip install -r ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/requirements.txt`.

2. **Extract**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/extract_sheet.py "<workbook.xlsx>" -o <output>/spec.json
   ```

3. **Generate** `network.json`, `org-registration.v1.json` + `.ui.json`, `registration.v1.json` + `.ui.json` in the output folder using the defaults above and the mapping below. Write `<output>/decisions.md`: one line per assumption (row, field, what was decided, why).

4. **Check**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/check_schema.py <output>/network.json
   ```
   Fix anything it reports and re-run until 0 problems. Confirm every aggregator form field is in its `.ui.json` `ui:order`.

5. **Report** (short): files written, field counts per domain, check result, and the top assumptions from `decisions.md` the user may want to change. The user edits `decisions.md` or replies with corrections; then regenerate.

**Compare mode** (only when the user supplies a `network.json` to compare with): run
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/diff_network.py <output>/spec.json <their-network.json> [SheetName=domain ...]
```
and report `CHANGED` / `NEW` / `ORPHAN` / `SKIP`. Read-only: never edit their file.

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
| **Options** | `enum`, split on `;` or newline (single cells split on `/` or `,` by the extractor) |
| An option named **Other** | add a companion free-text `<key>Other` with `x-show-if: {<key>: ["Other"]}` |
| **Dependency** "Shown if X = 'a' or 'b'" | `"x-show-if": {"<xKey>": ["a", "b"]}` |
| **PII Field** = Yes | `"private": true` |
| **Unmask event** ("… → Connection Request Accepted") | the interaction's `reveals_pii_on_status`, e.g. `["accepted"]` |
| **Vectorise** = Yes | `"vectorize": true`; `vector_weight: 2` for the main matching field (e.g. job roles) |
| **Search Field** = Yes | no marker: text search covers every non-private field, ranked search follows `vectorize` |
| **Filter Field** = Yes | not emitted by default; listed in `decisions.md` as filterable candidates |
| **Displayed on card** = Yes | domain `card.default_fields` |
| **How it's used / In the bots** | not stored; context only |

## Fixed rules (apply; list them in decisions.md)

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
