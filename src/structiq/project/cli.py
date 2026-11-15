"""Command line: ``python -m structiq.project new | receive | adopt | where``."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from structiq.core.config import load_config
from structiq.project import adopt as adopt_mod
from structiq.project import create, receive
from structiq.project.layout import load_layout
from structiq.project.receive import Item
from structiq.project.record import read_record


def _parent(arg: str | None, folder: str) -> Path:
    if arg:
        return Path(arg)
    cfg = load_config()
    if cfg.get("freelance"):
        return Path(str(cfg["freelance"]))
    if cfg.get("projects"):
        return Path(str(cfg["projects"])) / folder
    raise SystemExit("No parent folder: pass --parent or set 'projects' (or 'freelance') in config/paths.yaml")


def _items(files: list[str], meta: str | None, revision: str | None) -> list[Item]:
    """Files plus optional drawing number / title / revision from a CSV (columns: file, drawing_no, title, revision)."""
    info: dict[str, dict[str, str]] = {}
    if meta:
        with open(meta, newline="", encoding="utf-8-sig") as fh:
            info = {Path(r["file"]).name.lower(): r for r in csv.DictReader(fh)}
    out = []
    for f in files:
        r = info.get(Path(f).name.lower(), {})
        out.append(Item(Path(f), r.get("drawing_no") or None, r.get("title") or None, r.get("revision") or revision))
    return out


def _receive_args(ns: argparse.Namespace, project: Path) -> list[Path]:
    layout, _ = load_layout()
    return receive.receive(
        project,
        _items(ns.received if ns.cmd == "new" else ns.files, ns.meta, ns.revision),
        ns.label,
        pattern=layout.received_pattern,
        columns=layout.received_columns,
        split=not ns.no_split,
    )


def _new(ns: argparse.Namespace) -> int:
    layout, version = load_layout()
    result = create.new_project(
        ns.name, _parent(ns.parent, layout.parent_folder), layout, version, year=ns.year, dry_run=ns.dry_run
    )
    print(("WOULD CREATE" if result.dry_run else "CREATED") + f" {result.root}")
    for rel in result.folders:
        print(f"  {rel}")
    for f in result.files:
        print(f"  file: {f.relative_to(result.root).as_posix()}")
    for w in result.warnings:
        print(f"! {w}")
    if ns.received and not result.dry_run:
        for dest in _receive_args(ns, result.root):
            print(f"  received: {dest.relative_to(result.root).as_posix()}")
    elif ns.received:
        print("  (drawings would be copied into a dated set under the architect folder)")
    return 0


def _receive(ns: argparse.Namespace) -> int:
    for dest in _receive_args(ns, Path(ns.project)):
        print(dest)
    return 0


def _confirm(ns: argparse.Namespace) -> int:
    layout, _ = load_layout()
    new = receive.confirm(
        ns.project, ns.rcv_no, ns.drawing_no, ns.title, ns.revision,
        pattern=layout.received_pattern, columns=layout.received_columns, note=ns.note,
    )
    print(new)
    return 0


def _register(ns: argparse.Namespace) -> int:
    rows = read_record(Path(ns.project)).get("received") or []
    for e in rows:
        print(f"{e['rcv_no']:11} {e['status']:12} {e.get('drawing_no') or '-':10} Rev {e.get('revision') or '-':4} {e['file']}")
    if not rows:
        print("nothing received yet")
    return 0


def _adopt(ns: argparse.Namespace) -> int:
    plan = adopt_mod.plan_adopt(ns.project) if ns.dry_run else adopt_mod.adopt(ns.project)
    print(("DETECTED (nothing written)" if ns.dry_run else f"WROTE {plan.written}") + f" for {plan.root.name}")
    for role, folder in plan.roles.items():
        print(f"  {role:20} -> {folder}")
    if plan.missing:
        print("  no folder found for: " + ", ".join(plan.missing))
    if plan.unmatched:
        print("  not mapped (left as they are): " + ", ".join(plan.unmatched))
    return 0


def _where(ns: argparse.Namespace) -> int:
    root = Path(ns.project)
    roles = read_record(root)["roles"]
    if ns.role not in roles:
        raise SystemExit(f"role {ns.role!r} not recorded; known: {', '.join(sorted(roles))}")
    print(root / roles[ns.role])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m structiq.project")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="create the next PJR-YYYY-NNN project folder from the Core Brain layout")
    p.add_argument("name", help="short project name")
    p.add_argument("--parent", help="folder that holds the projects (default: projects/01-Freelance from config)")
    p.add_argument("--year", type=int)
    p.add_argument("--received", nargs="*", default=[], help="architect drawings to store (.pdf .dwg .dxf)")
    p.add_argument("--label", default="Issue A", help="label of the received set (default: Issue A)")
    p.add_argument("--meta", help="CSV with columns file, drawing_no, title, revision for the received files")
    p.add_argument("--revision", help="revision for received files that have none in --meta")
    p.add_argument("--no-split", action="store_true", help="do not split combined PDFs into single sheets")
    p.add_argument("--dry-run", action="store_true", help="show what would be created; change nothing")
    p.set_defaults(fn=_new)

    p = sub.add_parser("receive", help="store received architect drawings in a new dated set")
    p.add_argument("project")
    p.add_argument("files", nargs="+")
    p.add_argument("--label", default="Issue A")
    p.add_argument("--meta", help="CSV with columns file, drawing_no, title, revision")
    p.add_argument("--revision", help="revision for files that have none in --meta")
    p.add_argument("--no-split", action="store_true")
    p.set_defaults(fn=_receive)

    p = sub.add_parser("confirm", help="name a stored file: drawing number, title, revision (renames it, updates the register)")
    p.add_argument("project")
    p.add_argument("rcv_no", help="e.g. RCV-007 or RCV-007.03")
    p.add_argument("--drawing-no", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--note", help="what the file contains (kept in the register note)")
    p.set_defaults(fn=_confirm)

    p = sub.add_parser("register", help="list the received-drawing register")
    p.add_argument("project")
    p.set_defaults(fn=_register)

    p = sub.add_parser("adopt", help="record the folder roles of an old project (moves nothing)")
    p.add_argument("project")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=_adopt)

    p = sub.add_parser("where", help="print the folder for a role")
    p.add_argument("project")
    p.add_argument("role")
    p.set_defaults(fn=_where)

    ns = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return int(ns.fn(ns))
    except (FileExistsError, FileNotFoundError, ValueError, KeyError) as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
