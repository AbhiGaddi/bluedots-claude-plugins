# bluedots-claude-plugins

Tools for Claude Code that help you set up a Blue Dots network.

## What it does

You describe your network in an Excel workbook: who uses it (for example job seekers and job providers), what each of them fills in, and who can connect with whom.

This tool reads that workbook and creates the files Blue Dots needs:

- **`network.json`**: the profile form for each type of user, and who can connect with whom
- **four registration form files**: the sign-up forms for organisations and their coordinators, built from the workbook's Aggregator Owner and Coordinator sheets
- **`aggregator.config.yaml`**: the aggregator portal's config for the network (who the login person is in each domain, and the domain names shown in the portal)
- **`deployments.env`**: if the workbook lists deployments (Domains sheet), the settings each one needs: which domains it serves and the app links

You don't need to write any JSON. Claude reads the workbook, makes the small decisions the sheet leaves open (such as short labels for long questions), builds the files and checks them. Every decision it made is listed in `decisions.md` so you can review it.

## What you need

- **Claude Code**: in the terminal, VS Code, a JetBrains IDE, or the Code tab of Claude Desktop
- **Python 3.9 or newer**: if you don't have it, get it from [python.org](https://www.python.org/downloads/). Claude installs anything else it needs.

## Install

Pick **one** of these.

**Option 1: as a plugin (recommended)**

In Claude Code, type:

```
/plugin marketplace add AbhiGaddi/bluedots-claude-plugins
/plugin install bluedots-schema-tools@bluedots-claude-plugins
```

In VS Code you can also do this from the menu: type `/plugins`, add `AbhiGaddi/bluedots-claude-plugins` under **Marketplaces**, then install **bluedots-schema-tools** under **Plugins**.

**Option 2: from a zip file**

1. Download the zip from the [latest release](https://github.com/AbhiGaddi/bluedots-claude-plugins/releases/latest).
2. Unzip it into the `.claude/skills/` folder in your home folder.
3. Restart Claude Code.

## Use

Ask Claude in plain words, for example:

> Convert `my-schema.xlsx` into network.json and the aggregator forms

You get a folder with these files, plus `decisions.md` (what Claude decided and why) and `decisions.json` (lets you rebuild the files after you change the workbook).

**Keep your workbook private.** Don't upload it to GitHub or any shared folder: workbooks often have hidden sheets with real people's details.

## Update

- **Plugin:** type `/plugin marketplace update bluedots-claude-plugins`, then `/reload-plugins`.
- **Zip:** delete the old `schema-from-sheet` folder and unzip the new release.

## Not supported yet

Claude Desktop chat and claude.ai. The tool runs small Python scripts on your computer, which only Claude Code can do.

---

## For developers

The files are built by scripts in `skills/schema-from-sheet/scripts/`, so the same workbook always gives the same files. Before a release, run:

```
python3 skills/schema-from-sheet/tests/run_golden.py
python3 tests/test_package.py
```

The first rebuilds two real networks, Purple Dots (ALIMCO) and Blue Dots, from their workbooks and checks every file matches. The second builds the zip (`python3 tools/package_skill.py` makes it for the release) and checks it works on its own.

Current version: **0.3.3**. See [releases](https://github.com/AbhiGaddi/bluedots-claude-plugins/releases) for what changed.
