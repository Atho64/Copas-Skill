"""Batch read/split/bundle/validate/write/apply for CopasTool project backups."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from . import audit, cache as cache_mod, glossary as glossary_mod, langpair, state
from .cstl_io import (
    backup_cstl,
    ensure_cstl,
    load_cstl,
    locked,
    log_event,
    ordered_lines,
    save_cstl,
)
from .integrity import check_message, check_snapshot, expected_lines, normalize_message
from .prompt import project_prompt_info


def _ordered_lines(data: dict) -> list[dict]:
    return ordered_lines(data)


def _selected_lines(data: dict, size: int, task: str = "translate", offset: int = 0, files=None) -> list[dict]:
    if size < 1 or offset < 0:
        raise ValueError("batch size must be positive and offset non-negative")
    if task not in ("translate", "agent", "glossary", "ai-check"):
        raise ValueError(f"unsupported batch task: {task}")
    eligible = [
        line for line in _ordered_lines(data)
        if not line.get("_hidden") and (line.get("message") or "").strip()
    ]
    if files is not None:
        allowed = set(files)
        eligible = [line for line in eligible if line.get("file") in allowed]
    if task in ("translate", "agent"):
        eligible = [line for line in eligible if not line.get("is_translated")]
    elif task == "ai-check":
        eligible = [line for line in eligible if line.get("is_translated")]
    return eligible[offset:offset + size]


def _batch_lines(data: dict, size: int) -> list[dict]:
    return _selected_lines(data, size)


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


def read_context_batch(
    cstl_path: str,
    size: int = 100,
    before=None,
    after=None,
    task="translate",
    offset=0,
    files=None,
    brief_path=None,
) -> dict:
    data = ensure_cstl(load_cstl(cstl_path))
    selected = _selected_lines(data, size, task, offset, files)
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
    keys = (
        "line_num", "file", "name", "message", "trans_name", "trans_message",
        "is_translated", "ref_lang_1", "ref_lang_1_name", "ref_lang_2", "ref_lang_2_name",
    )

    def records(lines):
        return [{key: line[key] for key in keys if key in line} for line in lines]

    brief = Path(brief_path) if brief_path is not None else Path(str(cstl_path) + ".brief.md")
    brief_text = ""
    brief_source = None
    if brief_path is not None or brief.exists():
        brief_text = brief.read_text(encoding="utf-8-sig")
        brief_source = str(brief.resolve())

    return {
        "source_lang": data["source_lang"],
        "target_lang": data["target_lang"],
        "context_type": data.get("context_type", "raw"),
        "use_dialogue_tags": data.get("use_dialogue_tags") is not False,
        "prompt_header": data.get("prompt_header", ""),
        "glossary_text": data.get("glossary_text", ""),
        "currentBackground": data.get("currentBackground", ""),
        "project_brief": brief_text,
        "project_brief_source": brief_source,
        "context_before": records(preceding),
        "lines": records(selected),
        "context_after": records(following),
        **project_prompt_info(data, task, len(selected)),
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


# --------------------------------------------------------------- IO helpers ----
def _row_line_num(row: dict) -> int:
    if "line_num" in row:
        return int(row["line_num"])
    if "text_index" in row:
        return int(row["text_index"])
    return int(row["i"])


def load_translations(path: str) -> list[dict]:
    """Load JSON array, {"translations"|"items": [...]}, or JSONL."""
    with open(path, "r", encoding="utf-8-sig") as f:
        if path.lower().endswith(".jsonl"):
            rows = []
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{ln}: {e}") from e
            return rows
        data = json.load(f)
    if isinstance(data, dict):
        if "translations" in data:
            data = data["translations"]
        elif "items" in data:
            data = data["items"]
        elif "polished" in data:
            data = data["polished"]
        elif "lines" in data:
            data = data["lines"]
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array")
    return data


def load_many(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        rows.extend(load_translations(p))
    return rows


def duplicates(rows: list[dict]) -> list[int]:
    c = Counter(_row_line_num(r) for r in rows if any(k in r for k in ("line_num", "text_index", "i")))
    return sorted(i for i, n in c.items() if n > 1)


def _extract_trans_message(item: dict) -> str | None:
    for k in ("trans_message", "polished_text", "translated_text", "text"):
        if k in item and item[k] is not None:
            return str(item[k])
    return None


def _extract_trans_name(item: dict):
    for k in ("trans_name", "polished_name", "translated_name", "name"):
        if k in item:
            return item[k]
    return None


def _apply_patches(current: str, patches) -> str | None:
    text = current or ""
    for old, new in patches:
        if not old or text.count(old) != 1:
            return None
        text = text.replace(old, new, 1)
    return text


def write_back(
    cstl_path: str,
    translations: list[dict],
    expected_batch=None,
    *,
    allow_tag_mismatch: bool = False,
) -> int:
    data = ensure_cstl(load_cstl(cstl_path))
    by_num = {ln["line_num"]: ln for ln in data.get("lines", [])}
    dec = state.load(cstl_path)
    exc = state.token_exceptions(dec)
    if expected_batch is not None:
        expected = expected_lines(expected_batch)
        if not isinstance(translations, list) or any(not isinstance(item, dict) for item in translations):
            raise ValueError("expected batch and translations must contain arrays")
        expected_nums = [line["line_num"] for line in expected]
        actual_nums = [item.get("line_num") for item in translations]
        if any(type(num) is not int for num in actual_nums) or expected_nums != actual_nums or len(set(actual_nums)) != len(actual_nums):
            raise ValueError("translations must match the expected batch's line numbers, count, and order")
        for source, item in zip(expected, translations):
            current = by_num.get(source["line_num"])
            check_snapshot(current, source, translation=True)
            name = item.get("trans_name") or item.get("translated_name") or item.get("name")
            if name is not None and not isinstance(name, str):
                raise ValueError(f"speaker on line {source['line_num']} must be a string or null")
            if bool((source.get("name") or "").strip()) != bool(name and str(name).strip()):
                raise ValueError(f"speaker presence changed on line {source['line_num']}")
            message = item.get("trans_message")
            if message is None:
                message = item.get("translated_text") if "translated_text" in item else item.get("text")
            allow_exc = allow_tag_mismatch or (source["line_num"] in exc)
            check_message(
                source.get("message") or "",
                message,
                source["line_num"],
                bool(data.get("disable_empty_line_validation")),
                allow_tag_mismatch=allow_exc,
            )

    with locked(cstl_path):
        backup_cstl(cstl_path)
        # Re-read under lock for fresh mutation if not snapshot-checked
        if expected_batch is None:
            data = ensure_cstl(load_cstl(cstl_path))
            by_num = {ln["line_num"]: ln for ln in data.get("lines", [])}
        applied = 0
        for it in translations:
            try:
                num = _row_line_num(it)
            except Exception:
                continue
            ln = by_num.get(num)
            if ln is None:
                continue
            tmsg = _extract_trans_message(it)
            if tmsg is None:
                tmsg = ""
            tmsg = normalize_message(str(tmsg))
            tname = _extract_trans_name(it)
            if tname is not None:
                tname = str(tname).strip() or None
                if tname is not None:
                    ln["trans_name"] = tname
            if expected_batch is not None and not (ln.get("name") or "").strip():
                ln["trans_name"] = None
            ln["trans_message"] = tmsg
            ln["is_translated"] = bool(tmsg.strip()) or bool(data.get("disable_empty_line_validation"))
            if tmsg.strip():
                ln["is_translated"] = True
            applied += 1
        save_cstl(cstl_path, data)
    log_event(cstl_path, {"event": "write", "applied": applied, "total": len(translations)})
    return applied


def write_gated(
    cstl_path: str,
    translations: list[dict],
    *,
    force: bool = False,
    allow_tag_mismatch: bool = False,
) -> dict:
    """Gate + write JSON/JSONL translations without --expect-batch, returning summary + rejected."""
    dec = state.load(cstl_path)
    exc = state.token_exceptions(dec)
    rules = state.lint_rules(dec)
    res = {"total": len(translations), "applied": 0, "rejected": [], "warnings": {}}
    with locked(cstl_path):
        backup_cstl(cstl_path)
        data = ensure_cstl(load_cstl(cstl_path))
        by_num = {int(ln["line_num"]): ln for ln in data.get("lines", [])}
        sl, tl = data.get("source_lang", "Japanese"), data.get("target_lang", "Indonesian")
        disable_empty = bool(data.get("disable_empty_line_validation"))

        for it in translations:
            try:
                num = _row_line_num(it)
            except Exception:
                res["rejected"].append({"line_num": None, "reason": "missing_line_num"})
                continue
            ln = by_num.get(num)
            if ln is None:
                res["rejected"].append({"line_num": num, "reason": "unknown_line_num"})
                continue
            tmsg = _extract_trans_message(it)
            if tmsg is None:
                res["rejected"].append({"line_num": num, "reason": "missing_trans_message"})
                continue
            tmsg_norm = normalize_message(tmsg)
            tname = _extract_trans_name(it)
            if not (ln.get("name") or "").strip():
                if tname and str(tname).strip() and not force:
                    res["rejected"].append({"line_num": num, "reason": "speaker_invented"})
                    continue
                tname_clean = None
            else:
                tname_clean = str(tname).strip() if tname is not None else ""
                if not tname_clean:
                    tname_clean = (ln.get("trans_name") or "").strip() or None
            probe = {
                "line_num": num,
                "name": ln.get("name"),
                "message": ln.get("message") or "",
                "trans_name": tname_clean,
                "trans_message": tmsg_norm,
            }
            hard, soft = audit.lint_line(
                probe,
                source_lang=sl,
                target_lang=tl,
                allow_tag_mismatch=allow_tag_mismatch,
                token_exceptions=exc,
                rules=rules,
                disable_empty=disable_empty,
            )
            if hard and not force:
                res["rejected"].append({"line_num": num, "reason": ",".join(hard)})
                continue
            for w in soft:
                res["warnings"][w] = res["warnings"].get(w, 0) + 1
            ln["trans_message"] = tmsg_norm
            ln["trans_name"] = tname_clean
            ln["is_translated"] = bool(tmsg_norm.strip()) or disable_empty
            res["applied"] += 1
        save_cstl(cstl_path, data)
    log_event(cstl_path, {"event": "write", "applied": res["applied"], "rejected": len(res["rejected"]), "total": res["total"]})
    return res


def apply_rows(
    cstl_path: str,
    rows: list[dict],
    *,
    source: str | None = None,
    reason: str | None = None,
    force: bool = False,
    allow_tag_mismatch: bool = False,
) -> dict:
    """Unified fix writer: supports full text or patches [[old, new]], preserves line status, logs provenance."""
    dec = state.load(cstl_path)
    exc = state.token_exceptions(dec)
    rules = state.lint_rules(dec)
    res = {"total": len(rows), "applied": 0, "rejected": [], "warnings": {}, "changes": []}
    with locked(cstl_path):
        backup_cstl(cstl_path)
        data = ensure_cstl(load_cstl(cstl_path))
        by_num = {int(ln["line_num"]): ln for ln in data.get("lines", [])}
        sl, tl = data.get("source_lang", "Japanese"), data.get("target_lang", "Indonesian")
        disable_empty = bool(data.get("disable_empty_line_validation"))

        for it in rows:
            try:
                num = _row_line_num(it)
            except Exception:
                res["rejected"].append({"line_num": None, "reason": "missing_line_num"})
                continue
            ln = by_num.get(num)
            if ln is None:
                res["rejected"].append({"line_num": num, "reason": "unknown_line_num"})
                continue
            old_msg = ln.get("trans_message") or ""
            old_name = ln.get("trans_name")
            if "patches" in it:
                new_msg = _apply_patches(old_msg, it["patches"])
                if new_msg is None:
                    res["rejected"].append({"line_num": num, "reason": "patch_not_found"})
                    continue
            else:
                extracted = _extract_trans_message(it)
                new_msg = old_msg if extracted is None else extracted
            new_msg = normalize_message(str(new_msg))

            if "name_patches" in it and old_name:
                new_name = _apply_patches(old_name, it["name_patches"])
                if new_name is None:
                    res["rejected"].append({"line_num": num, "reason": "name_patch_not_found"})
                    continue
            else:
                extracted_name = _extract_trans_name(it)
                if extracted_name is not None:
                    new_name = str(extracted_name).strip() or None
                else:
                    new_name = old_name
            if not (ln.get("name") or "").strip():
                if new_name and not force and any(k in it for k in ("trans_name", "polished_name", "translated_name", "name")):
                    res["rejected"].append({"line_num": num, "reason": "speaker_invented"})
                    continue
                new_name = None

            probe = {
                "line_num": num,
                "name": ln.get("name"),
                "message": ln.get("message") or "",
                "trans_name": new_name,
                "trans_message": new_msg,
            }
            hard, soft = audit.lint_line(
                probe,
                source_lang=sl,
                target_lang=tl,
                allow_tag_mismatch=allow_tag_mismatch,
                token_exceptions=exc,
                rules=rules,
                disable_empty=disable_empty,
            )
            if hard and not force:
                res["rejected"].append({"line_num": num, "reason": ",".join(hard)})
                continue
            for w in soft:
                res["warnings"][w] = res["warnings"].get(w, 0) + 1
            if new_msg != old_msg or new_name != old_name:
                res["changes"].append({
                    "line_num": num,
                    "before": old_msg,
                    "after": new_msg,
                    "before_name": old_name,
                    "after_name": new_name,
                })
            ln["trans_message"] = new_msg
            ln["trans_name"] = new_name
            if not ln.get("is_translated") and (new_msg.strip() or disable_empty):
                ln["is_translated"] = True
            res["applied"] += 1
        save_cstl(cstl_path, data)

    if source:
        why = {_row_line_num(r): r.get("reason") or reason for r in rows if any(k in r for k in ("line_num", "text_index", "i"))}
        state.record(cstl_path, [{**c, "source": source, "reason": why.get(c["line_num"])} for c in res["changes"]])
    log_event(cstl_path, {"event": "apply", "source": source, "applied": res["applied"], "changed": len(res["changes"]), "rejected": len(res["rejected"])})
    return res


# ------------------------------------------------------------------ split ----
def _file_runs(data: dict) -> list[tuple[str, list[dict]]]:
    runs: list[tuple[str, list[dict]]] = []
    for ln in _ordered_lines(data):
        fname = ln.get("file", "")
        if runs and runs[-1][0] == fname:
            runs[-1][1].append(ln)
        else:
            runs.append((fname, [ln]))
    return runs


def _eligible_for_stage(ln: dict, stage: str, index_range=None, files=None, only=None, include_polished: bool = False) -> bool:
    if ln.get("_hidden") or not (ln.get("message") or "").strip():
        return False
    num = int(ln["line_num"])
    if index_range and not (index_range[0] <= num <= index_range[1]):
        return False
    if files is not None and ln.get("file", "") not in files:
        return False
    if only is not None and num not in only:
        return False
    is_t = bool(ln.get("is_translated"))
    if stage == "translate":
        return not is_t
    if stage == "polish":
        return is_t and (include_polished or not ln.get("_polished"))
    if stage == "review":
        return is_t
    raise ValueError(f"unsupported stage: {stage}")


def split_project(
    cstl_path: str,
    target: int = 250,
    out_dir: str | None = None,
    context_before: int | None = None,
    context_after: int | None = None,
    stage: str = "translate",
    index_range: tuple[int, int] | None = None,
    files: list[str] | None = None,
    prefix: str = "",
    only: set[int] | None = None,
    include_polished: bool = False,
) -> dict:
    data = ensure_cstl(load_cstl(cstl_path))
    before = int(data.get("context_lines", 15) if context_before is None else context_before)
    after = int(data.get("context_lines_after", 0) if context_after is None else context_after)
    allowed_files = set(files) if files else None

    file_groups = []
    for fname, items in _file_runs(data):
        td = [it for it in items if _eligible_for_stage(it, stage, index_range, allowed_files, only, include_polished)]
        if td:
            file_groups.append((fname, td))

    groups: list[dict] = []
    cur = {"files": [], "items": []}

    def flush():
        nonlocal cur
        if cur["items"]:
            groups.append(cur)
        cur = {"files": [], "items": []}

    for fname, td in file_groups:
        if len(td) > 1.5 * target:
            flush()
            n = math.ceil(len(td) / target)
            sz = math.ceil(len(td) / n)
            for i in range(n):
                groups.append({"files": [fname], "items": td[i * sz:(i + 1) * sz]})
            continue
        if cur["items"] and len(cur["items"]) + len(td) > 1.25 * target:
            flush()
        cur["files"].append(fname)
        cur["items"].extend(td)
        if len(cur["items"]) >= target:
            flush()
    flush()

    if len(groups) >= 2 and len(groups[-1]["items"]) < 0.4 * target:
        tail = groups.pop()
        for f in tail["files"]:
            if f not in groups[-1]["files"]:
                groups[-1]["files"].append(f)
        groups[-1]["items"].extend(tail["items"])

    visible = [ln for ln in _ordered_lines(data) if not ln.get("_hidden")]
    pos_by_num = {int(ln["line_num"]): idx for idx, ln in enumerate(visible)}

    keys = (
        "line_num", "file", "name", "message", "trans_name", "trans_message",
        "is_translated", "ref_lang_1", "ref_lang_1_name", "ref_lang_2", "ref_lang_2_name",
    )

    def _rec(ln: dict, include_trans: bool) -> dict:
        r = {k: ln[k] for k in keys if k in ln}
        if not include_trans:
            r.pop("trans_name", None)
            r.pop("trans_message", None)
            r.pop("is_translated", None)
        return r

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "_stage.json"), "w", encoding="utf-8") as f:
            json.dump({
                "stage": stage,
                "target": target,
                "context_before": before,
                "context_after": after,
                "groups": len(groups),
                "prefix": prefix,
                "range": list(index_range) if index_range else None,
            }, f, ensure_ascii=False, indent=1)

    rows = []
    for n, g in enumerate(groups, 1):
        items = g["items"]
        gid = f"{prefix}{n}"
        row = {
            "group": gid if prefix else n,
            "count": len(items),
            "first_line": items[0]["line_num"],
            "last_line": items[-1]["line_num"],
            "files": g["files"],
        }
        if out_dir:
            src_path = os.path.join(out_dir, f"grp_{gid}_src.json")
            include_trans = stage in ("polish", "review")
            with open(src_path, "w", encoding="utf-8") as f:
                json.dump([_rec(it, include_trans) for it in items], f, ensure_ascii=False, indent=1)
            row["src_file"] = src_path

            p0 = pos_by_num[int(items[0]["line_num"])]
            p1 = pos_by_num[int(items[-1]["line_num"])]
            prev_all = visible[:p0]
            translated_prev = [it for it in prev_all if it.get("is_translated") and (it.get("trans_message") or "").strip()]
            # Prefer prior lines immediately before the group; if un-translated neighbor, grab recent visible lines
            ctx_before_lines = prev_all[-before:] if before > 0 else []
            if before > 0 and not any(it.get("is_translated") for it in ctx_before_lines) and translated_prev:
                ctx_before_lines = translated_prev[-before:]
            ctx_after_lines = visible[p1 + 1:p1 + 1 + after] if after > 0 else []

            ctx_path = os.path.join(out_dir, f"grp_{gid}_ctx.json")
            with open(ctx_path, "w", encoding="utf-8") as f:
                json.dump({
                    "context_type": data.get("context_type", "raw"),
                    "context_before": [_rec(it, True) for it in ctx_before_lines],
                    "context_after": [_rec(it, True) for it in ctx_after_lines],
                }, f, ensure_ascii=False, indent=1)
            row["ctx_file"] = ctx_path
        rows.append(row)
    return {"stage": stage, "target": target, "pending": sum(r["count"] for r in rows), "groups": rows}


# --------------------------------------------------------------- bundle ----
def glossary_tsv(locked_data: dict) -> str:
    lines = []
    for c in locked_data.get("characters", []):
        canon = str(c.get("canonical") or c.get("src") or "").strip()
        render = canon if c.get("keep_source") else str(c.get("render") or c.get("dst") or canon).strip()
        aliases = [str(a).strip() for a in (c.get("aliases") or []) if str(a).strip()]
        desc = str(c.get("desc") or c.get("note") or "").strip()
        if canon:
            extra = f" | aliases: {', '.join(aliases)}" if aliases else ""
            note = f" {{{desc}}}" if desc else ""
            lines.append(f"[character] {canon}\t{render}{extra}{note}")
    for t in locked_data.get("terms", []):
        src = str(t.get("src") or "").strip()
        if not src:
            continue
        dst = "=" if t.get("keep_source") or not t.get("dst") else str(t["dst"]).strip()
        cat = str(t.get("category") or "term").strip()
        desc = str(t.get("desc") or "").strip()
        note = f" {{{desc}}}" if desc else ""
        lines.append(f"[{cat}] {src}\t{dst}{note}")
    return "\n".join(lines)


def make_bundle(
    cstl_path: str,
    src_json: str,
    out_md: str,
    *,
    stage: str = "translate",
    locked_path: str | None = None,
    includes=(),
    ctx_json: str | None = None,
    out_file: str | None = None,
    newterms_file: str | None = None,
) -> dict:
    data = ensure_cstl(load_cstl(cstl_path))
    rows = load_translations(src_json)
    nums = [int(r["line_num"]) for r in rows] if rows else [0]
    task = "ai-check" if stage in ("polish", "review") else "translate"
    pinfo = project_prompt_info(data, task, len(rows))

    parts = [
        f"# {stage} bundle — {os.path.basename(src_json)} ({len(rows)} lines, {min(nums)}–{max(nums)})",
        f"Language pair: {data.get('source_lang')} -> {data.get('target_lang')} ({pinfo['language_pair']})",
        "",
    ]
    if stage == "review":
        parts += [
            "## Delivery (write once)",
            "- Review every line below against its source (`message`), context, glossary, and settled decisions.",
            "- Write JSONL findings (one JSON object per line) to the path specified in your prompt.",
            "- Never modify `.copas` or glossary files.",
            "",
        ]
    elif out_file:
        if stage == "polish":
            schema_line = '`{"line_num": N, "polished_text": "...", "polished_name": "..."|null}`'
        else:
            schema_line = '`{"line_num": N, "trans_message": "...", "trans_name": "..."|null}`'
        parts += [
            "## Delivery (write once)",
            f"- Write ALL {len(rows)} rows to `{out_file}` as JSONL (one JSON object per line): {schema_line}.",
            "- Keep exact count, order, `line_num`, speaker presence (`trans_name` non-empty iff `name` non-empty), tags, placeholders, and `\\n` markers.",
            "- Do not include `context_before` or `context_after` rows in the output.",
            "- Do not touch `.copas` or run `batch write`.",
        ]
        if newterms_file:
            parts.append(f"- Write out-of-glossary new proper nouns/terms to `{newterms_file}`, one per line as `[type] source = target {{note}}` or `source<TAB>target`.")
        parts += ["- Reply concisely with: translated count, newterms count, and up to 5 uncertain lines (line_num + note).", ""]

    card_txt = state.card(cstl_path, min(nums), max(nums))
    if card_txt:
        parts += [card_txt]

    if pinfo["instruction"].strip():
        parts += [f"## Active Project Prompt ({pinfo['prompt_source']}:{pinfo['prompt_field']})", pinfo["instruction"].strip(), ""]

    if (data.get("currentBackground") or "").strip():
        parts += ["## Story Background", data["currentBackground"].strip(), ""]

    for p in includes:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8-sig") as f:
                parts += [f"## {os.path.basename(p)}", f.read().strip(), ""]

    if locked_path and os.path.exists(locked_path):
        with open(locked_path, "r", encoding="utf-8-sig") as f:
            gl = json.load(f)
        texts = [str(r.get("message") or "") for r in rows]
        names = [str(r.get("name") or "") for r in rows if r.get("name")]
        sub_gl = glossary_mod.filter_locked(gl, texts, names)
        tsv = glossary_tsv(sub_gl)
        if tsv:
            parts += ["## Filtered Group Glossary (`=` means keep source)", "```", tsv, "```", ""]
    elif (data.get("glossary_text") or "").strip():
        parts += ["## Project Glossary", "```", data["glossary_text"].strip(), "```", ""]

    if ctx_json and os.path.exists(ctx_json):
        with open(ctx_json, "r", encoding="utf-8-sig") as f:
            ctx = json.load(f)
        for label, key in (("Context Before (READ-ONLY)", "context_before"), ("Context After (READ-ONLY — future events)", "context_after")):
            arr = ctx.get(key) if isinstance(ctx, dict) else (ctx if key == "context_before" else [])
            if arr:
                parts += [f"## {label}", "```"]
                parts += [json.dumps(r, ensure_ascii=False) for r in arr]
                parts += ["```", ""]

    parts += ["## Assigned Lines (JSONL)", "```"]
    parts += [json.dumps(r, ensure_ascii=False) for r in rows]
    parts += ["```", ""]
    txt = "\n".join(parts)
    os.makedirs(os.path.dirname(os.path.abspath(out_md)) or ".", exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(txt)
    return {"bundle": out_md, "lines": len(rows), "chars": len(txt)}


# ------------------------------------------------------------- validate ----
def validate(
    src_rows: list[dict],
    trans_rows: list[dict],
    allow_tag_mismatch: bool = False,
    cstl_path: str | None = None,
) -> dict:
    src_idx = [int(r["line_num"]) for r in src_rows]
    tr_idx = [_row_line_num(r) for r in trans_rows]
    src_by = {int(r["line_num"]): r for r in src_rows}
    hard = []
    missing = sorted(set(src_idx) - set(tr_idx))
    extra = sorted(set(tr_idx) - set(src_idx))
    dups = duplicates(trans_rows)
    if missing:
        hard.append({"kind": "missing_index", "count": len(missing), "line_nums": missing[:50]})
    if extra:
        hard.append({"kind": "extra_index", "count": len(extra), "line_nums": extra[:50]})
    if dups:
        hard.append({"kind": "duplicate_index", "count": len(dups), "line_nums": dups[:50]})

    sl, tl = "Japanese", "Indonesian"
    disable_empty = False
    exc: set[int] = set()
    rules = ()
    if cstl_path and os.path.exists(cstl_path):
        data = ensure_cstl(load_cstl(cstl_path))
        sl = data.get("source_lang", "Japanese")
        tl = data.get("target_lang", "Indonesian")
        disable_empty = bool(data.get("disable_empty_line_validation"))
        dec = state.load(cstl_path)
        exc = state.token_exceptions(dec)
        rules = state.lint_rules(dec)

    seg_hard, soft = [], {}
    for r in trans_rows:
        num = _row_line_num(r)
        src = src_by.get(num)
        if src is None:
            continue
        tmsg = _extract_trans_message(r)
        tname = _extract_trans_name(r)
        probe = {
            "line_num": num,
            "name": src.get("name"),
            "message": src.get("message") or src.get("source_text") or "",
            "trans_name": tname,
            "trans_message": "" if tmsg is None else normalize_message(tmsg),
        }
        h, s = audit.lint_line(
            probe,
            source_lang=sl,
            target_lang=tl,
            allow_tag_mismatch=allow_tag_mismatch,
            token_exceptions=exc,
            rules=rules,
            disable_empty=disable_empty,
        )
        if h:
            seg_hard.append({"line_num": num, "reasons": h})
        for w in s:
            soft.setdefault(w, []).append(num)
    if seg_hard:
        hard.append({"kind": "segment", "count": len(seg_hard), "items": seg_hard[:50]})
    common = set(src_idx) & set(tr_idx)
    order_ok = [i for i in tr_idx if i in common] == [i for i in src_idx if i in common]
    if not order_ok:
        hard.append({"kind": "order_mismatch", "count": 1})
    return {
        "ok": not hard,
        "count_src": len(src_rows),
        "count_trans": len(trans_rows),
        "order_preserved": order_ok,
        "hard": hard,
        "warnings": {k: {"count": len(v), "lines": v[:20]} for k, v in sorted(soft.items(), key=lambda kv: -len(kv[1]))},
    }


def _report_res(res: dict, verb: str = "applied") -> None:
    msg = f"{verb} {res['applied']} of {res['total']}"
    if res["rejected"]:
        msg += f"; rejected {len(res['rejected'])}"
    print(msg)
    for r in res["rejected"][:50]:
        print(f"  rejected #{r['line_num']}: {r['reason']}")
    if len(res["rejected"]) > 50:
        print(f"  ... {len(res['rejected']) - 50} more")
    if res.get("warnings"):
        print("  warnings: " + ", ".join(f"{k}={v}" for k, v in sorted(res["warnings"].items(), key=lambda kv: -kv[1])))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Batch read/split/bundle/validate/write/apply for CopasTool backups")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("read", help="Print a task packet with saved prompts, context, and lines")
    r.add_argument("cstl_path")
    r.add_argument("--size", type=int, default=100)
    rv = r.add_mutually_exclusive_group()
    rv.add_argument("--with-context", action="store_true", help="Compatibility alias for the default task packet")
    rv.add_argument("--lines-only", action="store_true", help="Emit a legacy line array without prompts/context")
    r.add_argument("--task", choices=["translate", "agent", "glossary", "ai-check"], default="translate")
    r.add_argument("--offset", type=int, default=0, help="Skip this many eligible task lines")
    r.add_argument("--file", action="append", dest="files", help="Restrict assigned lines to an exact project filename")
    r.add_argument("--context-before", type=int, help="Override saved context_lines")
    r.add_argument("--context-after", type=int, help="Override saved context_lines_after")
    r.add_argument("--brief", help="Use this project brief instead of the optional <backup>.brief.md sidecar")

    rt = sub.add_parser("read-translated", help="Print next translated batch (for polish/review)")
    rt.add_argument("cstl_path")
    rt.add_argument("--size", type=int, default=100)
    rt.add_argument("--offset", type=int, default=0)
    rt.add_argument("--file", action="append", dest="files")
    rtv = rt.add_mutually_exclusive_group()
    rtv.add_argument("--with-context", action="store_true")
    rtv.add_argument("--lines-only", action="store_true")
    rt.add_argument("--context-before", type=int)
    rt.add_argument("--context-after", type=int)
    rt.add_argument("--brief")

    sp = sub.add_parser("split", help="Plan file-aligned groups of lines for parallel workers")
    sp.add_argument("cstl_path")
    sp.add_argument("--target", type=int, default=250)
    sp.add_argument("--out-dir", help="Write grp_N_src.json + grp_N_ctx.json + _stage.json here")
    sp.add_argument("--context", "--context-before", dest="context_before", type=int, default=None)
    sp.add_argument("--context-after", type=int, default=None)
    sp.add_argument("--stage", choices=["translate", "polish", "review"], default="translate")
    sp.add_argument("--range", metavar="A-B")
    sp.add_argument("--file", action="append", dest="files")
    sp.add_argument("--prefix", default="")
    sp.add_argument("--changed-since", metavar="OLD_PROJECT")
    sp.add_argument("--include-polished", action="store_true")

    bd = sub.add_parser("bundle", help="Build one self-contained read-once bundle_<gid>.md per group")
    bd.add_argument("cstl_path")
    bd.add_argument("src_json", nargs="+", help="grp_<gid>_src.json files")
    bd.add_argument("--stage", choices=["translate", "polish", "review"], default="translate")
    bd.add_argument("--locked", help="glossary.locked.json (default <cstl_dir>/glossary.locked.json)")
    bd.add_argument("--include", nargs="*", default=[], metavar="MD")
    bd.add_argument("--out-dir")

    va = sub.add_parser("validate", help="Validate worker translation JSON/JSONL against grp_N_src.json")
    va.add_argument("src_json")
    va.add_argument("trans_json")
    va.add_argument("--allow-tag-mismatch", action="store_true")
    va.add_argument("--cache", "--project", dest="project", help="Project backup path for langpair + decisions.json")

    w = sub.add_parser("write", help="Write translations back from JSON or JSONL file(s)")
    w.add_argument("cstl_path")
    w.add_argument("translations", nargs="+", metavar="TRANS_JSON")
    w.add_argument("--expect-batch", help="Validate exact alignment, speakers, snapshot, and integrity before writing")
    w.add_argument("--force", action="store_true")
    w.add_argument("--allow-tag-mismatch", action="store_true")

    ay = sub.add_parser("apply", help="Apply fixes (full text or patches [[old, new]]), preserving status")
    ay.add_argument("cstl_path")
    ay.add_argument("files", nargs="+", metavar="FIX_JSON")
    ay.add_argument("--source", help="Provenance label: adversarial / dual / external / user / editor")
    ay.add_argument("--reason", help="Default reason for rows without one")
    ay.add_argument("--force", action="store_true")
    ay.add_argument("--allow-tag-mismatch", action="store_true")

    a = ap.parse_args(argv)
    if a.cmd == "read":
        try:
            if a.lines_only and (a.context_before is not None or a.context_after is not None or a.brief is not None):
                ap.error("context/brief overrides cannot be used with --lines-only")
            batch = read_context_batch(a.cstl_path, a.size, a.context_before, a.context_after, a.task, a.offset, a.files, a.brief)
            if a.lines_only:
                batch = batch["lines"]
        except (OSError, ValueError) as e:
            ap.error(str(e))
        print(json.dumps(batch, ensure_ascii=False))
    elif a.cmd == "read-translated":
        try:
            if a.lines_only and (a.context_before is not None or a.context_after is not None or a.brief is not None):
                ap.error("context/brief overrides cannot be used with --lines-only")
            batch = read_context_batch(a.cstl_path, a.size, a.context_before, a.context_after, "ai-check", a.offset, a.files, a.brief)
            if a.lines_only:
                batch = batch["lines"]
        except (OSError, ValueError) as e:
            ap.error(str(e))
        print(json.dumps(batch, ensure_ascii=False))
    elif a.cmd == "split":
        try:
            rng = cache_mod.parse_range(a.range)
        except ValueError as e:
            ap.error(str(e))
        data = ensure_cstl(load_cstl(a.cstl_path))
        only = cache_mod.changed_line_nums(data, a.changed_since) if a.changed_since else None
        plan = split_project(
            a.cstl_path,
            target=a.target,
            out_dir=a.out_dir,
            context_before=a.context_before,
            context_after=a.context_after,
            stage=a.stage,
            index_range=rng,
            files=a.files,
            prefix=a.prefix,
            only=only,
            include_polished=a.include_polished,
        )
        print(json.dumps(plan, ensure_ascii=False, indent=1))
    elif a.cmd == "bundle":
        cstl_dir = os.path.dirname(os.path.abspath(a.cstl_path))
        default_locked = os.path.join(cstl_dir, "glossary.locked.json")
        locked_path = a.locked or (default_locked if os.path.exists(default_locked) else None)
        for src in a.src_json:
            d = a.out_dir or os.path.dirname(os.path.abspath(src))
            gid = os.path.basename(src).removeprefix("grp_").removesuffix("_src.json")
            ctx = os.path.join(os.path.dirname(os.path.abspath(src)), f"grp_{gid}_ctx.json")
            outf = None if a.stage == "review" else os.path.join(d, f"{'trans' if a.stage == 'translate' else 'polished'}_{gid}.jsonl")
            nt = os.path.join(d, f"newterms_{gid}.txt") if a.stage == "translate" else None
            r_info = make_bundle(
                a.cstl_path,
                src,
                os.path.join(d, f"bundle_{gid}.md"),
                stage=a.stage,
                locked_path=locked_path,
                includes=a.include,
                ctx_json=ctx,
                out_file=outf,
                newterms_file=nt,
            )
            print(f"[{gid}] {r_info['lines']} lines, {r_info['chars']} chars -> {r_info['bundle']}")
    elif a.cmd == "validate":
        try:
            src_rows = load_translations(a.src_json)
            tr_rows = load_translations(a.trans_json)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            ap.error(f"cannot read input: {e}")
        rep = validate(src_rows, tr_rows, allow_tag_mismatch=a.allow_tag_mismatch, cstl_path=a.project)
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0 if rep["ok"] else 1
    elif a.cmd == "write":
        try:
            translations = load_many(a.translations)
        except Exception as e:
            ap.error(f"cannot read translations file: {e}")
        total = len(translations)
        if a.expect_batch:
            try:
                with open(a.expect_batch, encoding="utf-8-sig") as f:
                    expected = json.load(f)
                applied = write_back(a.cstl_path, translations, expected_batch=expected, allow_tag_mismatch=a.allow_tag_mismatch)
            except (OSError, ValueError, KeyError, TypeError) as e:
                ap.error(str(e))
            if applied < total:
                print(f"applied {applied} of {total} translation(s) ({total - applied} unmatched line_num)")
            else:
                print(f"applied {applied} translation(s)")
            return 0
        dups = duplicates(translations)
        if dups and not a.force:
            ap.error(f"duplicate line_num across inputs: {dups[:20]} (use --force to let the last one win)")
        res = write_gated(a.cstl_path, translations, force=a.force, allow_tag_mismatch=a.allow_tag_mismatch)
        _report_res(res, verb="applied")
        return 1 if res["rejected"] else 0
    elif a.cmd == "apply":
        try:
            rows = load_many(a.files)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            ap.error(f"cannot read fix file: {e}")
        dups = duplicates(rows)
        if dups and not a.force:
            ap.error(f"duplicate line_num across inputs: {dups[:20]} (merge them, or --force: last wins)")
        res = apply_rows(
            a.cstl_path,
            rows,
            source=a.source,
            reason=a.reason,
            force=a.force,
            allow_tag_mismatch=a.allow_tag_mismatch,
        )
        _report_res(res, verb="applied")
        print(f"  changed {len(res['changes'])} line(s)" + (f"; provenance: {a.source}" if a.source else ""))
        return 1 if res["rejected"] else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
