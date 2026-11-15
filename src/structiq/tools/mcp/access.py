"""Read-only access to StructIQ for AI assistants (Claude, local Ollama models, other MCP clients).

Two roots are served, as virtual paths: ``repo/...`` (this repository: skills, docs, config, templates) and
``brain/...`` (the Core Brain on Google Drive). Project design bases are validated, never served as files.
Nothing here writes anything. Paths are confined to the roots; secrets, local config and caches are never served.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from structiq.core import design_basis
from structiq.core.config import load_config

TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".csv", ".py", ".toml"}
BLOCKED_PARTS = {".git", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".venv", "venv"}
BLOCKED_NAMES = {".env", "paths.yaml"}  # paths.yaml is this machine's local config
MAX_FILE_CHARS = 200_000
MAX_LIST = 500
BASIS_PATTERNS = ("*/design-basis.yaml", "*/*/design-basis.yaml", "*/*/*/design-basis.yaml")  # no deep Drive scans

RULES = (
    "Rules for any AI working on StructIQ: read the Core Brain safety rules first. Never invent engineering values, "
    "clauses, standards or PASS results; flag gaps instead. Never mark anything APPROVED: engineer sign-off is human. "
    "All outputs are DRAFT for engineer review. The design basis of a project is the single source for its data."
)


@dataclass(frozen=True)
class Access:
    repo: Path
    brain: Path | None = None
    projects: Path | None = None

    # ---- paths
    def _roots(self) -> dict[str, Path]:
        roots = {"repo": self.repo.resolve()}
        if self.brain is not None:
            roots["brain"] = self.brain.resolve()
        return roots

    def _split(self, path: str) -> tuple[str, Path, Path]:
        name, _, rest = path.replace("\\", "/").lstrip("/").partition("/")
        roots = self._roots()
        if name not in roots:
            known = ", ".join(f"{k}/..." for k in ("repo", "brain"))
            if name == "brain":
                raise FileNotFoundError("The Core Brain is not available (set core_brain in config/paths.yaml)")
            raise PermissionError(f"Path must start with one of: {known}")
        return name, roots[name], (roots[name] / rest).resolve()

    @staticmethod
    def _allowed(root: Path, p: Path) -> bool:
        try:
            r = p.relative_to(root)
        except ValueError:
            return False
        if any(part in BLOCKED_PARTS for part in r.parts):
            return False
        return p.name not in BLOCKED_NAMES and not p.name.startswith(".env")

    def resolve_safe(self, path: str) -> Path:
        _, root, p = self._split(path)
        if not self._allowed(root, p):
            raise PermissionError(f"Path not available to assistants: {path}")
        if not p.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        return p

    def virtual(self, p: Path) -> str:
        for name, root in self._roots().items():
            try:
                return f"{name}/{p.resolve().relative_to(root).as_posix()}"
            except ValueError:
                continue
        raise ValueError(f"{p} is outside the served roots")

    # ---- files
    def read_file(self, path: str, max_chars: int = MAX_FILE_CHARS) -> str:
        p = self.resolve_safe(path)
        if p.suffix.lower() not in TEXT_SUFFIXES:
            raise ValueError(f"Not a text file assistants can read: {path} (DXF, PDF, DOCX and XLSX are not served)")
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[... truncated at {max_chars} of {len(text)} characters]"
        return text

    def list_files(self, folder: str = "repo", pattern: str = "*") -> list[str]:
        _, root, base = self._split(folder if "/" in folder or folder in ("repo", "brain") else f"repo/{folder}")
        if not self._allowed(root, base) and base != root:
            raise PermissionError(f"Folder not available to assistants: {folder}")
        out = [self.virtual(p) for p in sorted(base.rglob(pattern)) if p.is_file() and self._allowed(root, p)]
        return out[:MAX_LIST]

    def _text_files(self, scope: str | None) -> list[Path]:
        roots = self._roots()
        names = [scope] if scope in roots else list(roots)
        files: list[Path] = []
        for n in names:
            root = roots[n]
            files += [
                p for p in sorted(root.rglob("*"))
                if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES and self._allowed(root, p)
            ]
        return files

    def search(self, query: str, scope: str | None = None, max_results: int = 30) -> list[dict[str, Any]]:
        """Case-insensitive text search over ``repo``, ``brain`` or both."""
        rx = re.compile(re.escape(query), re.IGNORECASE)
        hits: list[dict[str, Any]] = []
        for p in self._text_files(scope):
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for n, line in enumerate(lines, 1):
                if rx.search(line):
                    hits.append({"path": self.virtual(p), "line": n, "text": line.strip()[:300]})
                    if len(hits) >= max_results:
                        return hits
        return hits

    # ---- skills and brain
    def list_skills(self) -> list[dict[str, str]]:
        out = []
        for md in sorted((self.repo / ".claude" / "skills").glob("*/SKILL.md")):
            m = re.search(r"(?m)^description:\s*(.+)$", md.read_text(encoding="utf-8", errors="replace"))
            out.append({"name": md.parent.name, "description": m.group(1).strip() if m else "", "path": self.virtual(md)})
        return out

    def skill_context(self, name: str) -> str:
        """The rules plus the named skill: what an assistant should read before working in that area."""
        known = {s["name"] for s in self.list_skills()}
        if name not in known:
            raise KeyError(f"Unknown skill '{name}'. Known: {', '.join(sorted(known))}")
        return "\n\n---\n\n".join([RULES, self.read_file(f"repo/.claude/skills/{name}/SKILL.md")])

    def brain_rules(self) -> str:
        """The Core Brain safety rules, or an error when the brain cannot be read (never a fallback)."""
        return self.read_file("brain/03-Safety Rules/safety-rules.md")

    def knowledge_files(self, skill: str | None = None) -> list[Path]:
        """Brain markdown/yaml, plus one skill's files when named. ``None`` or ``core`` gives the brain only."""
        files: list[Path] = []
        if self.brain is not None:
            files += [p for p in sorted(self.brain.rglob("*")) if p.is_file() and p.suffix.lower() in {".md", ".yaml"}]
        if skill and skill != "core":
            folder = self.repo / ".claude" / "skills" / skill
            if not folder.is_dir():
                raise KeyError(f"Unknown skill '{skill}'")
            files += [p for p in sorted(folder.rglob("*")) if p.is_file() and p.suffix.lower() in {".md", ".yaml"}]
        return files

    # ---- design bases (validated, not served)
    def list_design_bases(self) -> list[str]:
        if self.projects is None or not self.projects.is_dir():
            return []
        found: list[Path] = []
        for pat in BASIS_PATTERNS:
            found += [p for p in sorted(self.projects.glob(pat)) if p not in found]
        return [f"projects/{p.relative_to(self.projects).as_posix()}" for p in found]

    def validate_design_basis(self, path: str) -> str:
        """Run the design-basis validator in-process on a listed design basis. Read-only."""
        if path not in self.list_design_bases() or self.projects is None:
            raise PermissionError("Only design bases returned by list_design_bases can be validated")
        import yaml

        file = self.projects / path.removeprefix("projects/")
        db = yaml.safe_load(file.read_text(encoding="utf-8"))
        issues = design_basis.validate(db)
        lines = [f"{sev:7} {p}: {msg}" for sev, p, msg in issues]
        errors = sum(1 for sev, *_ in issues if sev == "ERROR")
        lines.append(f"\n{errors} error(s), {len(issues) - errors} warning(s)")
        return "\n".join(lines)


def default_access() -> Access:
    cfg = load_config()
    brain = cfg.get("core_brain")
    projects = cfg.get("projects")
    return Access(
        repo=Path(__file__).resolve().parents[4],
        brain=Path(brain) if brain and Path(brain).is_dir() else None,
        projects=Path(projects) if projects else None,
    )
