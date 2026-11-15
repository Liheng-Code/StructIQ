"""Command line: ``python -m structiq.project new | receive | adopt | where``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from structiq.core.config import load_config
from structiq.project import adopt as adopt_mod
from structiq.project import create, receive
from structiq.project.layout import load_layout
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
        for dest in receive.receive(result.root, ns.received, ns.label):
            print(f"  received: {dest.relative_to(result.root).as_posix()}")
    elif ns.received:
        print("  (drawings would be copied into a dated set under the architect folder)")
    return 0


def _receive(ns: argparse.Namespace) -> int:
    for dest in receive.receive(ns.project, ns.files, ns.label):
        print(dest)
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
    p.add_argument("--dry-run", action="store_true", help="show what would be created; change nothing")
    p.set_defaults(fn=_new)

    p = sub.add_parser("receive", help="store received architect drawings in a new dated set")
    p.add_argument("project")
    p.add_argument("files", nargs="+")
    p.add_argument("--label", default="Issue A")
    p.set_defaults(fn=_receive)

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
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
