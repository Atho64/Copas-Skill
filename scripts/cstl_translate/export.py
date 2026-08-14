"""Export a .cstl bundle back to JSON / EPUB / Luca TXT on disk."""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import zipfile
from pathlib import Path

from .cstl_io import ensure_cstl, load_cstl


def export_json(cstl_path: str, out_dir: str) -> list[str]:
    data = ensure_cstl(load_cstl(cstl_path))
    by_file: dict[str, list[dict]] = {}
    for ln in data.get("lines", []):
        by_file.setdefault(ln.get("file", "output.json"), []).append(ln)
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    for fname, lns in by_file.items():
        # CSTL JSON export: {name?, message} with translated text if available
        entries = []
        for ln in lns:
            is_t = bool(ln.get("is_translated"))
            # Speaker: prefer trans_name when translated
            raw_name = (ln.get("trans_name") if is_t and ln.get("trans_name") else ln.get("name"))
            name = (str(raw_name).strip() if raw_name is not None else None)
            if name == "":
                name = None
            # Message: prefer trans_message when translated
            raw_msg = (ln.get("trans_message") if is_t and ln.get("trans_message") is not None else ln.get("message", ""))
            msg = str(raw_msg).replace("\\n", "\n")
            e: dict = {"message": msg}
            if name is not None:
                e["name"] = name
            entries.append(e)
        # File name: normalize to .json
        base = os.path.basename(fname) or "output.json"
        if not base.lower().endswith(".json"):
            base = os.path.splitext(base)[0] + ".json"
        out_path = os.path.join(out_dir, base)
        # Dedupe file names
        suffix = 1
        stem, ext = os.path.splitext(out_path)
        while os.path.exists(out_path):
            suffix += 1
            out_path = f"{stem}_{suffix}{ext}"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        written.append(out_path)
    # If multiple files, also write a zip
    if len(written) > 1:
        zip_path = os.path.join(out_dir, f"{Path(cstl_path).stem}_export.zip")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in written:
                zf.write(p, arcname=os.path.basename(p))
        written.append(zip_path)
    return written


def export_epub(cstl_path: str, out_dir: str, epub_source_path: str | None = None) -> list[str]:
    data = ensure_cstl(load_cstl(cstl_path))
    if data.get("projectType") != "epub":
        raise SystemExit("Project is not EPUB type — use --format json or luca instead.")
    # Resolve source epub bytes: embedded epub_source or external file
    epub_bytes: bytes | None = None
    src = data.get("epub_source") or {}
    if isinstance(src, dict) and src.get("data"):
        try:
            epub_bytes = base64.b64decode(src["data"])
        except Exception:
            pass
    if epub_bytes is None and epub_source_path and os.path.exists(epub_source_path):
        with open(epub_source_path, "rb") as f:
            epub_bytes = f.read()
    if epub_bytes is None:
        raise SystemExit("No EPUB source bytes found — pass --epub-source /path/to/original.epub or parse via this skill so bytes are embedded.")

    try:
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError:
        raise SystemExit("beautifulsoup4 + lxml required for EPUB export (pip install beautifulsoup4 lxml)")

    # Group translated text by file
    by_file: dict[str, list[dict]] = {}
    for ln in data.get("lines", []):
        by_file.setdefault(ln.get("file", ""), []).append(ln)

    # Patch each xhtml/html file in the epub zip in-place
    inp = io.BytesIO(epub_bytes)
    out_buf = io.BytesIO()
    import copy as _copy
    with zipfile.ZipFile(inp, "r") as zin, zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            raw = zin.read(info.filename)
            if info.filename in by_file:
                raw = _patch_epub_file(raw, info.filename, by_file[info.filename])
                # Preserve Store for mimetype
                comp = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
                zout.writestr(zipfile.ZipInfo(info.filename), raw, compress_type=comp)
            else:
                zout.writestr(info, raw)
    os.makedirs(out_dir, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*]', "_", data.get("projectName") or "export").strip() or "export"
    out_path = os.path.join(out_dir, f"{safe}_tl.epub")
    with open(out_path, "wb") as f:
        f.write(out_buf.getvalue())
    return [out_path]


def _patch_epub_file(raw_html: bytes, href: str, lines: list[dict]) -> bytes:
    from bs4 import BeautifulSoup
    # Detect tag selector from project (default p)
    text = raw_html.decode("utf-8", errors="replace")
    xml_header = ""
    m = re.match(r"^\s*<\?xml.*?\?>\s*", text, re.I | re.S)
    if m:
        xml_header = m.group(0)
        text = text[m.end():]
    soup = BeautifulSoup(text, "lxml")
    # We mirror parse selector — default to p, but exported lines correspond 1:1 to elements
    # that parse found. We patch in document order.
    els = soup.find_all("p")
    # If number matches, patch those; otherwise try broader
    if len(els) != len(lines):
        # Fallback: all tags with text
        els = [el for el in soup.find_all(True) if (el.get_text() or "").strip()]
        # Prefer leaf p-like
        p_like = [el for el in els if el.name in ("p", "div", "span", "li")]
        if p_like and abs(len(p_like) - len(lines)) < abs(len(els) - len(lines)):
            els = p_like
    j = 0
    for el in els:
        if j >= len(lines):
            break
        if not (el.get_text() or "").strip():
            continue
        ln = lines[j]
        j += 1
        if not ln.get("is_translated"):
            continue
        t = (ln.get("trans_message") or "").replace("\\n", "\n").replace("<br>", "\n")
        if not t:
            continue
        # Preserve inline — simplest: replace text content
        el.clear()
        # Handle embedded \n as <br>
        parts = t.split("\n")
        for idx, part in enumerate(parts):
            if idx > 0:
                el.append(soup.new_tag("br"))
            el.append(part)
    html_out = str(soup)
    if xml_header and not html_out.lstrip().startswith("<?xml"):
        html_out = xml_header + html_out
    return html_out.encode("utf-8")


