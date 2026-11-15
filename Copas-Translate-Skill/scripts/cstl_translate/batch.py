"""Batch read/write CopasTool project lines — the agent is the translation engine."""
from __future__ import annotations

import argparse
import json

from .cstl_io import backup_cstl, ensure_cstl, load_cstl, save_cstl


def _ordered_lines(data: dict) -> list[dict]:
    order = {file: index for index, file in enumerate(data.get("file_order", []))}
    return sorted(data.get("lines", []), key=lambda line: order.get(line.get("file"), len(order)))


def _batch_lines(data: dict, size: int) -> list[dict]:
    if size < 1:
        raise ValueError("batch size must be positive")
    return [line for line in _ordered_lines(data)
            if not line.get("_hidden") and not line.get("is_translated")
            and (line.get("message") or "").strip()][:size]


def read_batch(cstl_path: str, size: int = 100) -> list[dict]:
    data = ensure_cstl(load_cstl(cstl_path))
    out: list[dict] = []
    for ln in _batch_lines(data, size):
        out.append({
            "line_num": ln["line_num"],
            "file": ln.get("file", ""),
            "name": ln.get("name"),
            "message": ln.get("message", ""),
            "trans_message": ln.get("trans_message"),
        })
    return out


def read_context_batch(cstl_path: str, size: int = 100, before=None, after=None) -> dict:
    data = ensure_cstl(load_cstl(cstl_path))
    selected = _batch_lines(data, size)
    before = int(data.get("context_lines", 10) if before is None else before)
    after = int(data.get("context_lines_after", 0) if after is None else after)
    if before < 0 or after < 0:
        raise ValueError("context counts must be non-negative")
    visible = [line for line in _ordered_lines(data) if not line.get("_hidden")]
    if selected:
        first = visible.index(selected[0])
        last = visible.index(selected[-1])
        preceding = visible[max(0, first - before):first]
        following = visible[last + 1:last + 1 + after]
    else:
        preceding, following = [], []
    keys = ("line_num", "file", "name", "message", "trans_name", "trans_message",
            "is_translated", "ref_lang_1", "ref_lang_1_name", "ref_lang_2", "ref_lang_2_name")

    def records(lines):
        return [{key: line[key] for key in keys if key in line} for line in lines]

    return {
        "source_lang": data["source_lang"], "target_lang": data["target_lang"],
        "context_type": data.get("context_type", "raw"),
        "use_dialogue_tags": data.get("use_dialogue_tags") is not False,
        "prompt_header": data.get("prompt_header", ""),
        "glossary_text": data.get("glossary_text", ""),
        "currentBackground": data.get("currentBackground", ""),
        "context_before": records(preceding), "lines": records(selected),
        "context_after": records(following),
    }


def read_translated_batch(cstl_path: str, size: int = 100, offset: int = 0) -> list[dict]:
    if size < 1 or offset < 0:
        raise ValueError("size must be positive and offset non-negative")
    data = ensure_cstl(load_cstl(cstl_path))
    out: list[dict] = []
    translated = [line for line in _ordered_lines(data) if line.get("is_translated") and not line.get("_hidden")]
    for ln in translated[offset:offset + size]:
        out.append({
            "line_num": ln["line_num"],
            "file": ln.get("file", ""),
            "name": ln.get("name"),
            "message": ln.get("message", ""),
            "trans_message": ln.get("trans_message") or "",
            "trans_name": ln.get("trans_name"),
        })
    return out


