"""Read-only engine/format detection for a visual novel game folder.

Walks the game directory, collects evidence (file names, magic bytes,
executable strings), and ranks candidate engine families. Never writes
anything — the only output is a report (stdout and/or --out file).

Usage:
    python -m copas_reverse.detect <game_dir> [--out report.md] [--exe-scan]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

# High-confidence magic bytes. (family, signature, search window at file start)
MAGIC_SIGNATURES = [
    ("kirikiri", b"XP3", 64, "XP3 archive header"),
    ("rpgmaker", b"RGSSAD\x00", 8, "RGSSAD archive (XP/VX/VX Ace)"),
    ("renpy", b"RPA-3.0 ", 16, "Ren'Py RPA archive"),
    ("godot", b"GDPC", 8, "Godot PCK package"),
    ("majiro", b"MajiroArc", 16, "Majiro archive"),
    ("majiro", b"MajiroObj", 16, "Majiro bytecode object"),
]

# File-name rules. (family, kind, pattern, weight, evidence text)
# kind: exact (file name, case-insensitive) | suffix (extension) | dirname
FILENAME_RULES = [
    ("nscripter", "exact", "nscript.dat", 3, "NScripter encrypted script"),
    ("nscripter", "suffix", ".nsa", 2, "NScripter archive"),
    ("nscripter", "suffix", ".sar", 2, "NScripter archive"),
    ("kirikiri", "suffix", ".xp3", 3, "XP3 archive"),
    ("reallive", "exact", "gameexe.ini", 3, "RealLive configuration"),
    ("reallive", "exact", "seen.txt", 2, "RealLive scenario source"),
    ("renpy", "suffix", ".rpa", 3, "Ren'Py archive"),
    ("renpy", "suffix", ".rpyc", 2, "Ren'Py compiled script"),
    ("renpy", "suffix", ".rpy", 1, "Ren'Py script"),
    ("rpgmaker", "suffix", ".rgss3a", 3, "RPG Maker VX Ace archive"),
    ("rpgmaker", "suffix", ".rgss2a", 3, "RPG Maker VX archive"),
    ("rpgmaker", "suffix", ".rgssad", 3, "RPG Maker XP archive"),
    ("rpgmaker", "exact", "www", 2, "RPG Maker MV/MZ web folder"),
    ("rpgmaker", "exact", "js", 1, "possible RPG Maker MV/MZ js folder"),
    ("tyrano", "exact", "tyrano", 3, "Tyrano engine folder"),
    ("artemis", "suffix", ".pfs", 3, "Artemis archive"),
    ("ethornell", "exact", "archdata.bin", 3, "BGI/Ethornell archive"),
    ("ethornell", "exact", "datapack.bin", 3, "BGI/Ethornell archive"),
    ("ethornell", "exact", "ethornell.exe", 3, "Ethornell executable"),
    ("ethornell", "exact", "bgi.exe", 3, "BGI executable"),
    ("catsystem2", "suffix", ".int", 2, "CatSystem2 encrypted archive/data"),
    ("catsystem2", "exact", "cs2.ini", 2, "CatSystem2 configuration"),
    ("willplus", "suffix", ".fa", 1, "possible WillPlus resource"),
    ("yuris", "suffix", ".ypf", 3, "YU-RIS archive"),
    ("cmvs", "suffix", ".cpz", 3, "CMVS archive"),
    ("majiro", "suffix", ".mjil", 3, "Majiro intermediate bytecode"),
    ("majiro", "suffix", ".mjo", 2, "Majiro compiled object"),
    ("majiro", "suffix", ".mjs", 2, "Majiro script"),
    ("siglus", "exact", "siglusengine.exe", 3, "SiglusEngine executable"),
    ("malie", "suffix", ".mjo", 1, "possible Malie object (shared with Majiro)"),
    ("malie", "suffix", ".lib", 1, "possible Malie library file"),
    ("unity", "suffix", ".assets", 1, "Unity serialized asset"),
    ("unity", "suffix", ".unity3d", 2, "Unity bundle"),
    ("godot", "suffix", ".pck", 2, "Godot PCK (confirm by GDPC magic)"),
    ("wolf", "exact", "data.wolf", 3, "Wolf RPG Editor archive"),
    ("wolf", "suffix", ".wolf", 2, "Wolf RPG data"),
    ("qlie", "suffix", ".b", 1, "possible QLIE archive (confirm by layout)"),
    ("mages", "suffix", ".msb", 3, "MAGES scenario script"),
    ("nitroplus", "suffix", ".npa", 3, "Nitro+ archive"),
    ("eushully", "suffix", ".arc", 1, "generic .arc (Eushully and many others)"),
    ("minori", "suffix", ".mrg", 2, "possible Minori archive"),
    ("overdrive", "suffix", ".ovk", 3, "Overdrive archive"),
    ("systemnnn", "suffix", ".nnn", 3, "System-NNN file"),
    ("entisgls", "suffix", ".ems", 2, "possible EntisGLS archive"),
    ("gamemaker", "exact", "data.win", 3, "GameMaker data (FORM magic)"),
    ("lucasystem", "exact", "script.pak", 2, "LucaSystem script archive"),
    ("lucasystem", "exact", "param.pak", 2, "LucaSystem parameter archive"),
    ("lucasystem", "exact", "sysse.pak", 2, "LucaSystem system sound archive"),
]

# Strings to look for inside executables (first 1 MiB). (family, bytes, weight)
EXE_STRING_RULES = [
    ("kirikiri", b"Kirikiri", 2),
    ("kirikiri", b"KAG", 1),
    ("reallive", b"RealLive", 2),
    ("siglus", b"SiglusEngine", 3),
    ("malie", b"Malie", 2),
    ("ethornell", b"Ethornell", 2),
    ("ethornell", b"BGI", 1),
    ("artemis", b"Artemis", 2),
    ("willplus", b"AdvHD", 2),
    ("willplus", b"WillPlus", 2),
    ("yuris", b"YU-RIS", 3),
    ("cmvs", b"CMVS", 2),
    ("catsystem2", b"CatSystem", 3),
    ("nscripter", b"NScripter", 2),
    ("renpy", b"Ren'Py", 2),
    ("majiro", b"Majiro", 2),
    ("unity", b"UnityPlayer", 2),
    ("unity", b"UnityEngine", 1),
    ("tyrano", b"Tyrano", 2),
    ("godot", b"GodotEngine", 2),
    ("wolf", b"Silvore", 2),
    ("qlie", b"QLIE", 2),
    ("mages", b"MAGES", 3),
    ("mages", b"5pb", 1),
    ("nitroplus", b"Nitro", 2),
    ("eushully", b"Eushully", 3),
    ("minori", b"minori", 2),
    ("overdrive", b"Overdrive", 2),
    ("systemnnn", b"System-NNN", 3),
    ("entisgls", b"EntisGLS", 3),
    ("gamemaker", b"GameMaker", 2),
    ("silkys", b"Silky's", 2),
    ("circus", b"CIRCUS", 2),
    ("mink", b"MINK", 2),
    ("nexton", b"Nexton", 1),
    ("studioego", b"Studio e.go", 2),
    ("debonosu", b"Debonosu", 2),
    ("hunex", b"HuneX", 2),
    ("liarsoft", b"Liar-soft", 2),
]

# Families that have a dedicated engine page; everything else maps to catalog.md.
PAGE_FAMILIES = frozenset({
    "kirikiri", "nscripter", "reallive", "renpy", "rpgmaker", "tyrano",
    "unity", "godot", "catsystem2", "ethornell", "artemis", "willplus",
    "yuris", "cmvs", "majiro", "siglus", "malie", "wolf", "qlie", "mages",
    "nitroplus", "eushully", "minori", "overdrive", "systemnnn",
    "entisgls", "gamemaker", "lucasystem",
})


def _page_for(family: str) -> str:
    return f"references/engines/{family}.md" if family in PAGE_FAMILIES \
        else "references/engines/catalog.md"


def _walk_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            files.append(Path(dirpath) / fn)
            if len(files) >= max_files:
                print(f"warning: stopped listing at {max_files} files", file=sys.stderr)
                return files
    return files


def _scan_file(f: Path) -> dict:
    """Collect all evidence for one file (read-only)."""
    ev: dict = {"path": f, "families": Counter(), "notes": []}
    try:
        size = f.stat().st_size
    except OSError:
        return ev
    name = f.name.lower()
    rel = f
    # Magic bytes
    try:
        with open(f, "rb") as fh:
            head = fh.read(4096)
        for family, sig, window, desc in MAGIC_SIGNATURES:
            if head[:window].find(sig) != -1:
                ev["families"][family] += 4
                ev["notes"].append(f"magic '{sig.decode('ascii', 'replace')}' — {desc}")
    except OSError:
        return ev
    # File-name rules
    for family, kind, pattern, weight, desc in FILENAME_RULES:
        if kind == "exact" and name == pattern.lower():
            ev["families"][family] += weight
            ev["notes"].append(f"file name: {desc}")
        elif kind == "suffix" and name.endswith(pattern.lower()):
            ev["families"][family] += weight
            ev["notes"].append(f"extension {pattern}: {desc}")
        elif kind == "dirname" and name == pattern.lower():
            ev["families"][family] += weight
            ev["notes"].append(f"directory: {desc}")
    # Executable string scan
    if f.suffix.lower() == ".exe" and size > 0:
        try:
            with open(f, "rb") as fh:
                blob = fh.read(1024 * 1024)
            for family, needle, weight in EXE_STRING_RULES:
                if blob.find(needle) != -1:
                    ev["families"][family] += weight
                    ev["notes"].append(f"exe string: {needle.decode('ascii', 'replace')!r}")
        except OSError:
            pass
    ev["size"] = size
    return ev


def _detect_rpgmaker_mv_mz(files: list[Path]) -> Counter:
    ev: Counter = Counter()
    for f in files:
        pl = str(f).replace("\\", "/").lower()
        if "/data/" in pl and f.suffix.lower() == ".json" and "map" in f.stem.lower():
            ev["rpgmaker"] += 2
        if "/js/rpg_" in pl:
            ev["rpgmaker"] += 2
    return ev


def detect(game_dir: str, max_files: int = 20000):
    root = Path(game_dir)
    if not root.is_dir():
        raise SystemExit(f"not a directory: {game_dir}")
    files = _walk_files(root, max_files)
    per_file: list[dict] = []
    total: Counter = Counter()
    ext_hist: Counter = Counter()
    ext_size: Counter = Counter()
    for f in files:
        ev = _scan_file(f)
        ev["rel"] = str(ev["path"].relative_to(root))
        per_file.append(ev)
        total.update(ev["families"])
        ext = f.suffix.lower() or "(none)"
        ext_hist[ext] += 1
        ext_size[ext] += ev.get("size", 0)
    mv_mz = _detect_rpgmaker_mv_mz(files)
    for fam, sc in mv_mz.items():
        if sc >= 4:  # at least two independent json/js hits
            total[fam] += sc
    return total, per_file, ext_hist, ext_size


def render_report(game_dir: str, total: Counter, per_file: list[dict],
                  ext_hist: Counter, ext_size: Counter, top_ext: int = 30) -> str:
    lines: list[str] = []
    lines.append(f"# Engine detection report — {game_dir}")
    lines.append("")
    lines.append("Read-only scan; nothing in the game folder was modified.")
    lines.append("")
    lines.append("## Candidate engines (ranked)")
    lines.append("")
    lines.append("| Rank | Family | Score | Confidence | Read next |")
    lines.append("|---|---|---|---|---|")
    ranked = total.most_common()
    for i, (fam, score) in enumerate(ranked[:8], 1):
        conf = "high" if score >= 8 else ("medium" if score >= 4 else "low")
        page = _page_for(fam)
        lines.append(f"| {i} | {fam} | {score} | {conf} | `{page}` |")
    if not ranked:
        lines.append("| – | (no candidate found) | 0 | – | `references/engines/unknown.md` |")
    lines.append("")
    lines.append("Do not commit to a family from this table alone — cross-check at least two "
                 "independent signals (magic + layout + exe strings) before acting.")
    lines.append("")
    lines.append("## Per-file evidence (files with any hit)")
    lines.append("")
    lines.append("| File | Families (score) | Evidence |")
    lines.append("|---|---|---|")
    for ev in per_file:
        if not ev["families"]:
            continue
        fams = ", ".join(f"{k}({v})" for k, v in ev["families"].most_common(3))
        notes = "; ".join(dict.fromkeys(ev["notes"][:4]))
        lines.append(f"| `{ev['rel']}` | {fams} | {notes} |")
    lines.append("")
    lines.append("## Extension histogram (top %d)" % top_ext)
    lines.append("")
    lines.append("| Ext | Count | Total size |")
    lines.append("|---|---|---|")
    for ext, cnt in ext_hist.most_common(top_ext):
        lines.append(f"| {ext} | {cnt} | {ext_size[ext]:,} |")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only VN engine/format detection")
    ap.add_argument("game_dir")
    ap.add_argument("--out", default=None, help="also write the markdown report here")
    ap.add_argument("--max-files", type=int, default=20000)
    a = ap.parse_args(argv)
    total, per_file, ext_hist, ext_size = detect(a.game_dir, a.max_files)
    report = render_report(a.game_dir, total, per_file, ext_hist, ext_size)
    print(report)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"report written: {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
