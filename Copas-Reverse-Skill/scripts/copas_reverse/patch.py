"""Same-length byte patching driven by carve offsets and VNTP translations.

The safe default for unknown engines: rewrite text in place, never growing the
file. Overflowing translations are refused (or padded away), so file length,
offset tables, and pointers stay untouched.

Spec format (metadata/patch_<name>.json):
{
  "file": "data/script.bin",     // relative to the game root
  "encoding": "cp932",
  "pad": "space",                // none | space | fullwidth | zero
  "newline_hex": "0a",           // optional: replaces "\\n" in texts before encoding
  "entries": [
    {"offset": 1234, "orig_len": 40, "orig_hex": "aabb…",   // bytes BEFORE patching
     "kind": "message", "line": 7, "text": "Terjemahan baru"}
  ]
}

Usage:
    python -m copas_reverse.patch build-spec --carve metadata/carve_X.json \
        --input id_input/X.json --output id_output/X.json \
        --file-label data/script.bin --encoding cp932 --out metadata/patch_X.json
    python -m copas_reverse.patch apply --spec metadata/patch_X.json \
        --src original/data/script.bin --out patched/data/script.bin
    python -m copas_reverse.patch verify --spec metadata/patch_X.json \
        --src original/data/script.bin --dst patched/data/script.bin
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PADS = ("none", "space", "fullwidth", "zero")


def _norm(s: str) -> str:
    return s.replace("\u3000", " ").replace("\r\n", "\n").strip()


def _pad_bytes(pad: str, encoding: str, count: int) -> bytes:
    if count <= 0:
        return b""
    if pad == "space":
        return b" " * count
    if pad == "zero":
        return b"\x00" * count
    if pad == "fullwidth":
        unit = "\u3000".encode(encoding)
        full, rem = divmod(count, len(unit))
        return unit * full + b" " * rem  # half-width space for the remainder
    if pad == "none":
        raise SystemExit("pad 'none' leaves a length mismatch — pick a pad strategy")
    raise SystemExit(f"unknown pad: {pad}")


def _encode_text(text: str, encoding: str, newline_hex: str | None) -> bytes:
    t = text
    if newline_hex:
        t = t.replace("\\n", "\n").replace("\n", bytes.fromhex(newline_hex).decode("latin-1"))
    try:
        return t.encode(encoding)
    except UnicodeEncodeError as e:
        bad = e.object[e.start:e.end] if isinstance(e.object, bytes) else t
        raise SystemExit(
            f"cannot encode {bad!r} as {encoding} — see "
            f"references/guides/encoding_and_display.md for the character policy")


def build_spec(carve_path: str, input_path: str, output_path: str | None,
               file_label: str, encoding: str, pad: str,
               newline_hex: str | None, out_path: str) -> dict:
    from .carve import carve_file  # reuse the walker for consistent normalization
    from .vntp import load_vntp

    with open(carve_path, "r", encoding="utf-8") as f:
        carve = json.load(f)
    runs = carve["runs"]  # hex may be capped at 512 chars for very long runs; orig_len stays exact
    src_entries = load_vntp(input_path)
    out_entries = load_vntp(output_path) if output_path else src_entries
    if len(src_entries) != len(out_entries):
        raise SystemExit(f"line count mismatch: {len(src_entries)} input vs {len(out_entries)} output")

    used: set[int] = set()
    entries: list[dict] = []
    unmatched: list[dict] = []

    def find_run(text: str) -> int | None:
        want = _norm(text)
        if not want:
            return None
        for ri, r in enumerate(runs):
            if ri in used:
                continue
            if _norm(r["text"]) == want:
                return ri
        return None

    def find_run_seq(segments: list[str]) -> list[int] | None:
        """Match a multi-segment message (\\n-split) to consecutive unused runs —
        engines usually store each display line in its own slot."""
        segs = [s for s in segments if _norm(s)]
        if len(segs) < 2:
            return None
        for j in range(len(runs)):
            if j in used:
                continue
            idxs: list[int] = []
            k = j
            ok = True
            for seg in segs:
                while k < len(runs) and k in used:
                    k += 1
                if k >= len(runs) or _norm(runs[k]["text"]) != _norm(seg):
                    ok = False
                    break
                idxs.append(k)
                k += 1
            if ok:
                return idxs
        return None

    for i, (src, dst) in enumerate(zip(src_entries, out_entries), 1):
        matched_any = False
        for kind, key in (("message", "message"), ("name", "name")):
            if key == "name" and src.get("name") is None:
                continue
            src_text = src.get(key)
            if not isinstance(src_text, str) or not src_text.strip():
                continue
            new_text = (dst.get(key) if dst.get(key) is not None else src_text)
            ri = find_run(src_text)
            if ri is not None:
                used.add(ri)
                r = runs[ri]
                entries.append({
                    "offset": r["offset"],
                    "orig_len": r["length"],
                    "orig_hex": r["hex"][:512],
                    "kind": kind,
                    "line": i,
                    "text": new_text,
                })
                matched_any = True
                continue
            idxs = find_run_seq(src_text.split("\n")) if "\n" in src_text else None
            if idxs is None:
                unmatched.append({"line": i, "kind": kind, "text": src_text})
                continue
            dst_segs = str(new_text).split("\n")
            if len(dst_segs) != len(idxs):
                print(f"warning: line {i}: segment count changed "
                      f"({len(idxs)} -> {len(dst_segs)}); patching the common prefix only",
                      file=sys.stderr)
            for r_idx, seg_text in zip(idxs, dst_segs):
                used.add(r_idx)
                r = runs[r_idx]
                entries.append({
                    "offset": r["offset"],
                    "orig_len": r["length"],
                    "orig_hex": r["hex"][:512],
                    "kind": kind,
                    "line": i,
                    "text": seg_text,
                })
                matched_any = True
        if not matched_any and not (src.get("message") or "").strip():
            continue

    spec = {
        "file": file_label,
        "encoding": encoding,
        "pad": pad,
        "newline_hex": newline_hex,
        "carve_source": carve_path,
        "entry_count": len(entries),
        "entries": entries,
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    summary = {
        "spec": out_path,
        "file": file_label,
        "matched": len(entries),
        "unmatched": len(unmatched),
        "unmatched_lines": unmatched[:50],
        "changed_lines": sum(
            1 for s, d in zip(src_entries, out_entries)
            if (d.get("message") or "") != (s.get("message") or "")
            or (d.get("name") or "") != (s.get("name") or "")),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if unmatched:
        print(f"warning: {len(unmatched)} source string(s) had no carve-run match; "
              f"they will NOT be patched — check the carve dump or extract "
              f"those strings with an engine-specific extractor", file=sys.stderr)
    return spec


def apply_spec(spec_path: str, src_path: str, out_path: str,
               pad_override: str | None = None, truncate: bool = False) -> None:
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    with open(src_path, "rb") as f:
        data = bytearray(f.read())
    encoding = spec["encoding"]
    pad = pad_override or spec.get("pad") or "space"
    newline_hex = spec.get("newline_hex")
    overflow: list[str] = []
    for e in spec["entries"]:
        off, orig_len = e["offset"], e["orig_len"]
        if off + orig_len > len(data):
            raise SystemExit(f"entry line {e.get('line')}: range {off}+{orig_len} "
                             f"exceeds file size {len(data)}")
        orig_hex = e.get("orig_hex")
        if orig_hex:
            expected = bytes.fromhex(orig_hex)
            if data[off:off + len(expected)] != expected:
                raise SystemExit(
                    f"entry line {e.get('line')} @ {off}: original bytes do not match "
                    f"orig_hex — the source file changed or offsets are stale")
        enc = _encode_text(e["text"], encoding, newline_hex)
        if len(enc) > orig_len:
            if not truncate:
                overflow.append(
                    f"line {e.get('line')} @ {off}: needs {len(enc)} bytes, "
                    f"only {orig_len} available ({e['text'][:40]!r})")
                continue
            enc = enc[:orig_len]
        payload = enc + _pad_bytes(pad, encoding, orig_len - len(enc))
        data[off:off + orig_len] = payload
    if overflow:
        print("OVERFLOW — these lines are too long for their original slots:", file=sys.stderr)
        for line in overflow[:50]:
            print("  " + line, file=sys.stderr)
        print("Shorten the translations (see references/guides/writeback_and_verify.md) "
              "or re-extract with a structure-aware engine extractor.", file=sys.stderr)
        sys.exit(1)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    print(f"applied {len(spec['entries'])} patch entrie(s) -> {out_path} "
          f"(size unchanged: {len(data)} bytes)")


def verify_patch(spec_path: str, src_path: str, dst_path: str) -> None:
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    with open(src_path, "rb") as f:
        src = f.read()
    with open(dst_path, "rb") as f:
        dst = f.read()
    problems: list[str] = []
    if len(src) != len(dst):
        problems.append(f"file size changed: {len(src)} -> {len(dst)}")
    allowed: list[tuple[int, int]] = []
    for e in spec["entries"]:
        off, ln = e["offset"], e["orig_len"]
        allowed.append((off, off + ln))
        enc = _encode_text(e["text"], spec["encoding"], spec.get("newline_hex"))
        payload = enc + _pad_bytes(spec.get("pad") or "space", spec["encoding"], ln - len(enc))
        if len(payload) != ln:
            problems.append(f"entry line {e.get('line')}: payload length {len(payload)} != slot {ln}")
        elif dst[off:off + ln] != payload:
            problems.append(f"entry line {e.get('line')} @ {off}: patched bytes differ from spec")
    # No changes outside spec ranges
    allowed_sorted = sorted(allowed)
    merged: list[list[int]] = []
    for a, b in allowed_sorted:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    i = 0
    outside = []
    while i < len(src):
        if i < len(dst) and src[i] != dst[i]:
            if not any(a <= i < b for a, b in merged):
                outside.append(i)
            j = i
            while j < len(src) and src[j] != dst[j]:
                j += 1
            i = j
        else:
            i += 1
    if outside:
        problems.append(f"{len(outside)} changed byte(s) OUTSIDE spec ranges, "
                        f"first at offset {outside[0]}")
    for p in problems[:50]:
        print("PROBLEM: " + p, file=sys.stderr)
    if problems:
        sys.exit(1)
    print(f"verify OK: {len(spec['entries'])} entries, size {len(src)} bytes, "
          f"all changes inside declared ranges")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Same-length byte patching for VN scripts")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_bs = sub.add_parser("build-spec", help="match carved runs to VNTP input/output lines")
    p_bs.add_argument("--carve", required=True)
    p_bs.add_argument("--input", required=True, help="id_input/<name>.json")
    p_bs.add_argument("--output", default=None, help="id_output/<name>.json (default: identity)")
    p_bs.add_argument("--file-label", required=True, help="game-relative path of the binary")
    p_bs.add_argument("--encoding", default="cp932")
    p_bs.add_argument("--pad", default="space", choices=list(PADS))
    p_bs.add_argument("--newline-hex", default=None, help="e.g. 0a to turn \\n into 0x0A")
    p_bs.add_argument("--out", required=True)

    p_ap = sub.add_parser("apply", help="apply a spec to a COPY of the original file")
    p_ap.add_argument("--spec", required=True)
    p_ap.add_argument("--src", required=True, help="pristine original file (read-only)")
    p_ap.add_argument("--out", required=True, help="patched copy destination")
    p_ap.add_argument("--pad", default=None, choices=list(PADS))
    p_ap.add_argument("--truncate", action="store_true",
                      help="DANGEROUS: cut overflowing text instead of failing")

    p_ver = sub.add_parser("verify", help="confirm a patched file matches its spec exactly")
    p_ver.add_argument("--spec", required=True)
    p_ver.add_argument("--src", required=True)
    p_ver.add_argument("--dst", required=True)

    a = ap.parse_args(argv)
    if a.cmd == "build-spec":
        build_spec(a.carve, a.input, a.output, a.file_label, a.encoding,
                   a.pad, a.newline_hex, a.out)
    elif a.cmd == "apply":
        apply_spec(a.spec, a.src, a.out, a.pad, a.truncate)
    else:
        verify_patch(a.spec, a.src, a.dst)


if __name__ == "__main__":
    main()
