"""Validation for the id_input / id_output VNTP JSON hand-off format.

VNTP JSON = a UTF-8 (BOM tolerated) file containing a JSON array of
`{"name": <string|null>, "message": <string>}` objects — the same shape the
cstl-translate skill parses (`parse --type json`) and exports (`--format json`).

Usage:
    python -m copas_reverse.vntp validate <file-or-dir> [--against <input>] [--report out.md]
    python -m copas_reverse.vntp pair <id_input_dir> <id_output_dir> [--report out.md]

Exit codes: 0 = all checks passed, 1 = problems found.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

KANA_RE = re.compile(r"[\u3040-\u30FF]")  # hiragana + katakana
# Control-ish tokens that must survive translation: tags, placeholders,
# escapes, printf-style specifiers.
TOKEN_RE = re.compile(r"<[^<>]+>|\{[^{}]+\}|%[0-9a-zA-Z]|\\[a-zA-Z]|\[[^\[\]]+\]")


def load_vntp(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: top level must be a JSON array")
    return data


def list_vntp_files(path: str) -> list[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    return sorted(f for f in p.rglob("*.json") if f.is_file())


def check_file(path: str, against: str | None = None) -> dict:
    """Validate one VNTP file. Returns a dict of findings."""
    res: dict = {"file": str(path), "errors": [], "warnings": []}
    try:
        entries = load_vntp(path)
    except (ValueError, json.JSONDecodeError) as e:
        res["errors"].append(f"not loadable: {e}")
        return res
    res["count"] = len(entries)
    tokens_out: CounterLike = {}
    for i, e in enumerate(entries, 1):
        if not isinstance(e, dict):
            res["errors"].append(f"entry {i}: not an object")
            continue
        msg = e.get("message")
        if not isinstance(msg, str) or not msg.strip():
            res["errors"].append(f"entry {i}: missing/empty message")
            continue
        name = e.get("name")
        if name is not None and not isinstance(name, str):
            res["errors"].append(f"entry {i}: name must be a string or null")
        for tok in TOKEN_RE.findall(msg):
            tokens_out[tok] = tokens_out.get(tok, 0) + 1
        if KANA_RE.search(msg):
            res["warnings"].append(f"entry {i}: kana left in message (untranslated?)")
    res["tokens"] = tokens_out
    if against:
        try:
            src = load_vntp(against)
        except (ValueError, json.JSONDecodeError) as e:
            res["errors"].append(f"input file not loadable: {e}")
            return res
        if len(src) != len(entries):
            res["errors"].append(
                f"line count mismatch: input {len(src)} vs output {len(entries)}")
        tokens_in: CounterLike = {}
        for e in src:
            if isinstance(e, dict) and isinstance(e.get("message"), str):
                for tok in TOKEN_RE.findall(e["message"]):
                    tokens_in[tok] = tokens_in.get(tok, 0) + 1
        drift = _token_drift(tokens_in, tokens_out)
        if drift:
            res["errors"].append(f"control token drift vs input: {drift}")
    return res


class CounterLike(dict):
    pass


def _token_drift(tokens_in: dict, tokens_out: dict) -> dict:
    drift: dict = {}
    for tok in sorted(set(tokens_in) | set(tokens_out)):
        a, b = tokens_in.get(tok, 0), tokens_out.get(tok, 0)
        if a != b:
            drift[tok] = f"{a} -> {b}"
    return drift


def pair_dirs(input_dir: str, output_dir: str) -> tuple[list[dict], bool]:
    """Cross-check id_input/ vs id_output/: same basenames, same counts."""
    ins = {f.name: f for f in list_vntp_files(input_dir)}
    outs = {f.name: f for f in list_vntp_files(output_dir)}
    rows: list[dict] = []
    ok = True
    for name in sorted(set(ins) | set(outs)):
        row: dict = {"file": name}
        if name not in outs:
            row["status"] = "MISSING in id_output"
            ok = False
        elif name not in ins:
            row["status"] = "EXTRA in id_output"
            ok = False
        else:
            try:
                a, b = load_vntp(str(ins[name])), load_vntp(str(outs[name]))
                row["input"] = len(a)
                row["output"] = len(b)
                if len(a) != len(b):
                    row["status"] = "COUNT MISMATCH"
                    ok = False
                else:
                    row["status"] = "OK"
            except (ValueError, json.JSONDecodeError) as e:
                row["status"] = f"LOAD ERROR: {e}"
                ok = False
        rows.append(row)
    return rows, ok


def render(rows: list[dict], title: str) -> str:
    lines = [f"# {title}", "", "| File | Input | Output | Status |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r.get('file')}` | {r.get('input', '–')} | "
                     f"{r.get('output', '–')} | {r.get('status', '?')} |")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate VNTP JSON hand-off files")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="validate one file or every file in a dir")
    p_val.add_argument("path")
    p_val.add_argument("--against", default=None,
                       help="optional input dir/file to compare counts and tokens against")
    p_val.add_argument("--report")

    p_pair = sub.add_parser("pair", help="cross-check id_input vs id_output by basename")
    p_pair.add_argument("input_dir")
    p_pair.add_argument("output_dir")
    p_pair.add_argument("--report")

    a = ap.parse_args(argv)
    ok = True
    if a.cmd == "pair":
        rows, ok = pair_dirs(a.input_dir, a.output_dir)
        text = render(rows, f"VNTP pair check: {a.input_dir} vs {a.output_dir}")
        print(text)
    else:
        sections = []
        for f in list_vntp_files(a.path):
            res = check_file(str(f), a.against)
            if res["errors"] or res["warnings"]:
                ok = False
            lines = [f"## {res['file']} — {res.get('count', '?')} entries"]
            for e in res["errors"]:
                lines.append(f"- ERROR: {e}")
            for w in res["warnings"][:20]:
                lines.append(f"- warn: {w}")
            if res["warnings"] and len(res["warnings"]) > 20:
                lines.append(f"- ... {len(res['warnings']) - 20} more warnings")
            if not res["errors"] and not res["warnings"]:
                lines.append("- OK")
            sections.append("\n".join(lines))
        text = "\n\n".join(sections) if sections else "no files found"
        print(text)
    if getattr(a, "report", None):
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"report written: {a.report}", file=sys.stderr)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