def write_back(cstl_path: str, translations: list[dict], expected_batch=None) -> int:
    data = ensure_cstl(load_cstl(cstl_path))
    by_num = {ln["line_num"]: ln for ln in data.get("lines", [])}
    if expected_batch is not None:
        expected = expected_batch.get("lines") if isinstance(expected_batch, dict) else expected_batch
        if not isinstance(expected, list) or not isinstance(translations, list):
            raise ValueError("expected batch and translations must contain arrays")
        expected_nums = [line["line_num"] for line in expected]
        actual_nums = [item.get("line_num") for item in translations]
        if expected_nums != actual_nums or len(set(actual_nums)) != len(actual_nums):
            raise ValueError("translations must match the expected batch's line numbers, count, and order")
        for source, item in zip(expected, translations):
            current = by_num.get(source["line_num"])
            if current is None or any(current.get(key) != source.get(key) for key in ("file", "name", "message")):
                raise ValueError(f"source line {source['line_num']} changed since the batch was read")
            name = item.get("trans_name") or item.get("translated_name") or item.get("name")
            if bool((source.get("name") or "").strip()) != bool(name and str(name).strip()):
                raise ValueError(f"speaker presence changed on line {source['line_num']}")
    backup_cstl(cstl_path)
    applied = 0
    for it in translations:
        try:
            num = int(it["line_num"])
        except Exception:
            continue
        ln = by_num.get(num)
        if ln is None:
            continue
        tmsg = it.get("trans_message")
        if tmsg is None:
            # Support alternative key
            tmsg = it.get("translated_text") or it.get("text") or ""
        tmsg = str(tmsg)
        # Normalize: CSTL stores \n as \\n literal
        tmsg = tmsg.replace("\n", "\\n").replace("<br>", "\\n")
        tname = it.get("trans_name")
        if tname is None:
            tname = it.get("translated_name") or it.get("name")
        if tname is not None:
            tname = str(tname).strip() or None
            if tname is not None:
                ln["trans_name"] = tname
        if expected_batch is not None and not (ln.get("name") or "").strip():
            ln["trans_name"] = None
        ln["trans_message"] = tmsg
        # Mark translated if we have content or validation allows empty
        ln["is_translated"] = bool(tmsg.strip()) or bool(data.get("disable_empty_line_validation"))
        if not ln["is_translated"] and tmsg.strip():
            ln["is_translated"] = True
        if tmsg.strip():
            ln["is_translated"] = True
        applied += 1
    save_cstl(cstl_path, data)
    return applied


def main(argv=None):
    ap = argparse.ArgumentParser(description="Batch read/write for CopasTool project backups")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("read", help="Print next untranslated batch as JSON")
    r.add_argument("cstl_path")
    r.add_argument("--size", type=int, default=100)
    r.add_argument("--with-context", action="store_true", help="Emit a lines array with read-only context and project prompt/glossary")
    r.add_argument("--context-before", type=int, help="Override saved context_lines")
    r.add_argument("--context-after", type=int, help="Override saved context_lines_after")

    rt = sub.add_parser("read-translated", help="Print next translated batch (for polish)")
    rt.add_argument("cstl_path")
    rt.add_argument("--size", type=int, default=100)
    rt.add_argument("--offset", type=int, default=0, help="Skip this many translated lines when reviewing successive batches")

    w = sub.add_parser("write", help="Write translations back from a JSON file")
    w.add_argument("cstl_path")
    w.add_argument("translations_json_path")
    w.add_argument("--expect-batch", help="Validate alignment, speaker presence, and source identity against a saved batch before writing")

    a = ap.parse_args(argv)
    if a.cmd == "read":
        try:
            if not a.with_context and (a.context_before is not None or a.context_after is not None):
                ap.error("context overrides require --with-context")
            batch = (read_context_batch(a.cstl_path, a.size, a.context_before, a.context_after)
                     if a.with_context else read_batch(a.cstl_path, size=a.size))
        except ValueError as e:
            ap.error(str(e))
        print(json.dumps(batch, ensure_ascii=False))
    elif a.cmd == "read-translated":
        try:
            batch = read_translated_batch(a.cstl_path, size=a.size, offset=a.offset)
        except ValueError as e:
            ap.error(str(e))
        print(json.dumps(batch, ensure_ascii=False))
    elif a.cmd == "write":
        try:
            with open(a.translations_json_path, encoding="utf-8-sig") as f:
                translations = json.load(f)
        except Exception as e:
            ap.error(f"cannot read translations file: {e}")
        if isinstance(translations, dict) and "translations" in translations:
            translations = translations["translations"]
        total = len(translations)
        try:
            expected = None
            if a.expect_batch:
                with open(a.expect_batch, encoding="utf-8-sig") as f:
                    expected = json.load(f)
            applied = write_back(a.cstl_path, translations, expected_batch=expected)
        except (OSError, ValueError, KeyError, TypeError) as e:
            ap.error(str(e))
        if applied < total:
            print(f"applied {applied} of {total} translation(s) ({total - applied} unmatched line_num)")
        else:
            print(f"applied {applied} translation(s)")


if __name__ == "__main__":
    main()
