"""Local MCP server: lets any MCP client (Claude Code, Claude Desktop, Cline, ...) read StructIQ.

Read-only by design: no tool writes files, approves, issues or changes a check result.
Install the extra first: ``pip install -e ".[mcp]"``.  Run (stdio; the client starts it)::

    python -m structiq.tools.mcp.server
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as Server  # type: ignore[no-redef]

from structiq.tools.mcp import access

ACCESS = access.default_access()

server = Server(
    "structiq",
    instructions=(
        "StructIQ: AI-assisted structural engineering. Start with get_core_brain_rules, then list_skills and "
        "get_skill_context for the area in question, then read or search files. " + access.RULES
    ),
)


def _readable_errors(fn: Callable[..., str]) -> Callable[..., str]:
    """Return refusals and missing files as a readable message instead of a generic tool failure."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return fn(*args, **kwargs)
        except (PermissionError, FileNotFoundError, KeyError, ValueError) as exc:
            return f"ERROR: {exc}"

    return wrapper


@server.tool()
@_readable_errors
def get_core_brain_rules() -> str:
    """The Core Brain safety rules (read these first). Fails if the Core Brain cannot be read."""
    return ACCESS.brain_rules()


@server.tool()
@_readable_errors
def list_skills() -> str:
    """List the project skills with a one-line description."""
    return json.dumps(ACCESS.list_skills(), indent=1)


@server.tool()
@_readable_errors
def get_skill_context(name: str) -> str:
    """Project rules plus the named skill's SKILL.md."""
    return ACCESS.skill_context(name)


@server.tool()
@_readable_errors
def read_project_file(path: str, max_chars: int = 60000) -> str:
    """Read a text file by virtual path: 'repo/<path>' or 'brain/<path>'."""
    return ACCESS.read_file(path, max_chars=max_chars)


@server.tool()
@_readable_errors
def list_project_files(folder: str = "repo", pattern: str = "*") -> str:
    """List files under 'repo/<folder>' or 'brain/<folder>' (recursive glob). Binary files are not served."""
    return "\n".join(ACCESS.list_files(folder, pattern))


@server.tool()
@_readable_errors
def search_project(query: str, scope: str = "", max_results: int = 30) -> str:
    """Case-insensitive text search. scope: 'repo', 'brain' or empty for both."""
    return json.dumps(ACCESS.search(query, scope or None, max_results), indent=1)


@server.tool()
@_readable_errors
def list_design_bases() -> str:
    """List project design-basis files (the single source for project data). Contents are validated, not served."""
    return "\n".join(ACCESS.list_design_bases())


@server.tool()
@_readable_errors
def validate_design_basis(path: str) -> str:
    """Run the design-basis validator on one listed design basis and return its report (read-only)."""
    return ACCESS.validate_design_basis(path)


if __name__ == "__main__":
    server.run()