def export_luca(cstl_path: str, out_dir: str) -> list[str]:
    data = ensure_cstl(load_cstl(cstl_path))
    if data.get("projectType") != "luca":
        raise SystemExit("Project is not Luca type — use --format json instead.")
    by_file: dict[str, list[dict]] = {}
    for ln in data.get("lines", []):
        by_file.setdefault(ln.get("file", ""), []).append(ln)
    raw_files: dict[str, list[str]] = data.get("lucaRawFiles") or {}
    raw_buffers: dict[str, str] = data.get("lucaRawBuffers") or {}
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    for fname, lns in by_file.items():
        raw_lines = list(raw_files.get(fname, []))
        if not raw_lines and fname in raw_buffers:
            try:
                rb = base64.b64decode(raw_buffers[fname])
                raw_lines = rb.decode("utf-8", errors="replace").splitlines()
            except Exception:
                raw_lines = []
        if not raw_lines:
            # Reconstruct minimally from luca_raw per line
            raw_lines = [ln.get("luca_raw") or "" for ln in lns]
            # luca_raw_index may not be contiguous
            max_idx = max((ln.get("luca_raw_index", 0) or 0) for ln in lns) if lns else 0
            out = [""] * (max_idx + 1)
            for ln in lns:
                idx = ln.get("luca_raw_index")
                if idx is not None and 0 <= idx < len(out):
                    out[idx] = ln.get("luca_raw") or out[idx]
            raw_lines = out
        # Apply translations into raw_lines by luca_raw_index
        for ln in lns:
            if not ln.get("is_translated"):
                continue
            idx = ln.get("luca_raw_index")
            if idx is None or not (0 <= idx < len(raw_lines)):
                continue
            raw = raw_lines[idx]
            # Patch MESSAGE payload: first quoted string after '('
            m = re.search(r'(\bMESSAGE(?:_WAIT)?\s*\()(.*)(\))', raw, re.I | re.S)
            if not m:
                continue
            # Build export text like CSTL's luca-engine
            heavy_open = "\u275D"
            heavy_close = "\u275E"
            name = (ln.get("trans_name") or ln.get("name") or "").strip()
            tmsg = (ln.get("trans_message") or "").replace("\\n", "\n")
            payload = f"@{name}@{tmsg}" if name else tmsg
            if ln.get("luca_heavy_quotes"):
                payload = f"{heavy_open}{payload}{heavy_close}"
            # Replace first quoted payload in args
            args_str = m.group(2)
            # Naive: replace first "..." occurrence
            qm = re.search(r'"(?:\\.|[^"\\])*"', args_str)
            if qm:
                args_str = args_str[:qm.start()] + json.dumps(payload, ensure_ascii=False) + args_str[qm.end():]
            raw_lines[idx] = m.group(1) + args_str + m.group(3)
        out_path = os.path.join(out_dir, os.path.basename(fname) or "export.txt")
        suffix = 1
        stem, ext = os.path.splitext(out_path)
        while os.path.exists(out_path):
            suffix += 1
            out_path = f"{stem}_{suffix}{ext}"
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(raw_lines))
        written.append(out_path)
    if len(written) > 1:
        zip_path = os.path.join(out_dir, f"{Path(cstl_path).stem}_luca_export.zip")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in written:
                zf.write(p, arcname=os.path.basename(p))
        written.append(zip_path)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description="Export .cstl to JSON/EPUB/Luca")
    ap.add_argument("--cstl", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--format", dest="fmt", choices=["json", "epub", "luca", "auto"], default="auto")
    ap.add_argument("--epub-source", default=None, help="Original EPUB file if not embedded")
    a = ap.parse_args(argv)
    fmt = a.fmt
    if fmt == "auto":
        d = ensure_cstl(load_cstl(a.cstl))
        pt = d.get("projectType") or "json"
        fmt = "json" if pt == "json" else pt
    if fmt == "json":
        out = export_json(a.cstl, a.output)
    elif fmt == "epub":
        out = export_epub(a.cstl, a.output, epub_source_path=a.epub_source)
    elif fmt == "luca":
        out = export_luca(a.cstl, a.output)
    else:
        ap.error(f"unknown format {fmt}")
    for p in out:
        print(p)


if __name__ == "__main__":
    main()
