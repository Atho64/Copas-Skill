"""Per-project state every stage reads, stored next to the project backup.

  <project>.decisions.json   settled renderings, source errata, per-line token exceptions,
                             project lint rules (regex that must not match a translation)
  <project>.provenance.jsonl one row per line changed by `batch apply --source ...`
                             (what changed, why, and snippets a later pass must not restore)

  state show <project>
  state settle <project> --dst "Kak Mugi" [--src 麦先輩] [--note ...]
  state errata <project> LINE --note ...
  state token-exception <project> LINE --reason ...
  state lint-rule <project> NAME --re REGEX [--msg ...]
  state card <project> [--range A-B]          compact rule card for an agent prompt
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import time

EMPTY = {"settled": [], "errata": {}, "token_exceptions": {}, "lint": []}
PROTECTED_SOURCES = ("dual", "external", "codex", "user", "editor")
_WORDISH = re.compile(r"[A-Za-z\u3040-\u30ff\u3400-\u9fff]")


def _base(project: str) -> str:
    return os.path.abspath(project)


def decisions_path(project: str) -> str:
    p = _base(project) + ".decisions.json"
    if not os.path.exists(p):
        alt = os.path.join(os.path.dirname(_base(project)), "decisions.json")
        if os.path.exists(alt):
            return alt
    return p


def provenance_path(project: str) -> str:
    p = _base(project) + ".provenance.jsonl"
    if not os.path.exists(p):
        alt = os.path.join(os.path.dirname(_base(project)), "provenance.jsonl")
        if os.path.exists(alt):
            return alt
    return p


def load(project: str | None) -> dict:
    d = {k: (list(v) if isinstance(v, list) else dict(v)) for k, v in EMPTY.items()}
    if project:
        p = decisions_path(project)
        if os.path.exists(p):
            with open(p, encoding="utf-8-sig") as f:
                d.update(json.load(f))
    return d


def save(project: str, d: dict) -> None:
    p = _base(project) + ".decisions.json"
    tmp = p + f".tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def token_exceptions(d: dict) -> set[int]:
    exc = set()
    for key in ("token_exceptions", "tag_exceptions"):
        for k in (d.get(key) or {}):
            exc.add(int(k))
    return exc


def settled_dst(d: dict) -> list[str]:
    return [s["dst"] for s in d.get("settled", []) if (s.get("dst") or "").strip()]


def lint_rules(d: dict) -> list[tuple[str, re.Pattern, str]]:
    return [(r["name"], re.compile(r["re"]), r.get("msg", "")) for r in d.get("lint", [])]


def removed_snippets(old: str, new: str, min_chars: int = 3, ctx: int = 2) -> list[str]:
    """Chunks a fix removed from `old` (with a little surrounding context)."""
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    out = []
    for op, a1, a2, _, _ in sm.get_opcodes():
        if op in ("replace", "delete") and len(_WORDISH.findall(old[a1:a2])) >= min_chars:
            out.append(old[max(0, a1 - ctx):a2 + ctx].strip())
    return out


def record(project: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(provenance_path(project), "a", encoding="utf-8") as f:
        for r in rows:
            r = dict(r)
            r.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
            r["removed"] = removed_snippets(r.get("before") or "", r.get("after") or "")
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def history(project: str | None) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    p = provenance_path(project) if project else ""
    if p and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    out.setdefault(int(r["line_num"]), []).append(r)
    return out


def protected_removals(project: str | None) -> dict[int, set[str]]:
    """Snippets a meaning fix removed, per line: a later pass must not reintroduce them."""
    out: dict[int, set[str]] = {}
    for num, rows in history(project).items():
        for r in rows:
            if str(r.get("source", "")).split(":")[0] in PROTECTED_SOURCES:
                out.setdefault(num, set()).update(r.get("removed", []))
    return out


def card(project: str, lo: int | None = None, hi: int | None = None) -> str:
    d = load(project)
    inr = (lambda i: True) if lo is None else (lambda i: lo <= i <= hi)
    L: list[str] = []
    if d["settled"]:
        L.append("## Settled renderings (keep; do not report)")
        L += [f"- {s.get('src') + ' -> ' if s.get('src') else ''}{s['dst']}"
              + (f" ({s['note']})" if s.get("note") else "") for s in d["settled"]]
    err = {int(k): v for k, v in d["errata"].items() if inr(int(k))}
    if err:
        L.append("## Source errata (already handled; do not report)")
        L += [f"- {k}: {v}" for k, v in sorted(err.items())]
    tex = {int(k): v for k, v in {**(d.get("tag_exceptions") or {}), **(d.get("token_exceptions") or {})}.items() if inr(int(k))}
    if tex:
        L.append("## Token-count exceptions (not errors)")
        L += [f"- {k}: {v}" for k, v in sorted(tex.items())]
    if d["lint"]:
        L.append("## Project lint rules (a match is a warning)")
        L += [f"- {r['name']}: /{r['re']}/ {r.get('msg', '')}".rstrip() for r in d["lint"]]
    fixed = [(i, r) for i, rs in sorted(history(project).items()) if inr(i) for r in rs
             if str(r.get("source", "")).split(":")[0] in PROTECTED_SOURCES and r.get("reason")]
    if fixed:
        L.append("## Meaning fixes already made (do not revert)")
        L += [f"- {i}: {r['reason']}" for i, r in fixed]
    return "\n".join(L) + ("\n" if L else "")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Project decisions / errata / token exceptions / provenance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show").add_argument("project")
    s = sub.add_parser("settle"); s.add_argument("project"); s.add_argument("--dst", required=True)
    s.add_argument("--src"); s.add_argument("--note")
    e = sub.add_parser("errata"); e.add_argument("project"); e.add_argument("line", type=int)
    e.add_argument("--note", required=True)
    t = sub.add_parser("token-exception", aliases=["tag-exception"]); t.add_argument("project"); t.add_argument("line", type=int)
    t.add_argument("--reason", required=True)
    lr = sub.add_parser("lint-rule"); lr.add_argument("project"); lr.add_argument("name")
    lr.add_argument("--re", required=True); lr.add_argument("--msg", default="")
    c = sub.add_parser("card"); c.add_argument("project"); c.add_argument("--range", metavar="A-B")
    a = ap.parse_args(argv)
    d = load(a.project)
    if a.cmd == "show":
        print(f"settled {len(d['settled'])}, errata {len(d['errata'])}, token_exceptions "
              f"{len(token_exceptions(d))}, lint {len(d['lint'])}, provenance lines {len(history(a.project))}")
        return 0
    if a.cmd == "card":
        lo = hi = None
        if a.range:
            lo, hi = (int(x) for x in a.range.split("-", 1))
        print(card(a.project, lo, hi), end="")
        return 0
    if a.cmd == "settle":
        d["settled"] = [x for x in d["settled"] if x.get("dst") != a.dst]
        d["settled"].append({k: v for k, v in (("dst", a.dst), ("src", a.src), ("note", a.note)) if v})
    elif a.cmd == "errata":
        d["errata"][str(a.line)] = a.note
    elif a.cmd in ("token-exception", "tag-exception"):
        d["token_exceptions"][str(a.line)] = a.reason
    elif a.cmd == "lint-rule":
        re.compile(a.re)
        d["lint"] = [x for x in d["lint"] if x["name"] != a.name] + [{"name": a.name, "re": a.re, "msg": a.msg}]
    save(a.project, d)
    print(f"saved -> {decisions_path(a.project)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
