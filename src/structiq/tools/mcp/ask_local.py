"""Ask a local Ollama model (default qwen3:14b) about StructIQ, grounded on the Core Brain and one skill.

    python -m structiq.tools.mcp.ask_local --skill rc-design "What inputs do I need before an anchorage check?"
    python -m structiq.tools.mcp.ask_local --skill structural-documentation     (interactive; empty line or Ctrl+C to quit)

No extra packages: retrieval is keyword scoring over Markdown/YAML sections of the Core Brain and the chosen skill, and the
model is called through the Ollama HTTP API (default http://localhost:11434). Answers are AI text, not verified results.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request

from structiq.tools.mcp import access

ACCESS = access.default_access()

STOP = {"the", "and", "for", "with", "what", "how", "are", "can", "this", "that", "from", "does", "should", "which", "into"}


def sections(skill: str | None) -> list[tuple[str, str]]:
    """Split each knowledge file into (source label, text) chunks at Markdown headings."""
    out: list[tuple[str, str]] = []
    for p in ACCESS.knowledge_files(skill):
        text = p.read_text(encoding="utf-8", errors="replace")
        parts = re.split(r"(?m)^(?=#{1,3} )", text) if p.suffix == ".md" else [text]
        for part in parts:
            if part.strip():
                heading = part.strip().splitlines()[0][:80]
                out.append((f"{ACCESS.virtual(p)} :: {heading}", part.strip()))
    return out


def retrieve(question: str, skill: str | None, budget_chars: int = 24000) -> list[tuple[str, str]]:
    terms = [t for t in re.findall(r"[a-z0-9][a-z0-9\-\.]+", question.lower()) if len(t) >= 3 and t not in STOP]
    scored = []
    for label, text in sections(skill):
        low = text.lower()
        score = sum(low.count(t) for t in terms) + 3 * sum(t in label.lower() for t in terms)
        if score:
            scored.append((score, label, text))
    scored.sort(key=lambda s: -s[0])
    picked, used = [], 0
    for _, label, text in scored:
        chunk = text[:6000]
        if used + len(chunk) > budget_chars:
            continue
        picked.append((label, chunk))
        used += len(chunk)
    return picked


def build_messages(question: str, skill: str | None) -> list[dict[str, str]]:
    ctx = retrieve(question, skill)
    context = "\n\n".join(f"[SOURCE: {label}]\n{text}" for label, text in ctx) or "(no matching project text found)"
    system = (
        "You are a structural engineering assistant for StructIQ. " + access.RULES +
        " Answer only from the SOURCE extracts below; cite the source path for each point. If the extracts do not "
        "contain the answer, say so and name what is missing. Do not give numerical design values, clause numbers or "
        "PASS/FAIL results that are not in the extracts.\n\n" + context
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": question}]


def ask(question: str, skill: str | None, model: str, host: str, num_ctx: int) -> str:
    body = {"model": model, "messages": build_messages(question, skill), "stream": False, "think": False,
            "options": {"num_ctx": num_ctx, "temperature": 0.2}}
    req = urllib.request.Request(f"{host}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            reply = json.load(resp)["message"]["content"]
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach Ollama at {host} ({exc}). Start it with: ollama serve") from exc
    return re.sub(r"(?s)<think>.*?</think>", "", reply).strip()


def main() -> None:
    skill_ids = [s["name"] for s in ACCESS.list_skills()]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?", help="omit for interactive mode")
    ap.add_argument("--skill", choices=[*skill_ids, "core"], default="core")
    ap.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "qwen3:14b"))
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434"))
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--show-sources", action="store_true", help="print the retrieved sources, do not call the model")
    a = ap.parse_args()
    if a.show_sources:
        for label, _ in retrieve(a.question or "", a.skill):
            print(label)
        return
    if a.question:
        print(ask(a.question, a.skill, a.model, a.host, a.num_ctx))
        return
    print(f"[{a.model} | {a.skill}] Ask a question (empty line to quit).")
    try:
        while (q := input("> ").strip()):
            print(ask(q, a.skill, a.model, a.host, a.num_ctx), "\n")
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    main()
