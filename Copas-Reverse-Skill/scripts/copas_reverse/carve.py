"""Encoding-aware text carving from binary game files, with exact byte offsets.

Offsets recorded here can later be used by copas_reverse.patch for same-length
injection. Read-only: this module never writes to the scanned file.

Usage:
    python -m copas_reverse.carve scan <file-or-dir> [--out file.json]
    python -m copas_reverse.carve file <file> --encoding cp932 [--min-len 4]
            [--require-cjk] [--out file.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

MAX_RUN = 20000  # safety cap for a single carved run
SUGGEST_SAMPLE = 2 * 1024 * 1024

# CP932 ranges: printable ASCII 0x20-0x7E, half-width kana 0xA1-0xDF,
# lead bytes 0x81-0x9F / 0xE0-0xFC with trail 0x40-0x7E / 0x80-0xFC.
CP932_LEAD = set(range(0x81, 0xA0)) | set(range(0xE0, 0xFD))
CP932_TRAIL_OK = set(range(0x40, 0x7F)) | set(range(0x80, 0xFD))


def _cp932_char_at(data: bytes, i: int) -> int:
    """Return width of the CP932 char at data[i] (0 = not a char)."""
    b = data[i]
    if 0x20 <= b <= 0x7E or 0xA1 <= b <= 0xDF:
        return 1
    if b in CP932_LEAD and i + 1 < len(data) and data[i + 1] in CP932_TRAIL_OK:
        return 2
    return 0


def _walk_cp932(data: bytes, min_len: int) -> list[dict]:
    runs: list[dict] = []
    start = -1
    buf = bytearray()
    i, n = 0, len(data)
    while i < n:
        w = _cp932_char_at(data, i)
        if w:
            if start < 0:
                start, buf = i, bytearray()
            buf += data[i:i + w]
            i += w
        else:
            if start >= 0 and len(buf.decode("cp932", "replace")) >= min_len:
                runs.append(_run(start, buf, "cp932"))
            start = -1
            i += 1
    if start >= 0 and len(buf.decode("cp932", "replace")) >= min_len:
        runs.append(_run(start, buf, "cp932"))
    return runs


def _utf8_char_at(data: bytes, i: int) -> int:
    b = data[i]
    if b < 0x80:
        return 1 if 0x20 <= b <= 0x7E else 0
    if 0xC2 <= b <= 0xDF and i + 1 < len(data) and 0x80 <= data[i + 1] <= 0xBF:
        return 2
    if 0xE0 <= b <= 0xEF and i + 2 < len(data) and all(0x80 <= data[i + k] <= 0xBF for k in (1, 2)):
        return 3
    if 0xF0 <= b <= 0xF4 and i + 3 < len(data) and all(0x80 <= data[i + k] <= 0xBF for k in (1, 2, 3)):
        return 4
    return 0


def _walk_utf8(data: bytes, min_len: int) -> list[dict]:
    runs: list[dict] = []
    start = -1
    buf = bytearray()
    i, n = 0, len(data)
    while i < n:
        w = _utf8_char_at(data, i)
        if w:
            if start < 0:
                start, buf = i, bytearray()
            buf += data[i:i + w]
            i += w
        else:
            if start >= 0 and len(buf.decode("utf-8", "replace")) >= min_len:
                runs.append(_run(start, buf, "utf-8"))
            start = -1
            i += 1
    if start >= 0 and len(buf.decode("utf-8", "replace")) >= min_len:
        runs.append(_run(start, buf, "utf-8"))
    return runs


# Codepoint classes considered printable for UTF-16 carving: ASCII,
# Latin-1 supplement, CJK, kana, full-width forms, general punctuation.
def _utf16_printable(cp: int) -> bool:
    return (0x20 <= cp <= 0x7E or 0xA0 <= cp <= 0x2FFF or 0x3000 <= cp <= 0xD7FF
            or 0xF900 <= cp <= 0xFAFF or 0xFF00 <= cp <= 0xFFEF)


def _walk_utf16le(data: bytes, min_len: int, parity: int) -> list[dict]:
    runs: list[dict] = []
    start = -1
    buf = bytearray()
    i = parity
    n = len(data)
    while i + 1 < n:
        cp = data[i] | (data[i + 1] << 8)
        if _utf16_printable(cp):
            if start < 0:
                start, buf = i, bytearray()
            buf += data[i:i + 2]
            i += 2
        else:
            if start >= 0 and len(buf.decode("utf-16-le", "replace")) >= min_len:
                runs.append(_run(start, buf, "utf-16-le"))
            start = -1
            i += 2
    if start >= 0 and len(buf.decode("utf-16-le", "replace")) >= min_len:
        runs.append(_run(start, buf, "utf-16-le"))
    return runs


def _run(offset: int, buf: bytearray, encoding: str) -> dict:
    text = buf.decode(encoding, "replace")
    has_cjk = any(0x3000 <= ord(c) <= 0xD7FF or 0xFF00 <= ord(c) <= 0xFFEF for c in text)
    return {
        "offset": offset,
        "length": len(buf),
        "hex": buf.hex(),
        "text": text,
        "has_cjk": has_cjk,
    }


def carve_file(path: str, encoding: str = "cp932", min_len: int = 4,
               require_cjk: bool = False) -> dict:
    with open(path, "rb") as f:
        data = f.read()
    if encoding == "cp932":
        runs = _walk_cp932(data, min_len)
    elif encoding == "utf-8":
        runs = _walk_utf8(data, min_len)
    elif encoding == "utf-16-le":
        runs = _walk_utf16le(data, min_len, 0) + _walk_utf16le(data, min_len, 1)
        runs.sort(key=lambda r: r["offset"])
    else:
        raise SystemExit(f"unsupported encoding: {encoding}")
    if require_cjk:
        runs = [r for r in runs if r["has_cjk"]]
    for r in runs:
        r["hex"] = r["hex"][:512]  # keep reports readable; offset+length are exact
    return {
        "file": str(path),
        "size": len(data),
        "encoding": encoding,
        "min_len": min_len,
        "require_cjk": require_cjk,
        "run_count": len(runs),
        "runs": runs,
    }


def suggest_encodings(path: str) -> dict:
    """Try decoders over a sample; report which encodings look plausible."""
    with open(path, "rb") as f:
        sample = f.read(SUGGEST_SAMPLE)
    out: dict = {"file": str(path), "size": os.path.getsize(path), "candidates": {}}
    for enc in ("utf-8", "cp932", "utf-16-le"):
        try:
            text = sample.decode(enc)
        except (UnicodeDecodeError, ValueError):
            out["candidates"][enc] = {"decodes": False}
            continue
        cjk = sum(1 for c in text if 0x3000 <= ord(c) <= 0xD7FF)
        hwkana = sum(1 for c in text if 0xFF61 <= ord(c) <= 0xFF9F)
        out["candidates"][enc] = {
            "decodes": True,
            "cjk_ratio": round(cjk / max(len(text), 1), 4),
            "hw_kana_ratio": round(hwkana / max(len(text), 1), 4),
        }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Encoding-aware text carving with byte offsets")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="suggest plausible encodings per file")
    p_scan.add_argument("path")
    p_scan.add_argument("--out")

    p_file = sub.add_parser("file", help="carve text runs from one file")
    p_file.add_argument("path")
    p_file.add_argument("--encoding", default="cp932", choices=["cp932", "utf-8", "utf-16-le"])
    p_file.add_argument("--min-len", type=int, default=4)
    p_file.add_argument("--require-cjk", action="store_true",
                        help="keep only runs containing CJK/kana/full-width chars")
    p_file.add_argument("--out")

    a = ap.parse_args(argv)
    if a.cmd == "scan":
        p = Path(a.path)
        results = []
        files = [p] if p.is_file() else sorted(
            f for f in p.rglob("*") if f.is_file() and f.stat().st_size < 512 * 1024 * 1024)
        for f in files:
            results.append(suggest_encodings(str(f)))
        payload = {"scanned": len(results), "results": results}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        result = carve_file(a.path, a.encoding, a.min_len, a.require_cjk)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        print(f"carved {result['run_count']} run(s) from {a.path} "
              f"[encoding={a.encoding}]", file=sys.stderr)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"written: {a.out}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
