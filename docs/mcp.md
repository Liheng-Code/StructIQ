# StructIQ read-only MCP server

Lets an MCP client (Claude Code, Claude Desktop, Cline, ...) read StructIQ. It is **read-only**: no tool writes a file,
approves, issues or changes a check result. Ported from the SDSA project and reworked for StructIQ's layout.

## What it serves
- `repo/...`: this repository (skills, docs, config examples, templates, source).
- `brain/...`: the Core Brain on Google Drive (`core_brain` in `config/paths.yaml`). If it cannot be read, `get_core_brain_rules`
  returns an error; there is no fallback to rules from memory.
- Project design bases are **validated, not served** (`list_design_bases`, `validate_design_basis`). Other project files
  (drawings, notes, client data) are never served.
- Never served: `config/paths.yaml` (this machine's local config), `.git`, caches, virtual environments, `.env*`, binary files.

## Tools
`get_core_brain_rules`, `list_skills`, `get_skill_context`, `read_project_file`, `list_project_files`, `search_project`,
`list_design_bases`, `validate_design_basis`.

## Setup
```bash
pip install -e ".[mcp]"
```
Claude Code / Claude Desktop entry (adjust the path to your checkout):
```json
{
  "mcpServers": {
    "structiq": {
      "command": "D:\Dev\StructIQ\.venv\Scripts\python.exe",
      "args": ["-m", "structiq.tools.mcp.server"]
    }
  }
}
```

## Local model (optional)
`python -m structiq.tools.mcp.ask_local --skill rc-design "your question"` asks a local Ollama model (default `qwen3:14b`),
grounded on the Core Brain and the chosen skill. Answers are AI text, not verified results.
