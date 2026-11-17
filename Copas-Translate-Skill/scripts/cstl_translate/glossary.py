"""Glossary tools for CopasTool projects: extract, from-text, from-project, inject, filter, lint, merge-newterms."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

from .cstl_io import ensure_cstl, load_cstl, locked, save_cstl
from .helpers import backup_file, has_cjk, latin_boundary_search, normalize_apostrophes

_TITLES = {
    "dr", "mr", "mrs", "ms", "miss", "sir", "lady", "lord", "captain", "capt", "commander", "cmdr",
    "lieutenant", "lt", "major", "colonel", "general", "admiral", "ensign", "sergeant", "governor",
    "president", "senator", "ambassador", "minister", "chancellor", "professor", "prof", "elder",
    "chief", "brother", "sister", "father", "mother", "master", "mistress",
}
_JP_HON_SUFFIX = re.compile(r"(?:[-‐‑–—]?(?:san|kun|chan|sama|sensei|senpai|dono)|さん|くん|ちゃん|様|先生|先輩|殿)$", re.I)


def _kanji(s: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", s or ""))


def extract_candidates(cstl_path: str, top_k: int = 200) -> dict:
    """Heuristic extraction from source messages — frequency of CJK tokens + katakana + speakers."""
    data = ensure_cstl(load_cstl(cstl_path))
    counter: Counter[str] = Counter()
    speakers: set[str] = set()
    for ln in data.get("lines", []):
        msg = ln.get("message") or ""
        for m in re.findall(r"[\u3400-\u9fff]{2,}", msg):
            if 2 <= len(m) <= 8:
                counter[m] += 1
        for m in re.findall(r"[\u30a0-\u30ff]{2,}", msg):
            if 2 <= len(m) <= 10:
                counter[m] += 1
        name = (ln.get("name") or "").strip()
        if name:
            speakers.add(name)
            counter[name] += 3
    cands = [(tok, c) for tok, c in counter.items() if c >= 2 or tok in speakers]
    cands.sort(key=lambda x: (-x[1], x[0]))
    characters: list[dict] = []
    terms: list[dict] = []
    for tok, c in cands[:top_k]:
        if tok in speakers or (_kanji(tok) and len(tok) <= 5 and c >= 3):
            characters.append({
                "canonical": tok, "render": tok, "aliases": [], "type": "character",
                "desc": "character name", "keep_source": False, "count": c,
            })
        else:
            terms.append({"src": tok, "dst": tok, "category": "term", "count": c})
    return {"characters": characters, "terms": terms, "non_translate": []}


def parse_glossary_text(text: str) -> dict:
    """Parse CSTL glossary_text format: `[type] source = target {desc}`, `src<TAB>dst`, or `src => dst`."""
    chars: list[dict] = []
    terms: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\s*\[([a-z ]+)\]\s*(.*)$", line, re.I)
        gtype = "term"
        body = line
        if m:
            gtype = re.sub(r"\s+", "-", m.group(1).strip().lower())
            body = m.group(2).strip()
        aliases = {"char": "character", "chars": "character", "name": "character", "names": "character",
                   "place": "place", "location": "place"}
        gtype = aliases.get(gtype, gtype)
        if "\t" in body and "=" not in body:
            src, rest = body.split("\t", 1)
            src, rest = src.strip(), rest.strip()
        elif "=>" in body and "=" not in body.replace("=>", ""):
            src, rest = body.split("=>", 1)
            src, rest = src.strip(), rest.strip()
        else:
            sep = body.find("=")
            if sep == -1:
                sep = body.find(":")
            if sep == -1:
                continue
            src = body[:sep].strip()
            rest = body[sep + 1:].strip()
        desc = ""
        dm = re.search(r"\{([^{}]+)\}\s*$", rest)
        if dm:
            desc = dm.group(1).strip()
            rest = rest[:dm.start()].strip()
        dst = rest
        if not src or not dst:
            continue
        if gtype == "character":
            chars.append({"canonical": src, "render": dst, "aliases": [], "type": "character", "desc": desc or "character name"})
        else:
            terms.append({"src": src, "dst": dst, "category": gtype, "desc": desc})
    return {"characters": chars, "terms": terms, "non_translate": []}


def serialize_glossary_text(locked_data: dict) -> str:
    lines: list[str] = []
    for ch in locked_data.get("characters", []):
        src = ch.get("canonical") or ch.get("src") or ""
        dst = ch.get("render") or ch.get("dst") or ""
        if ch.get("keep_source"):
            dst = src
        desc = (ch.get("desc") or "character name").strip()
        if src and dst:
            lines.append(f"[character] {src} = {dst} {{{desc}}}")
    for t in locked_data.get("terms", []):
        src = t.get("src") or ""
        dst = t.get("dst") or ""
        if t.get("keep_source"):
            dst = src
        cat = (t.get("category") or t.get("type") or "term").strip().lower()
        desc = (t.get("desc") or "").strip()
        if src and dst:
            suffix = f" {{{desc}}}" if desc else ""
            lines.append(f"[{cat}] {src} = {dst}{suffix}")
    return "\n".join(lines)


def inject_into_cstl(cstl_path: str, locked_path: str) -> None:
    with open(locked_path, "r", encoding="utf-8-sig") as f:
        locked_data = json.load(f)
    with locked(cstl_path):
        backup_file(cstl_path)
        data = ensure_cstl(load_cstl(cstl_path))
        data["glossary_text"] = serialize_glossary_text(locked_data)
        save_cstl(cstl_path, data)
    print(f"injected glossary_text ({len(data['glossary_text'].splitlines())} entries) -> {cstl_path}")


# ------------------------------------------------------------------ filter ----
def _term_present(term: str, corpus: str) -> bool:
    t = normalize_apostrophes(term or "").strip()
    if not t:
        return False
    if has_cjk(t):
        return t in corpus
    return latin_boundary_search(t, corpus, ignore_case=True) is not None


def filter_locked(locked_data: dict, texts: list[str], names: list[str] = ()) -> dict:
    """Subset of characters & terms that occur in `texts` or speaker `names`."""
    corpus = normalize_apostrophes("\n".join(list(texts) + [n for n in names if n]))
    chars = []
    for c in locked_data.get("characters", []):
        candidates = [c.get("canonical"), c.get("render")] + list(c.get("aliases") or [])
        if any(_term_present(str(n), corpus) for n in candidates if n):
            chars.append(c)
    terms = [t for t in locked_data.get("terms", []) if _term_present(str(t.get("src") or ""), corpus)]
    return {
        "characters": chars,
        "terms": terms,
        "non_translate": locked_data.get("non_translate", []),
        "_meta": {
            "filtered": True,
            "kept": {"characters": len(chars), "terms": len(terms)},
            "total": {"characters": len(locked_data.get("characters", [])),
                      "terms": len(locked_data.get("terms", []))},
        },
    }


def _texts_from_files(paths: list[str]) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    names: list[str] = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            data = json.load(f)
        rows = data.get("lines") if isinstance(data, dict) else data
        for r in rows or ():
            if not isinstance(r, dict):
                continue
            texts.append(str(r.get("message") or r.get("source_text") or ""))
            if r.get("name"):
                names.append(str(r["name"]))
    return texts, names


# -------------------------------------------------------------------- lint ----
def lint_locked(locked_data: dict) -> list[dict]:
    issues: list[dict] = []
    chars = locked_data.get("characters", []) or []
    terms = locked_data.get("terms", []) or []
    owner: dict[str, str] = {}
    term_srcs = {normalize_apostrophes(str(t.get("src") or "")).lower() for t in terms}

    lead_count: dict[str, set[str]] = {}
    for c in chars:
        canon_l = normalize_apostrophes(str(c.get("canonical") or "")).lower()
        for n in [c.get("canonical"), c.get("render")] + list(c.get("aliases") or []):
            toks = normalize_apostrophes(str(n or "")).split()
            if len(toks) >= 2 and " ".join(t.lower() for t in toks[1:]) == canon_l:
                lead_count.setdefault(toks[0].lower(), set()).add(canon_l)

    for c in chars:
        canon = str(c.get("canonical") or c.get("render") or "").strip()
        render = str(c.get("render") or "").strip()
        if not render:
            issues.append({"kind": "character_missing_render", "character": canon})
        canon_toks = normalize_apostrophes(canon).lower().split()
        render_is_surname = (
            normalize_apostrophes(render).lower().split() == canon_toks[-len(render.split()):]
            if render.split() else False
        )
        for n in [canon] + ([] if render_is_surname else [render]) + list(c.get("aliases") or []):
            n_s = str(n or "").strip()
            if not n_s:
                continue
            toks = normalize_apostrophes(n_s).split()
            lead = toks[0].lower().rstrip(".") if toks else ""
            titled = (
                len(toks) >= 2 and [t.lower() for t in toks[1:]] == canon_toks
                and (lead in term_srcs or len(lead_count.get(lead, ())) >= 2)
            )
            if (toks and (lead in _TITLES or titled)) or (_JP_HON_SUFFIX.search(n_s) and n_s != canon and n_s != render):
                issues.append({
                    "kind": "alias_has_title",
                    "character": canon,
                    "alias": n_s,
                    "hint": "Keep bare names as aliases; honorifics/titles that translate separately cause false positives",
                })
            key = normalize_apostrophes(n_s).lower()
            if key in owner and owner[key] != canon:
                issues.append({"kind": "alias_collides", "alias": n_s, "characters": [owner[key], canon]})
            owner.setdefault(key, canon)

    by_surname: dict[str, set[str]] = {}
    for c in chars:
        canon = str(c.get("canonical") or "").strip()
        render = str(c.get("render") or "").strip()
        for form in (canon, render):
            toks = normalize_apostrophes(form).split()
            if len(toks) >= 2:
                for edge in (toks[0].lower(), toks[-1].lower()):
                    if len(edge) >= 3 and edge.rstrip(".") not in _TITLES:
                        by_surname.setdefault(edge, set()).add(canon or render)
        if canon and " " not in canon and has_cjk(canon) and len(canon) >= 3:
            prefix = canon[:2]
            if _kanji(prefix):
                by_surname.setdefault(prefix, set()).add(canon)
    for last, cs in by_surname.items():
        if len(cs) > 1:
            issues.append({
                "kind": "shared_surname",
                "surname": last,
                "characters": sorted(cs),
                "hint": "Check no alias was merged across distinct characters",
            })

    seen: dict[str, str] = {}
    for t in terms:
        src_raw = str(t.get("src") or "").strip()
        src = normalize_apostrophes(src_raw).lower()
        if not src:
            issues.append({"kind": "term_missing_src", "term": t})
            continue
        if src in seen:
            issues.append({"kind": "duplicate_term", "src": src_raw, "dst": [seen[src], t.get("dst")]})
        seen.setdefault(src, str(t.get("dst") or ""))
        if not str(t.get("dst") or "").strip() and not t.get("keep_source"):
            issues.append({"kind": "term_missing_dst", "src": src_raw})
    return issues


# ----------------------------------------------------------- merge-newterms ----
def _known_entries(locked_data: dict) -> set[str]:
    known: set[str] = set()
    for c in locked_data.get("characters", []):
        for n in [c.get("canonical"), c.get("render")] + list(c.get("aliases") or []):
            if n:
                known.add(normalize_apostrophes(str(n)).lower())
    for t in locked_data.get("terms", []):
        if t.get("src"):
            known.add(normalize_apostrophes(str(t["src"])).lower())
    return known


def parse_newterm(line: str) -> tuple[str, str, str, str] | None:
    """Parse `src`, `src<TAB>dst`, `src => dst`, or `[type] src = dst {desc}` -> `(src, dst, cat, desc)`."""
    line = line.strip().strip(",;")
    if not line or line.startswith("#") or line in ("<new_terms>", "</new_terms>"):
        return None
    cat = "term"
    desc = ""
    m = re.match(r"^\s*\[([a-z ]+)\]\s*(.*)$", line, re.I)
    if m:
        cat = re.sub(r"\s+", "-", m.group(1).strip().lower())
        line = m.group(2).strip()
    dm = re.search(r"\{([^{}]+)\}\s*$", line)
    if dm:
        desc = dm.group(1).strip()
        line = line[:dm.start()].strip()
    if "\t" in line:
        src, dst = line.split("\t", 1)
    elif "=>" in line:
        src, dst = line.split("=>", 1)
    elif "=" in line:
        src, dst = line.split("=", 1)
    else:
        src, dst = line, line
    src = src.strip()
    dst = dst.strip() or src
    if not src:
        return None
    return src, dst, cat, desc


def newterm_conflicts(per_file: dict[str, list[tuple[str, str, str, str]]]) -> dict[str, dict[str, list[str]]]:
    seen: dict[str, dict[str, list[str]]] = {}
    for f, rows in per_file.items():
        for src, dst, _, _ in rows:
            seen.setdefault(normalize_apostrophes(src).lower(), {}).setdefault(dst, []).append(f)
    return {k: v for k, v in seen.items() if len(v) > 1}


def merge_newterms(locked_data: dict, entries: list, category: str = "new") -> tuple[list[str], list[str]]:
    known = _known_entries(locked_data)
    added, skipped = [], []
    for raw in entries:
        if isinstance(raw, str):
            parsed = parse_newterm(raw)
            if not parsed:
                continue
            src, dst, cat, desc = parsed
        elif len(raw) == 2:
            src, dst = raw
            cat, desc = category, ""
        else:
            src, dst, cat, desc = raw[0], raw[1], raw[2] or category, raw[3] if len(raw) > 3 else ""
        k = normalize_apostrophes(src).lower()
        if k in known:
            skipped.append(src)
            continue
        known.add(k)
        keep = normalize_apostrophes(dst) == normalize_apostrophes(src)
        if cat in ("character", "char", "name"):
            locked_data.setdefault("characters", []).append({
                "canonical": src,
                "render": dst,
                "aliases": [],
                "type": "character",
                "desc": desc or "character name (parallel newterm)",
                "keep_source": keep,
            })
        else:
            locked_data.setdefault("terms", []).append({
                "src": src,
                "dst": dst,
                "keep_source": keep,
                "category": cat if cat != "term" else category,
                "desc": desc or ("kept verbatim" if keep else "chosen by worker; review"),
            })
        added.append(src if keep else f"{src} -> {dst}")
    return added, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSTL glossary helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("extract", help="Extract candidate glossary from project source lines")
    ex.add_argument("cstl_path")
    ex.add_argument("--out", required=True)
    ex.add_argument("--top-k", type=int, default=200)

    ft = sub.add_parser("from-text", help="Convert CSTL glossary_text file to locked JSON")
    ft.add_argument("--text", required=True)
    ft.add_argument("--out", required=True)

    fp = sub.add_parser("from-project", help="Seed locked JSON from the backup's saved glossary_text")
    fp.add_argument("cstl_path")
    fp.add_argument("--out", required=True)

    inj = sub.add_parser("inject", help="Inject locked glossary into project glossary_text")
    inj.add_argument("cstl_path")
    inj.add_argument("locked_path")

    flt = sub.add_parser("filter", help="Subset of locked glossary occurring in batch/group source files")
    flt.add_argument("--locked", required=True)
    flt.add_argument("--for", dest="sources", nargs="+", required=True, metavar="SRC_JSON")
    flt.add_argument("--out", required=True)

    lnt = sub.add_parser("lint", help="Check structural issues in locked glossary JSON")
    lnt.add_argument("--locked", required=True)

    mrg = sub.add_parser("merge-newterms", help="Merge parallel newterms_*.txt into locked glossary")
    mrg.add_argument("--locked", required=True)
    mrg.add_argument("files", nargs="+")
    mrg.add_argument("--apply", action="store_true")
    mrg.add_argument("--inject", metavar="CSTL_PATH", help="Also inject updated glossary into project backup")
    mrg.add_argument("--category", default="new")

    vdb = sub.add_parser("vndb", help="Fetch character glossary from VNDB Kana API v2")
    from . import vndb as vndb_mod
    vndb_mod.add_vndb_arguments(vdb)

    a = ap.parse_args(argv)
    if a.cmd == "vndb":
        return vndb_mod.run_cli_args(a)
    if a.cmd == "extract":
        locked_data = extract_candidates(a.cstl_path, top_k=a.top_k)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(locked_data, f, ensure_ascii=False, indent=2)
        print(f"locked glossary -> {a.out}  (characters={len(locked_data['characters'])} terms={len(locked_data['terms'])})")
    elif a.cmd == "from-text":
        with open(a.text, "r", encoding="utf-8-sig") as f:
            txt = f.read()
        locked_data = parse_glossary_text(txt)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(locked_data, f, ensure_ascii=False, indent=2)
        print(f"locked glossary -> {a.out}")
    elif a.cmd == "from-project":
        data = ensure_cstl(load_cstl(a.cstl_path))
        locked_data = parse_glossary_text(data.get("glossary_text") or "")
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(locked_data, f, ensure_ascii=False, indent=2)
        print(f"project glossary -> {a.out}")
    elif a.cmd == "inject":
        inject_into_cstl(a.cstl_path, a.locked_path)
    elif a.cmd == "filter":
        with open(a.locked, "r", encoding="utf-8-sig") as f:
            locked_data = json.load(f)
        texts, names = _texts_from_files(a.sources)
        sub_gl = filter_locked(locked_data, texts, names)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(sub_gl, f, ensure_ascii=False, indent=2)
        k, t = sub_gl["_meta"]["kept"], sub_gl["_meta"]["total"]
        print(f"filtered glossary -> {a.out}: characters {k['characters']}/{t['characters']}, terms {k['terms']}/{t['terms']}")
    elif a.cmd == "lint":
        with open(a.locked, "r", encoding="utf-8-sig") as f:
            locked_data = json.load(f)
        issues = lint_locked(locked_data)
        print(json.dumps(issues, ensure_ascii=False, indent=2))
        sys.stderr.write(f"{len(issues)} issue(s)\n")
        return 1 if issues else 0
    elif a.cmd == "merge-newterms":
        with open(a.locked, "r", encoding="utf-8-sig") as f:
            locked_data = json.load(f)
        per_file: dict[str, list[tuple[str, str, str, str]]] = {}
        for p in a.files:
            with open(p, "r", encoding="utf-8-sig") as fh:
                per_file[p] = [x for x in (parse_newterm(line) for line in fh.read().splitlines()) if x]
        conflicts = newterm_conflicts(per_file)
        for k, v in conflicts.items():
            print(f"CONFLICT {k}: " + "; ".join(f"{d} ({', '.join(os.path.basename(f) for f in fs)})"
                                               for d, fs in v.items()))
        pairs = [row for rows in per_file.values() for row in rows
                 if normalize_apostrophes(row[0]).lower() not in conflicts]
        added, skipped = merge_newterms(locked_data, pairs, a.category)
        print(f"new: {len(added)}  already known: {len(skipped)}  conflicts (not merged): {len(conflicts)}")
        for n in added:
            print(f"  + {n}")
        if a.apply:
            backup_file(a.locked)
            with open(a.locked, "w", encoding="utf-8") as f:
                json.dump(locked_data, f, ensure_ascii=False, indent=2)
            print(f"written -> {a.locked}")
            if a.inject:
                inject_into_cstl(a.inject, a.locked)
        elif added:
            print("(preview; add --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
