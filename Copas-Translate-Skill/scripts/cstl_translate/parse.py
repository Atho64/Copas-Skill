"""Parse VN inputs or read CopasTool project backups into a project bundle."""
from __future__ import annotations

import base64
import glob as globmod
import json
import os
import re
import zipfile
from pathlib import Path

from .cstl_io import build_minimal_cstl, ensure_cstl, is_project_backup_path, load_cstl, save_cstl


def _normalize_file_base(p: str) -> str:
    # Mirrors CSTL's normalizeFileBaseName
    return os.path.basename(p).strip()


def _parse_json_entries(arr, file_name: str, start_line: int) -> list[dict]:
    if not isinstance(arr, list):
        raise ValueError(f"File {file_name} is not a JSON array")
    out: list[dict] = []
    cur = start_line
    for entry in arr:
        if not isinstance(entry, dict) or "message" not in entry:
            continue
        out.append({
            "line_num": cur,
            "file": file_name,
            "name": (None if entry.get("name") is None else str(entry["name"]).replace("\r\n", "\\n").replace("\n", "\\n").strip()) or None,
            "message": str(entry.get("message", "")).replace("\r\n", "\\n").replace("\n", "\\n").strip(),
            "trans_name": None,
            "trans_message": None,
            "is_translated": False,
        })
        cur += 1
    return out


def _parse_json_file(path: str, cur: int) -> tuple[list[dict], str]:
    base = _normalize_file_base(path)
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return _parse_json_entries(data, base, cur), base


