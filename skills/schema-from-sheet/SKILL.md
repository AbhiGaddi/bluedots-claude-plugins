---
name: schema-from-sheet
description: Turn a Blue Dots schema workbook (Excel) into a network.json and the aggregator registration form schemas. Use when the user gives a schema .xlsx (profile sheets per domain, aggregator owner/coordinator sheets, interaction rules) and wants the Blue Dots / Signals schema files created, or wants to compare the workbook with a network.json they already have.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/*.py *)
compatibility: Requires Python 3.9 or newer (tested on 3.9 and 3.14) and the openpyxl package (3.1+), installed automatically if missing.
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
| Mode | **Create**. If a `network.json` for the **same network** already exists (the user mentions one, or the workbook is a later version of a deployed schema), it's an update: run compare first, then **reuse its keys, domain ids, titles and domain settings** and change only what the sheet changes. New keys would orphan every stored profile. Compare-only when the user just wants the differences |
| Network id / display name | From the user's request if given; else from the workbook name (e.g. `Blue Dots Schema …` → `blue_dot`, "Blue Dot") |
| Domain per profile sheet | Existing network's domain ids first (e.g. a Service Provider sheet → `provider` if that's what the network uses). Otherwise `*Seeker*` → `seeker`, `*JobProvider*` → `provider`, `*ServiceProvider*` → `service_provider`, else snake_case of the sheet name |
| Instance API URL | `http://localhost:2742` (local), noted in decisions |
| Output folder | `./schema-output/<network>/` |
| Field keys | Existing key when the field already exists (matched by title, description or key). New fields: follow the existing network's key style (snake_case or camelCase); for a brand-new network, camelCase of the short title |
| "Needs Review" rows | Resolve with the fixed rules (PII wins; no vectorize on numbers, amounts, counts or locations; upload skipped). Otherwise keep the sheet's own values. Note each one in decisions |
| Options in one cell | Already split by the extractor on `/` or `,`; noted in decisions |
| Non-literal options ("State-specific trade list", "Dropdown of … colleges", notes) | Free-text field (`"type": "string"`), or `x-reference-source` for a college/institution search; noted in decisions |
| Filter Field = Yes | Nothing to write: Signals makes every declared, non-private field filterable. If the field is PII, note that it can never be filtered |
| Upload fields | Skipped; noted |

Never write outside the output folder. Never copy rows from hidden sheets (they usually hold sample personal data).

## Steps

1. **Check Python** (do this yourself; don't ask the user):
   - `python3 --version` must be **3.9 or newer** (tested on 3.9 and 3.14). On Windows try `py -3 --version` and use `py -3` instead of `python3` below.
   - No Python 3, or older than 3.9: stop and tell the user to install Python 3.9+ from python.org (or their package manager). Don't install system software yourself.
   - `python3 -c "import openpyxl"`. If missing, install it, trying in order until one works:
     1. `python3 -m pip install -r ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/requirements.txt`
     2. same with `--user` (for "externally-managed-environment" errors on newer macOS/Linux)
     3. a virtual environment in the output folder: `python3 -m venv <output>/.venv` then `<output>/.venv/bin/pip install openpyxl`, and run the scripts with `<output>/.venv/bin/python` instead of `python3`
   - If all three fail (e.g. a locked-down machine), tell the user installs are blocked and that `openpyxl` is needed.

2. **Extract** (its summary lists `warnings`: unmapped columns, unrecognised types, Yes/No cells with extra text, unrecognised sheets; carry every one into `decisions.md`):
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/extract_sheet.py "<workbook.xlsx>" -o <output>/.spec.json
   ```

3. **Generate** `network.json`, `org-registration.v1.json` + `.ui.json`, `registration.v1.json` + `.ui.json` in the output folder using the defaults above and the mapping below. Write `<output>/decisions.md`: one line per assumption (row, field, what was decided, why).

4. **Check**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/check_schema.py <output>/network.json
   ```
   Fix anything it reports and re-run until 0 problems. Confirm every aggregator form field is in its `.ui.json` `ui:order`.

5. **Report** (short): files written, field counts per domain, check result, and the top assumptions from `decisions.md` the user may want to change. The user edits `decisions.md` or replies with corrections; then regenerate.

6. **Clean up**: delete `<output>/.spec.json` (and `<output>/.venv` if you created one). It's only a working copy of the workbook; the output folder should end with just the schema files and `decisions.md`.

**Compare mode** (only when the user supplies a `network.json` to compare with): run
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/schema-from-sheet/scripts/diff_network.py <output>/.spec.json <their-network.json> [SheetName=domain ...]
```
and report `CHANGED` / `NEW` / `ORPHAN` / `SKIP`, then delete `<output>/.spec.json`. Read-only: never edit their file.

## Mapping: profile sheets → `domains[].item_schemas.<type>.properties`

| Sheet column | network.json |
|---|---|
| **Framework** (WHO I AM / WHAT I HAVE / WHAT I WANT) | `x-form-layout.sections[]` (section title + field order) |
| **Fields** | Short label as `title` (2–4 words, e.g. "Looking For", "Address"); the sheet's question text goes in `description` ("What are you looking for?"). Reuse an existing field's title. Strip trailing `*` |
| **Required** = Yes | key in the schema's `required` array (Signals uses `required` as the go-live check; drafts can be saved incomplete) |
| **Fields required to change profile status to live** (when the sheet has this column) | This column decides `required`. Fields marked only in "Required" are noted in decisions |
| **Required** + **Depends On** (required only when shown, e.g. CRR Number when category = RCI) | Not in top-level `required`. Add `x-show-if` for the form **and** an `allOf` rule for the API: `{"if": {"properties": {"<parent>": {"const": "<value>"}}, "required": ["<parent>"]}, "then": {"required": ["<child>"]}}` |
| **Type** `string` / `free text` / `free-text` | `"type": "string"` (`minLength: 1` if required) |
| **Type** `number` | `integer` for counts/age (with `minimum`/`maximum`); a phone number stays `string` with a `pattern` and `x-error-message` |
| **Type** `email` | `"type": "string", "format": "email"` |
| **Type** `url` | `"type": "string", "x-uri": true` |
| **Type** `dropdown` / `single select` | `"type": "string", "enum": [...]` |
| **Type** `array selection` / `array` | `"type": "array", "items": {"type": "string", "enum": [...]}, "uniqueItems": true` |
| **Type** `conditional dropdown` (+ blank-title rows below) | one property per variant, each with its own `enum` and `x-show-if` |
| **Type** `dropdown with search` | `x-reference-source` (e.g. `{"source": "colleges"}`) instead of an inline enum |
| **Type** `geo` | `"type": "string", "location": "primary"` for the map pin ("Map Discovery" column), else `"secondary"` |
| **Type** `geo, array` (several places, e.g. service cities) | `"type": "array", "items": {"type": "string"}`, no `location` marker; noted in decisions |
| **Type** `upload` | not supported: flag it, don't create a field |
| Min/Max amount fields | `"type": "number", "minimum": 0` |
| **Options** | `enum`, split on `;` or newline (single cells split on `/` or `,` by the extractor). When updating an existing network, keep each existing enum value's exact spelling: a sheet value that differs only in quotes, case or punctuation ("Parkinson’s" vs "Parkinson's") must not replace it |
| An option named **Other** | add a companion free-text `<key>Other` with `x-show-if: {<key>: ["Other"]}` |
| **Dependency** "Shown if X = 'a' or 'b'" | `"x-show-if": {"<xKey>": ["a", "b"]}` |
| **PII Field** = Yes | `"private": true` |
| **Unmask event** ("… → Connection Request Accepted") | the interaction's `reveals_pii_on_status`, e.g. `["accepted"]` |
| **Vectorise** = Yes | `"vectorize": true`; `vector_weight: 2` for the main matching field (e.g. job roles) |
| **Search Field** = Yes | no marker: text search covers every non-private field, ranked search follows `vectorize`. Extra text in the cell ("Yes (Limited to Area & City)") goes to decisions |
| **Filter Field** = Yes | no marker (every declared non-private field is filterable). On a PII field: note it can't be filtered |
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
