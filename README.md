# bluedots-claude-plugins

Claude Code plugins for Blue Dots integrators.

## bluedots-schema-tools

Turns a Blue Dots schema workbook (Excel) into the files a Signals deployment reads:

- `network.json` (domains, fields, interactions)
- aggregator registration forms (`org-registration.v1.json`, `registration.v1.json` and their `.ui.json`)

Claude reads the workbook, asks you about every row marked "Needs Review" or otherwise unclear, generates the files, and checks them.

### Install

In Claude Code:

```
/plugin marketplace add AbhiGaddi/bluedots-claude-plugins
/plugin install bluedots-schema-tools@bluedots-claude-plugins
```

Requires Python 3 with `openpyxl` (`python3 -m pip install openpyxl`).

### Use

Ask Claude, for example: "Convert `my-schema.xlsx` into network.json and the aggregator forms", or run `/bluedots-schema-tools:schema-from-sheet`.

Your workbook stays on your machine. Don't commit workbooks to any repo: their hidden sheets often contain sample personal data.

### Updates

`/plugin marketplace update bluedots-claude-plugins`

## Status

Early version (0.1.0): extraction, comparison and checks are scripted; file generation is guided by Claude. A deterministic generator is planned.