def _read_text_file(path: str) -> str:
    # Try utf-8 then latin-1 fallback (Luca txt may be shift-jis/latin-1 bytes)
    for enc in ("utf-8-sig", "utf-8", "cp932", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


# --- Luca TXT minimal parser (preserves raw behavior for round-trip) ---

def _split_luca_args(s: str) -> list[str]:
    args: list[str] = []
    cur = ""
    in_str = False
    depth = 0
    for i, ch in enumerate(s):
        if ch == '"' and not in_str:
            in_str = True; cur += ch; continue
        if ch == '"' and in_str:
            in_str = False; cur += ch; continue
        if in_str:
            cur += ch; continue
        if ch == '(':
            depth += 1; cur += ch; continue
        if ch == ')':
            depth -= 1; cur += ch; continue
        if ch == ',' and depth == 0:
            args.append(cur.strip()); cur = ""; continue
        cur += ch
    if cur.strip():
        args.append(cur.strip())
    return args


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _parse_luca_txt(text: str, file_name: str, start_line: int) -> list[dict]:
    lines = text.splitlines()
    out: list[dict] = []
    cur = start_line
    # Support both MESSAGE and MESSAGE_WAIT; payload at args[1] for Tomoyo style
    # and args[2] for SP Steam multi-lang; we store full luca state for export.
    for idx, raw in enumerate(lines):
        m = re.match(r"^\s*(?:[A-Za-z_]\w*\s*:\s*)?(MESSAGE(?:_WAIT)?)\s*\(", raw, re.I)
        if not m:
            continue
        cmd = m.group(1).upper()
        try:
            paren_start = raw.index("(")
            paren_end = raw.rindex(")")
        except ValueError:
            continue
        args = _split_luca_args(raw[paren_start + 1:paren_end])
        if len(args) < 2:
            continue
        # Heuristic: source jp at args[1] if quoted, else args[0]
        payload = None
        heavy = False
        if len(args) >= 2 and args[1].strip().startswith('"'):
            payload = _unquote(args[1])
        elif args[0].strip().startswith('"'):
            payload = _unquote(args[0])
        else:
            continue
        # Parse @name@ payload if present
        name = None
        msg = payload
        heavy_open = "\u275D"
        heavy_close = "\u275E"
        if msg.startswith(heavy_open) and msg.endswith(heavy_close):
            heavy = True
            msg = msg[len(heavy_open):-len(heavy_close)]
        at = re.match(r"^@([^@]+)@(.*)$", msg, re.S)
        if at:
            name = at.group(1).strip() or None
            msg = at.group(2).strip()
            if msg.startswith(heavy_open) and msg.endswith(heavy_close):
                heavy = True
                msg = msg[len(heavy_open):-len(heavy_close)]
        if not msg and not name:
            continue
        out.append({
            "line_num": cur,
            "file": file_name,
            "name": name,
            "message": msg,
            "trans_name": None,
            "trans_message": None,
            "is_translated": False,
            "luca_command": cmd,
            "luca_raw_index": idx,
            "luca_raw": raw,
            "luca_heavy_quotes": heavy,
            "luca_pre": raw[:paren_start + 1],
            "luca_text_prefix": None,
        })
        cur += 1
        # SELECT handling — each choice as separate line
        if cmd == "SELECT":
            # Minimal: args[0]=jp "$d"-joined, expand
            jp_choices = _unquote(args[0]).split("$d")
            for ci, choice_text in enumerate(jp_choices):
                choice_text = choice_text.strip()
                if not choice_text:
                    continue
                # Avoid double-counting: MESSAGE already handled above
                # For SELECT we overwrite last entry to be choice-expanded
                pass
    return out


def parse_inputs(
    input_path: str,
    project_type: str = "auto",
    epub_tags: str = "p",
    name: str = "Imported Project",
    source_lang: str | None = None,
    target_lang: str | None = None,
) -> dict:
    p = Path(input_path)
    data = build_minimal_cstl(name, project_type if project_type != "auto" else "json", source_lang or "Japanese", target_lang or "Indonesian")
    lines: list[dict] = []
    imported: list[str] = []
    cur = 1

    def detect_type(path: str) -> str:
        ext = Path(path).suffix.lower()
        if ext == ".epub":
            return "epub"
        if ext in (".copas", ".cstl"):
            return "cstl"
        # Luca detection: .txt that contains MESSAGE(
        if ext == ".txt":
            try:
                sample = _read_text_file(path)[:4000]
                if re.search(r"\bMESSAGE(?:_WAIT)?\s*\(", sample, re.I):
                    return "luca"
            except Exception:
                pass
            return "luca" if project_type == "luca" else "txt"
        return "json"

    # Current CopasTool backups are .copas JSON; legacy .cstl remains supported.
    # Large custom-parser projects use .copas.zip with project.json + custom_sources/.
    if p.is_file() and is_project_backup_path(str(p)):
        loaded = ensure_cstl(load_cstl(str(p)))
        # Preserve project metadata unless the caller explicitly overrides it.
        if name and name != "Imported Project":
            loaded["projectName"] = name
        if source_lang is not None:
            loaded["source_lang"] = source_lang
        if target_lang is not None:
            loaded["target_lang"] = target_lang
        return loaded

    # Collect files
    files: list[str] = []
    if p.is_file():
        if p.suffix.lower() == ".zip":
            # ZIP of JSONs
            with zipfile.ZipFile(str(p), "r") as zf:
                for info in zf.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".json"):
                        continue
                    base = _normalize_file_base(info.filename)
                    if base in imported:
                        continue
                    content = json.loads(zf.read(info.filename).decode("utf-8-sig"))
                    chunk = _parse_json_entries(content, base, cur)
                    if chunk:
                        lines.extend(chunk)
                        cur += len(chunk)
                        imported.append(base)
            data["lines"] = lines
            data["imported_files"] = imported
            data["file_order"] = list(imported)
            data["projectType"] = "json"
            return data
        files = [str(p)]
    elif p.is_dir():
        # All relevant files in dir (recursive for luca/json)
        for ext in ("*.json", "*.txt", "*.epub"):
            files.extend(globmod.glob(os.path.join(str(p), "**", ext), recursive=True))
        if not files:
            files = [str(x) for x in p.iterdir() if x.is_file()]
        files = sorted(set(files))

    if not files:
        raise SystemExit(f"No files found at {input_path}")

    # Determine project type
    if project_type != "auto":
        ptype = project_type
    else:
        # Infer from files
        has_epub = any(f.lower().endswith(".epub") for f in files)
        has_luca = any(detect_type(f) == "luca" for f in files)
        if has_epub and (has_luca or any(f.lower().endswith(".json") for f in files)):
            raise SystemExit("Mixed EPUB + JSON/Luca not allowed — parse them as separate projects.")
        if has_epub:
            ptype = "epub"
        elif has_luca and not any(f.lower().endswith(".json") for f in files):
            ptype = "luca"
        else:
            ptype = "json"
    data["projectType"] = ptype

    epub_source_b64 = None
    epub_source_id = None

    if ptype == "epub":
        # Single EPUB — preserve bytes for later export round-trip
        epub_file = next((f for f in files if f.lower().endswith(".epub")), files[0])
        with open(epub_file, "rb") as f:
            epub_bytes = f.read()
        epub_source_b64 = base64.b64encode(epub_bytes).decode("ascii")
        try:
            lines, imported = _parse_epub(epub_bytes, epub_tags)
        except Exception as e:
            raise SystemExit(f"Failed to parse EPUB: {e}")
        data["lines"] = lines
        data["imported_files"] = imported
        data["file_order"] = list(imported)
        data["epub_source"] = {"data": epub_source_b64}
        # also keep a synthetic id for compat
        data["epubSourceId"] = None
        # Re-number
        for i, ln in enumerate(lines, 1):
            ln["line_num"] = i
        return data

    if ptype == "luca":
        luca_files: dict[str, list[str]] = {}
        luca_buffers: dict[str, str] = {}
        for f in files:
            if not f.lower().endswith(".txt"):
                continue
            base = _normalize_file_base(f)
            if base in imported:
                continue
            text = _read_text_file(f)
            with open(f, "rb") as bf:
                raw_bytes = bf.read()
            luca_files[base] = text.splitlines()
            luca_buffers[base] = base64.b64encode(raw_bytes).decode("ascii")
            chunk = _parse_luca_txt(text, base, cur)
            if chunk:
                lines.extend(chunk)
                cur += len(chunk)
                imported.append(base)
        data["lines"] = lines
        data["imported_files"] = imported
        data["file_order"] = list(imported)
        data["lucaRawFiles"] = luca_files
        data["lucaRawBuffers"] = luca_buffers
        return data

    # JSON
    for f in files:
        if not f.lower().endswith(".json"):
            continue
        base = _normalize_file_base(f)
        if base in imported:
            continue
        try:
            chunk, _ = _parse_json_file(f, cur)
        except Exception as e:
            print(f"skip {f}: {e}")
            continue
        if chunk:
            lines.extend(chunk)
            cur += len(chunk)
            imported.append(base)

    data["lines"] = lines
    data["imported_files"] = imported
    data["file_order"] = list(imported)
    return data


