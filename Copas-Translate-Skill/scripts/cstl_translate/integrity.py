"""Check structural tokens before committing translated or reviewed messages."""
from __future__ import annotations

import re
from collections import Counter


TAG = re.compile(r"</?[A-Za-z][^<>\r\n]*>")
TOKEN = re.compile(
    r"</?[A-Za-z][^<>\r\n]*>"
    r"|\{[^{}\r\n]+\}"
    r"|%(?:\d+\$)?[-+#0]*\d*(?:\.\d+)?[sdifuxXocgeEG](?![A-Za-z])|%%"
    r"|\\[A-Za-z]+\[[^\]\r\n]*\]"
    r"|\\[nrt]|\\[!.$|^<>]"
)


def normalize_message(text: str) -> str:
    return text.replace("\r\n", "\\n").replace("\n", "\\n").replace("<br>", "\\n")


def message_issues(source: str, translated: str, allow_tag_mismatch: bool = False) -> list[dict]:
    source = normalize_message(source)
    translated = normalize_message(translated)
    issues = []
    if allow_tag_mismatch:
        src_toks = [t for t in TOKEN.findall(source) if not TAG.fullmatch(t)]
        dst_toks = [t for t in TOKEN.findall(translated) if not TAG.fullmatch(t)]
    else:
        src_toks = TOKEN.findall(source)
        dst_toks = TOKEN.findall(translated)
    src_tokens = Counter(src_toks)
    dst_tokens = Counter(dst_toks)
    if src_tokens != dst_tokens:
        issues.append({"kind": "structural_tokens", "missing": list((src_tokens - dst_tokens).elements()),
                       "added": list((dst_tokens - src_tokens).elements())})
    if not allow_tag_mismatch and TAG.findall(source) != TAG.findall(translated):
        issues.append({"kind": "markup_order", "detail": "markup tag order changed"})
    trailing = re.search(r"[ \t]+$", source)
    dst_trailing = re.search(r"[ \t]+$", translated)
    if trailing and (dst_trailing.group() if dst_trailing else "") != trailing.group():
        issues.append({"kind": "trailing_space", "detail": "source trailing whitespace was not preserved"})
    return issues


def check_message(
    source: str,
    translated,
    line_num,
    allow_empty: bool = False,
    allow_tag_mismatch: bool = False,
) -> None:
    if not isinstance(translated, str):
        raise ValueError(f"message on line {line_num} must be a string")
    if source.strip() and not translated.strip() and not allow_empty:
        raise ValueError(f"empty translation on line {line_num}")
    issues = message_issues(source, translated, allow_tag_mismatch=allow_tag_mismatch)
    if issues:
        raise ValueError(f"message integrity failed on line {line_num}: {issues}")


def expected_lines(expected_batch) -> list[dict]:
    lines = expected_batch.get("lines") if isinstance(expected_batch, dict) else expected_batch
    if not isinstance(lines, list) or any(not isinstance(line, dict) for line in lines):
        raise ValueError("expected batch must contain a lines array")
    nums = [line.get("line_num") for line in lines]
    if any(type(num) is not int for num in nums) or len(set(nums)) != len(nums):
        raise ValueError("expected batch must contain unique integer line numbers")
    return lines


def check_snapshot(current: dict | None, source: dict, translation: bool = False) -> None:
    keys = ["file", "name", "message"]
    if translation:
        keys += [key for key in ("trans_message", "trans_name", "is_translated") if key in source]
    if current is None or any(current.get(key) != source.get(key) for key in keys):
        raise ValueError(f"line {source['line_num']} changed since the batch was read; read a fresh batch")
