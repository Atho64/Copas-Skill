"""Scan CopasTool project lines for glossary gaps, pending terms, strays, and merges."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

from .cstl_io import ensure_cstl, load_cstl
from .helpers import has_cjk, latin_boundary_search, normalize_apostrophes

_TAGS = re.compile(r"</?[ib]>")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’]{2,}")
_LOWER = re.compile(r"(?<![A-Za-z'’-])[a-z][a-z-]{4,}(?![A-Za-z'’])")

_COMMON_WORDS = set(
    """the a an and or but if then else when while where why how what who whom whose which that this these those
    he she it they we you i me him her them his hers its their our your my mine ours theirs
    is are was were be been being am do does did done have has had having will would shall should can could may might must
    not no nor yes so as at by for from in into of off on onto out over to up with within without
    about after again against all also although among another any around because before besides both
    despite down during each either enough even ever every few finally first instead just last like
    many maybe more most much never next none nothing now once only other perhaps please right same
    several since some soon still such than thanks then there therefore though through thus too until very well yet
    okay yeah oh ah hey sir madam mister doctor captain commander lieutenant ensign admiral general colonel major chief
    mr mrs ms dr st chapter part one two three four five six seven eight nine ten
    yang dan ini itu dengan untuk dari akan adalah tidak saya aku kamu kau dia mereka kami kita ia
    anda beliau kalian ini itu ada sudah telah sedang belum masih bisa dapat boleh harus mau ingin
    jika kalau bila karena sebab maka jadi tapi namun atau serta agar supaya demi ke di pada oleh
    lagi juga pun saja hanya sangat terlalu paling lebih kurang semua setiap para suatu sebuah
    apa siapa mana kapan mengapa kenapa bagaimana berapa ya iya bukan jangan mari ayo halo hai
    baik benar salah maaf tolong terima kasih selamat pagi siang sore malam wah aduh hei eh hmm""".split()
)


def normalize_apo(s: str) -> str:
    return normalize_apostrophes(s)


def _load_locked(path: str) -> dict:
    if not path:
        return {"characters": [], "terms": []}
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _glossary_known(locked: dict) -> set[str]:
    known: set[str] = set()
    for c in locked.get("characters", []):
        for n in [c.get("canonical"), c.get("render")] + list(c.get("aliases") or []):
            if n:
                known.add(normalize_apo(str(n)).lower())
    for t in locked.get("terms", []):
        if t.get("src"):
            known.add(normalize_apo(str(t["src"])).lower())
        if t.get("dst"):
            known.add(normalize_apo(str(t["dst"])).lower())
    return known


def _proper_noun_vocab(lines: list[dict]) -> set[str]:
    vocab: set[str] = set()
    for ln in lines:
        src = normalize_apo(_TAGS.sub("", ln.get("message") or ""))
        for m in _WORD.finditer(src):
            w = m.group()
            if not w[0].isupper() or len(w) < 3:
                continue
            j = m.start() - 1
            if j >= 0 and src[j] == " ":
                j -= 1
            prev = src[j] if j >= 0 else ""
            if prev and (prev.islower() or prev in ",;:-"):
                vocab.add(w)
    return vocab


def discover_pending(lines: list[dict], known: set[str], min_count: int = 3) -> list[dict]:
    """Find recurring terms/speakers in untranslated lines not yet seen in translated lines or glossary."""
    done_cjk: set[str] = set()
    done_lat: set[str] = set()
    pend_cjk: dict[str, list[int]] = {}
    pend_lat: dict[str, list[int]] = {}

    for ln in lines:
        if ln.get("_hidden"):
            continue
        msg = _TAGS.sub("", ln.get("message") or "")
        name = (ln.get("name") or "").strip()
        num = ln.get("line_num")
        cjk_toks = set(re.findall(r"[\u3400-\u9fff]{2,8}|[\u30a0-\u30ff]{2,10}", msg))
        if name and has_cjk(name):
            cjk_toks.add(name)
        lat_toks = {m.group().lower() for m in _LOWER.finditer(normalize_apo(msg))} | {
            m.group().lower() for m in _WORD.finditer(normalize_apo(msg)) if m.group()[0].isupper()
        }
        if name and not has_cjk(name):
            lat_toks.add(normalize_apo(name).lower())

        if ln.get("is_translated"):
            done_cjk |= cjk_toks
            done_lat |= lat_toks
        else:
            for t in cjk_toks:
                pend_cjk.setdefault(t, []).append(num)
            for t in lat_toks:
                pend_lat.setdefault(t, []).append(num)

    out: list[dict] = []
    for tok, idxs in pend_cjk.items():
        idxs = sorted(set(idxs))
        if len(idxs) < min_count or tok in done_cjk or tok.lower() in known:
            continue
        spread = max(1, len({i // 50 for i in idxs}))
        out.append({"token": tok, "count": len(idxs), "burst": round(len(idxs) / spread, 2), "segments": idxs[:12]})

    merged_lat: dict[str, list[int]] = {}
    for tok, idxs in pend_lat.items():
        base = tok[:-1] if tok.endswith("s") and tok[:-1] in pend_lat else tok
        merged_lat.setdefault(base, []).extend(idxs)
    for tok, idxs in merged_lat.items():
        idxs = sorted(set(idxs))
        if len(idxs) < min_count or {tok, tok + "s"} & (done_lat | known | _COMMON_WORDS):
            continue
        spread = max(1, len({i // 50 for i in idxs}))
        out.append({"token": tok, "count": len(idxs), "burst": round(len(idxs) / spread, 2), "segments": idxs[:12]})

    out.sort(key=lambda r: (-(r["count"] * r["burst"]), r["token"]))
    return out[:50]


def scan(
    cstl_path: str,
    locked_path: str = "",
    mode: str = "all",
    min_merge_len: int = 15,
    min_count: int = 3,
) -> dict:
    data = ensure_cstl(load_cstl(cstl_path))
    locked = _load_locked(locked_path)
    known = _glossary_known(locked)
    lines = [ln for ln in data.get("lines", []) if not ln.get("_hidden")]

    result: dict = {}

    if mode in ("discover", "all"):
        discover: list[dict] = []
        counter: Counter[str] = Counter()
        speaker_variants: dict[str, Counter[str]] = {}
        for ln in lines:
            msg = _TAGS.sub("", ln.get("message") or "")
            for m in re.findall(r"[\u3400-\u9fff]{2,}", msg):
                if 2 <= len(m) <= 8:
                    counter[m] += 1
            for m in re.findall(r"[\u30a0-\u30ff]{2,}", msg):
                if 2 <= len(m) <= 10:
                    counter[m] += 1
            name = (ln.get("name") or "").strip()
            if name:
                if has_cjk(name):
                    counter[name] += 5
                if ln.get("is_translated") and (ln.get("trans_name") or "").strip():
                    speaker_variants.setdefault(name, Counter())[(ln.get("trans_name") or "").strip()] += 1

        for tok, c in counter.items():
            if c < 2 or normalize_apo(tok).lower() in known:
                continue
            examples = []
            for ln in lines:
                if tok in (ln.get("message") or "") or tok == (ln.get("name") or ""):
                    examples.append({"line_num": ln.get("line_num"), "message": (ln.get("message") or "")[:80]})
                    if len(examples) >= 3:
                        break
            discover.append({"tok": tok, "count": c, "examples": examples})

        # Also check mid-sentence Latin proper nouns (EN source) + inconsistent speaker renderings
        vocab = _proper_noun_vocab(lines)
        lat_kept: Counter[str] = Counter()
        lat_missing: dict[str, list[int]] = {}
        for ln in lines:
            if not ln.get("is_translated"):
                continue
            src = _TAGS.sub("", ln.get("message") or "")
            tgt = _TAGS.sub("", ln.get("trans_message") or "")
            if not tgt.strip():
                continue
            for m in _WORD.finditer(normalize_apo(src)):
                w = m.group()
                if w not in vocab or w.lower() in known or w.lower() in _COMMON_WORDS:
                    continue
                if latin_boundary_search(w, tgt, ignore_case=True):
                    lat_kept[w] += 1
                else:
                    lat_missing.setdefault(w, []).append(ln.get("line_num"))
        for w, idxs in lat_missing.items():
            if lat_kept.get(w, 0) > 0:
                discover.append({"tok": w, "count": len(idxs), "kind": "latin_inconsistent", "preserved": lat_kept[w], "lines": idxs[:8]})

        for sname, variants in speaker_variants.items():
            if len(variants) > 1:
                discover.append({"tok": sname, "count": sum(variants.values()), "kind": "speaker_drift", "variants": dict(variants)})

        discover.sort(key=lambda x: -x["count"])
        result["discover"] = discover[:50]

    if mode in ("terms", "all"):
        terms_hits: list[dict] = []
        for t in locked.get("terms", []):
            src = str(t.get("src") or "").strip()
            dst = str(t.get("dst") or "").strip()
            if not src or t.get("keep_source") or not dst or dst.lower() == src.lower():
                continue
            hits = []
            for ln in lines:
                if not ln.get("is_translated"):
                    continue
                msg = normalize_apo(ln.get("message") or "")
                tmsg = normalize_apo(ln.get("trans_message") or "")
                src_hit = (src in msg) if has_cjk(src) else (latin_boundary_search(src, msg, ignore_case=True) is not None)
                dst_hit = (dst in tmsg) if has_cjk(dst) else (latin_boundary_search(dst, tmsg, ignore_case=True) is not None)
                leak_hit = (src in tmsg) if has_cjk(src) else (latin_boundary_search(src, tmsg, ignore_case=True) is not None)
                if src_hit and not dst_hit and leak_hit:
                    hits.append({
                        "line_num": ln.get("line_num"),
                        "message": (ln.get("message") or "")[:60],
                        "trans_message": (ln.get("trans_message") or "")[:60],
                    })
            if hits:
                terms_hits.append({"src": src, "dst": dst, "hits": hits[:5]})
        result["terms"] = terms_hits

    if mode in ("strays", "all"):
        strays: list[dict] = []
        for ln in lines:
            if not ln.get("is_translated"):
                continue
            src = normalize_apo(_TAGS.sub("", ln.get("message") or ""))
            tmsg = normalize_apo(_TAGS.sub("", ln.get("trans_message") or ""))
            src_tokens = {w.lower() for w in re.findall(r"[A-Za-z]{2,}", src)}
            stray_tokens = [
                tok for tok in re.findall(r"[A-Za-z]{2,}", tmsg)
                if tok.lower() not in src_tokens
                and tok.lower() not in known
                and tok.lower() not in _COMMON_WORDS
                and len(tok) >= 3
            ]
            suspects = [t for t in stray_tokens if 2 <= len(t) <= 12 and t.istitle()]
            if suspects:
                strays.append({"line_num": ln.get("line_num"), "strays": suspects[:5], "trans_message": tmsg[:80]})
        result["strays"] = strays

    if mode in ("merges", "all"):
        merges: list[dict] = []
        for ln in lines:
            msg = _TAGS.sub("", ln.get("message") or "")
            tmsg = _TAGS.sub("", ln.get("trans_message") or "")
            for txt, kind in [(msg, "source"), (tmsg, "trans")]:
                for m in re.finditer(r"[A-Za-z]{10,}", txt):
                    tok = m.group(0)
                    if re.search(r"[a-z]{8,}[A-Z]", tok) or (len(tok) >= min_merge_len and tok.islower()):
                        merges.append({"line_num": ln.get("line_num"), "kind": kind, "token": tok})
        result["merges"] = merges

    if mode == "pending":
        result["pending"] = discover_pending(lines, known, min_count=min_count)

    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Scan CopasTool project for glossary gaps, pending terms, strays, merges")
    ap.add_argument("cstl_path")
    ap.add_argument("--locked", default="")
    ap.add_argument("--mode", choices=["all", "discover", "terms", "strays", "merges", "pending"], default="all")
    ap.add_argument("--min-merge-len", type=int, default=15)
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    res = scan(a.cstl_path, a.locked, mode=a.mode, min_merge_len=a.min_merge_len, min_count=a.min_count)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    total = sum(len(v) for v in res.values())
    if not a.json:
        print(f"\n{total} finding(s) across {list(res.keys())}")
    sys.stderr.write("; ".join(f"{k}: {len(v)}" for k, v in res.items()) + "\n")


if __name__ == "__main__":
    main()
