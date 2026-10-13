# bluedots-claude-plugins

Claude Code plugins for Blue Dots integrators.

## bluedots-schema-tools

Turns a Blue Dots schema workbook (Excel) into the files a Signals deployment reads:

- `network.json` (domains, fields, interactions)
- aggregator registration forms (`org-registration.v1.json`, `registration.v1.json` and their `.ui.json`)

Claude reads the workbook, drafts the decisions (keys, short titles, anything the sheet leaves open), builds the files with a script and checks them: no questionnaire, and every assumption is written to `decisions.md` for you to review.

### Install

Works wherever Claude Code runs. Install once per machine; a plugin installed in one place (for example the terminal) shows up in the others.

**Terminal (Claude Code CLI)**

```
/plugin marketplace add AbhiGaddi/bluedots-claude-plugins
/plugin install bluedots-schema-tools@bluedots-claude-plugins
```

**VS Code (Claude Code extension)**

1. In the Claude panel, type `/plugins` to open **Manage plugins**.
2. **Marketplaces** tab → add `AbhiGaddi/bluedots-claude-plugins`.
3. **Plugins** tab → install **bluedots-schema-tools**.

**JetBrains IDEs**

Run Claude in the IDE terminal and use the same two `/plugin` commands as the terminal.

**Claude Desktop: Code tab (local sessions)**

Click **+** next to the prompt → **Plugins → Add plugin** → choose **bluedots-schema-tools**. If the marketplace isn't listed, add it once from the terminal or VS Code (steps above). Not available in cloud or WSL sessions.

**Claude Desktop chat / claude.ai**

Not supported yet. The skill runs local Python scripts, which chat can't run reliably today. Use one of the Claude Code options above.

**Requirements**

Python **3.9 or newer** (tested on 3.9 and 3.14). Claude checks the version and installs the `openpyxl` library automatically the first time if it's missing. If your machine has no Python 3, install it from [python.org](https://www.python.org/downloads/).

### Use

Ask Claude, for example: "Convert `my-schema.xlsx` into network.json and the aggregator forms", or run `/bluedots-schema-tools:schema-from-sheet`.

Your workbook stays on your machine. Don't commit workbooks to any repo: their hidden sheets often contain sample personal data.

### Updates

`/plugin marketplace update bluedots-claude-plugins`

## Accuracy

`skills/schema-from-sheet/tests/run_golden.py` rebuilds the Purple Dots (ALIMCO) schema from its Oct 2026 workbook. All five files (`network.json` and the four aggregator forms) must match the deployed reference exactly, and a brand-new network built from the same workbook must pass the structural check (`check_schema.py`, mirroring what Signals and the aggregator portal read). Run it before every release:

```
python3 skills/schema-from-sheet/tests/run_golden.py
```

## Status

Version 0.3.0: files are built by a script (`build.py`) from the workbook, a `decisions.json` and reference templates, so the same inputs always give the same, valid files.
