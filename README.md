# bluedots-claude-plugins

Claude Code plugins for Blue Dots integrators.

## bluedots-schema-tools

Turns a Blue Dots schema workbook (Excel) into the files a Signals deployment reads:

- `network.json` (domains, fields, interactions)
- aggregator registration forms (`org-registration.v1.json`, `registration.v1.json` and their `.ui.json`)

Claude reads the workbook, generates the files and checks them without a questionnaire: unclear rows are resolved with safe defaults, and every assumption is written to `decisions.md` for you to review.

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

Python 3 with `openpyxl`:

```
python3 -m pip install openpyxl
```

### Use

Ask Claude, for example: "Convert `my-schema.xlsx` into network.json and the aggregator forms", or run `/bluedots-schema-tools:schema-from-sheet`.

Your workbook stays on your machine. Don't commit workbooks to any repo: their hidden sheets often contain sample personal data.

### Updates

`/plugin marketplace update bluedots-claude-plugins`

## Status

Early version (0.1.0): extraction, comparison and checks are scripted; file generation is guided by Claude. A deterministic generator is planned.