def _parse_epub(epub_bytes: bytes, tags_selector: str = "p") -> tuple[list[dict], list[str]]:
    """Extract lines from EPUB HTML documents using a CSS-like tag selector."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError("beautifulsoup4 is required for EPUB parsing (pip install beautifulsoup4 lxml)")
    import xml.etree.ElementTree as ET

    # Use stdlib zipfile to enumerate OPF/manifest
    with zipfile.ZipFile(os.path.join(os.path.sep, "tmp_epub"), "r") as _:
        pass
    # Re-open from bytes
    import io
    zf = zipfile.ZipFile(io.BytesIO(epub_bytes), "r")
    # Find OPF via container.xml
    try:
        container = zf.read("META-INF/container.xml").decode("utf-8")
    except KeyError:
        raise RuntimeError("EPUB missing META-INF/container.xml")
    m = re.search(r'full-path="([^"]+)"', container)
    if not m:
        raise RuntimeError("EPUB container.xml missing rootfile path")
    opf_path = m.group(1)
    opf_dir = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
    opf_xml = zf.read(opf_path).decode("utf-8")

    # Parse OPF manifest + spine with namespace handling
    NS = {"opf": "http://www.idpf.org/2007/opf"}
    try:
        opf_doc = ET.fromstring(opf_xml.encode("utf-8"))
    except ET.ParseError as e:
        raise RuntimeError(f"EPUB OPF parse error: {e}")

    # Collect manifest items: id -> href
    manifest: dict[str, str] = {}
    for item in opf_doc.findall(".//opf:item", NS):
        iid = item.get("id") or ""
        href = item.get("href") or ""
        if iid and href:
            # href is relative to OPF dir
            manifest[iid] = href

    # Spine order
    spine_hrefs: list[str] = []
    for ref in opf_doc.findall(".//opf:itemref", NS):
        idref = ref.get("idref") or ""
        href = manifest.get(idref)
        if href:
            spine_hrefs.append(opf_dir + href)

    selector = tags_selector.strip() or "p"
    # Simple selector: support "p", "p,div", "p.foo" — we normalize to tag list for bs4
    tags = [t.strip().split(".")[0].split("#")[0].split("[")[0] for t in re.split(r"\s*,\s*", selector) if t.strip()]
    if not tags:
        tags = ["p"]

    lines: list[dict] = []
    imported: list[str] = []
    cur = 1
    for href in spine_hrefs:
        try:
            html = zf.read(href).decode("utf-8")
        except KeyError:
            continue
        soup = BeautifulSoup(html, "lxml")
        els = []
        for tag in tags:
            els.extend(soup.find_all(tag))
        # Keep document order for mixed selectors
        # Deduplicate by id()
        seen = set()
        ordered = []
        for el in els:
            eid = id(el)
            if eid in seen:
                continue
            seen.add(eid)
            ordered.append(el)
        file_has_content = False
        for el in ordered:
            text = (el.get_text() or "").replace("\r\n", " ").replace("\n", " ").strip()
            if not text:
                continue
            lines.append({
                "line_num": cur,
                "file": href,
                "name": None,
                "message": text,
                "trans_name": None,
                "trans_message": None,
                "is_translated": False,
            })
            cur += 1
            file_has_content = True
        if file_has_content:
            imported.append(href)
    zf.close()
    return lines, imported


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Parse VN inputs or import a CopasTool project backup")
    ap.add_argument("--input", required=True, help="File or folder to parse")
    ap.add_argument("--out", required=True, help="Output .copas or .copas.zip project path")
    ap.add_argument("--name", default="Imported Project")
    ap.add_argument("--type", dest="ptype", default="auto", choices=["auto", "json", "epub", "luca"])
    ap.add_argument("--epub-tags", default="p")
    ap.add_argument("--source-lang", default=None)
    ap.add_argument("--target-lang", default=None)
    ap.add_argument("--import-project", "--import-cstl", dest="import_project", action="store_true", help="Copy an existing .copas/.cstl project backup to --out")
    a = ap.parse_args(argv)

    if a.import_project:
        import shutil
        if not os.path.exists(a.input):
            ap.error(f"input not found: {a.input}")
        input_is_zip = a.input.lower().endswith((".copas.zip", ".cstl.zip"))
        output_is_zip = a.out.lower().endswith((".copas.zip", ".cstl.zip"))
        if input_is_zip != output_is_zip:
            ap.error("keep the backup container type in --out (.copas/.cstl or .copas.zip/.cstl.zip)")
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        shutil.copy2(a.input, a.out)
        s = load_cstl(a.out)
        total = len(s.get("lines", []))
        trans = sum(1 for l in s.get("lines", []) if l.get("is_translated"))
        print(f"imported {total} lines ({trans} translated) -> {a.out} [{s.get('projectType','?')}]")
        return

    data = parse_inputs(a.input, project_type=a.ptype, epub_tags=a.epub_tags, name=a.name, source_lang=a.source_lang, target_lang=a.target_lang)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    save_cstl(a.out, data)
    print(f"parsed {len(data['lines'])} lines -> {a.out} [type={data.get('projectType')}]")


if __name__ == "__main__":
    main()
