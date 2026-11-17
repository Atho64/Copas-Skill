"""Adversarial & dual-model review pipeline (deterministic half) for CopasTool backups.

Subcommands:
  blind       strip source text -> groups/blind_X.json for Blind Reader
  hints       validate Blind Reader flags_X.jsonl -> hints_X.json
  rules       per-group slice of glossary + EXAMPLES.md + state card -> rules_X.json
  check       read-only lint of Reviewer's findings_X.jsonl (exits 1 on error)
  pre         mechanical gate -> findings_X.pre.jsonl + rejected_X.jsonl
  segs        split pre-gated findings for Challenger (--mode slim|tier|all)
  inventory   extract recurring JP/EN terms, speakers, and callbacks -> inventory.json
  stats       per-stage yield & Challenger reject rate -> stats.md
  final       merge Challenger verdicts -> apply_X.json (A/B) + review_X.md (C/D/human)
  merge       combine leftover C/D/human findings across groups -> review_ALL.md
  pick        select ids / --min-sev from review lists -> apply_pick.json
  benchmark   diff current project against baseline snapshot -> benchmark.json
  score       recall / precision against benchmark.json -> scores.md
  log         append provenance/token row to review_log.jsonl
  ledger      summarize tokens/segment from review_log.jsonl
  import      normalize external findings JSON/JSONL -> findings_X.jsonl
  dual-merge  merge two independent reviewer lists -> editor input sorted by agree
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
import re

from . import audit, cstl_io, glossary as glossary_mod, langpair, state
from .helpers import has_cjk, latin_boundary_search, normalize_apostrophes

LATIN = re.compile(r"[A-Za-z][A-Za-z’'\-]*")
HAN = re.compile(r"[\u4e00-\u9fff]")
JP_TERM = re.compile(r"[\u3400-\u9fff]{2,8}|[\u30a0-\u30ff]{2,10}")
NEVER = re.compile(r"(?!x)x")

DEFAULT_SOFT_BLOCK_LATIN = ["kana_residue", "kanji_residue", "jp_punct", "space_before_punct", "odd_quotes", "english_sfx_residue"]
DEFAULT_SOFT_BLOCK_CJK = ["jp_punct", "odd_quotes"]
DEFAULT_LEAK_FILES = ["DEFECT_TAXONOMY.md", "AI_FLAVOR_CHECKLIST.md", "EXAMPLES.md"]

CATEGORY_RE = re.compile(
    r"(?:reclassif\w*\s+as|change\s+to|downgrade\s+to|upgrade\s+to|ubah\s+ke|turun\s+ke|naik\s+ke|降为|升为|改为|应为|应归|归为|as)\s*([ABCD])(?![A-Za-z])",
    re.I,
)
SEVERITY_RE = re.compile(
    r"(?:severity|sev)\D{0,8}([123])\D{0,8}(?:to|->|→|ke|改为|降为|应为)\s*([123])",
    re.I,
)
REWRITE_MIN_VISIBLE = 25
REWRITE_MIN_HAN = 12
REWRITE_RATIO = (0.45, 2.2)

_STOP = set(
    "the a an of to in on at for and or but with by from as is was were be been his her its their "
    "he she it they them him this that these those into onto over under out up down off "
    "yang dan ini itu di ke dari untuk dengan pada oleh adalah tidak akan sudah telah".split()
)
EX_STOP = _STOP | {
    "what", "when", "will", "your", "said", "just", "like", "have", "then", "than",
    "been", "only", "some", "yes", "not", "all", "one", "out",
}


# ---------------------------------------------------------------------- IO ----
def _line_num(row: dict) -> int:
    if "line_num" in row:
        return int(row["line_num"])
    if "text_index" in row:
        return int(row["text_index"])
    return int(row["i"])


def _normalize_finding(row: dict) -> dict:
    r = dict(row)
    if "line_num" not in r and ("text_index" in r or "i" in r):
        r["line_num"] = _line_num(r)
    return r


def read_jsonl(p: str) -> list[dict]:
    with open(p, "r", encoding="utf-8-sig") as f:
        return [_normalize_finding(json.loads(l)) for l in f if l.strip()]


def write_jsonl(p: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def append_jsonl(p: str, rows: list[dict]) -> None:
    if not rows:
        return
    os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_json(p: str, obj) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def group_of(path: str) -> str:
    m = re.search(r"(?:findings|verdicts|flags)_([A-Za-z0-9]+)", os.path.basename(path))
    if not m:
        raise ValueError(f"cannot infer group id from {path!r} (expected findings_X / flags_X .jsonl)")
    return m.group(1)


class Paths:
    def __init__(self, project: str, dir: str | None = None, run: str | None = None):
        self.project = project
        self.root = dir or os.path.join(os.path.dirname(os.path.abspath(project)), "review")
        self.dir = os.path.join(self.root, run) if run else self.root
        self.groups = os.path.join(self.dir, "groups")

    def f(self, name: str) -> str:
        return os.path.join(self.dir, name)

    def shared(self, name: str) -> str:
        p = self.f(name)
        return p if os.path.exists(p) else os.path.join(self.root, name)

    def group_src(self, g: str) -> dict[int, dict]:
        p = os.path.join(self.groups, f"grp_{g}_src.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8-sig") as f:
                rows = json.load(f)
            return {_line_num(r): {
                "line_num": _line_num(r),
                "file": r.get("file", ""),
                "name": r.get("name"),
                "message": r.get("message") or r.get("source_text") or "",
                "trans_name": r.get("trans_name"),
                "trans_message": r.get("trans_message") if "trans_message" in r else (r.get("translated_text") or ""),
            } for r in rows}
        data = cstl_io.ensure_cstl(cstl_io.load_cstl(self.project))
        return {
            int(ln["line_num"]): {
                "line_num": int(ln["line_num"]),
                "file": ln.get("file", ""),
                "name": ln.get("name"),
                "message": ln.get("message") or "",
                "trans_name": ln.get("trans_name"),
                "trans_message": ln.get("trans_message") or "",
            }
            for ln in cstl_io.ordered_lines(data)
            if not ln.get("_hidden") and (ln.get("message") or "").strip()
        }


# ------------------------------------------------------------------- Rules ----
class Rules:
    def __init__(
        self,
        cfg: dict,
        glossary_dst: list[str] = (),
        protected_removals: dict | None = None,
        protected_names: set[str] = (),
        source_lang: str = "Japanese",
        target_lang: str = "Indonesian",
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.tc = langpair.lang_code(target_lang)
        self.protected = protected_removals or {}
        self.protected_names = {normalize_apostrophes(n) for n in protected_names if n}
        self.token_exc: set[int] = set()
        self.lint_rules = ()

        red = [r if isinstance(r, str) else r["re"] for r in cfg.get("redline", [])]
        self.redline = re.compile("|".join(red)) if red else NEVER
        self.redline_hard = [
            re.compile(r if isinstance(r, str) else r["re"])
            for r in cfg.get("redline", [])
            if isinstance(r, str) or not r.get("waivable")
        ]

        settled = sorted(set(cfg.get("settled", [])), key=len, reverse=True)
        gl = sorted({re.escape(t) for t in glossary_dst} if cfg.get("glossary_settled", True) else (),
                    key=len, reverse=True)
        self.settled = re.compile("|".join(settled)) if settled else NEVER
        self.settled_gl = re.compile("|".join(gl)) if gl else NEVER
        self.settled_all = re.compile("|".join(sorted(settled + gl, key=len, reverse=True))) if settled or gl else NEVER

        if "forbid" in cfg:
            forbid = cfg["forbid"]
        elif self.tc in langpair.LATIN_TARGETS:
            forbid = r"[\u3001\u3002\uff01\uff1f\u3000]"
        else:
            forbid = r"[「」\"]"
        self.forbid = re.compile(forbid) if forbid else NEVER

        default_sb = DEFAULT_SOFT_BLOCK_LATIN if self.tc in langpair.LATIN_TARGETS else DEFAULT_SOFT_BLOCK_CJK
        self.soft_block = set(cfg.get("soft_block", default_sb))
        self.term_only = [tuple(x) for x in cfg.get("term_only", [])]
        self.norm = [(re.compile(p), r) for p, r in cfg.get("norm", [])]
        self.leak_files = list(cfg.get("leak_files", DEFAULT_LEAK_FILES))

    def settled_removed(self, off: str, prop: str) -> set[str]:
        was, kept = set(self.settled_all.findall(off)), set(self.settled_all.findall(prop))
        new = kept - was
        return {t for t in was - kept if not any(t in k for k in new)}

    def violation(self, off: str, prop: str, waiver: bool = False, category: str = "") -> tuple[str, set[str]]:
        if self.forbid.search(prop):
            return "forbid_char", set()
        if collections.Counter(self.redline.findall(off)) != collections.Counter(self.redline.findall(prop)):
            if not waiver or any(collections.Counter(rx.findall(off)) != collections.Counter(rx.findall(prop))
                                 for rx in self.redline_hard):
                return "E_redline", set()
        gone = self.settled_removed(off, prop)
        if gone and not (category == "A" and all(self.settled_gl.fullmatch(t) and not self.settled.fullmatch(t)
                                                 for t in gone)):
            return "E_settled_removed", set()
        return "", gone

    def normalize(self, s: str) -> str:
        for a, b in self.term_only:
            s = s.replace(a, b)
        for rx, r in self.norm:
            s = rx.sub(r, s)
        return re.sub(r"\s+", " ", s).strip()


def load_rules(paths: Paths, locked: str | None = None) -> Rules:
    cfg = {}
    cp = paths.shared("config.json")
    if os.path.exists(cp):
        with open(cp, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)

    data = cstl_io.ensure_cstl(cstl_io.load_cstl(paths.project))
    sl = data.get("source_lang", "Japanese")
    tl = data.get("target_lang", "Indonesian")

    dst: list[str] = []
    prot_names: set[str] = set()
    locked = locked or cfg.get("glossary") or os.path.join(
        os.path.dirname(os.path.abspath(paths.project)), "glossary.locked.json"
    )
    if locked and os.path.exists(locked):
        with open(locked, "r", encoding="utf-8-sig") as f:
            gl = json.load(f)
        for c in gl.get("characters", []):
            for n in [c.get("canonical"), c.get("render")] + list(c.get("aliases") or []):
                if n and not has_cjk(str(n)):
                    prot_names.add(str(n).strip())
        for t in gl.get("terms", []):
            src_t = str(t.get("src") or "").strip()
            dst_t = str(t.get("dst") or "").strip()
            if t.get("keep_source") and src_t and not has_cjk(src_t):
                prot_names.add(src_t)
            elif dst_t:
                if not has_cjk(dst_t) and dst_t[0].isupper():
                    prot_names.add(dst_t)
                if cfg.get("glossary_settled", True):
                    dst.append(dst_t)

    d = state.load(paths.project)
    cfg = dict(cfg, settled=list(cfg.get("settled", [])) + [re.escape(x) for x in state.settled_dst(d)])
    r = Rules(
        cfg,
        glossary_dst=dst,
        protected_removals=state.protected_removals(paths.project),
        protected_names=prot_names,
        source_lang=sl,
        target_lang=tl,
    )
    r.token_exc = state.token_exceptions(d)
    r.lint_rules = state.lint_rules(d)
    return r


# ------------------------------------------------------------------- Gate ----
def _protected_in_span(text: str, seg: dict, rules: Rules) -> collections.Counter:
    """Count protected proper-noun occurrences in `text` (safe for Latin prose targets)."""
    norm_text = normalize_apostrophes(text)
    if rules.tc not in langpair.LATIN_TARGETS:
        return collections.Counter(LATIN.findall(norm_text))

    # For Latin targets (Indonesian / English), only protect:
    # 1. Glossary character names/aliases/keep_source/capitalized terms
    # 2. Speaker names
    # 3. Latin tokens that appear verbatim in BOTH the line's source message and its current translation
    src_lat = set(LATIN.findall(normalize_apostrophes(seg.get("message") or "")))
    old_lat = set(LATIN.findall(normalize_apostrophes(seg.get("trans_message") or "")))
    line_prot = {t for t in (src_lat & old_lat) if len(t) >= 2}
    if seg.get("trans_name"):
        line_prot.update(LATIN.findall(normalize_apostrophes(seg["trans_name"])))
    if seg.get("name"):
        line_prot.update(LATIN.findall(normalize_apostrophes(seg["name"])))

    candidates = {tok for tok in (rules.protected_names | line_prot) if len(tok) >= 2 and tok.lower() not in _STOP}
    counts: collections.Counter = collections.Counter()
    for cand in sorted(candidates, key=len, reverse=True):
        if has_cjk(cand):
            n = norm_text.count(cand)
        else:
            n = len(re.findall(rf"(?<![A-Za-z]){re.escape(cand)}(?![A-Za-z])", norm_text))
        if n:
            counts[cand] = n
    return counts


def check(f: dict, seg: dict | None, rules: Rules) -> tuple[bool, str, str | None, list[str]]:
    req = ("id", "line_num", "category", "offending", "proposed")
    if any(k not in f or f[k] in (None, "") for k in req):
        return False, "missing_field", None, []
    if f["category"] not in ("A", "B", "C", "D"):
        return False, "bad_category", None, []
    if seg is None:
        return False, "unknown_index", None, []

    old = seg["trans_message"]
    off, prop = f["offending"], f["proposed"]
    n = old.count(off)
    if n != 1:
        return False, f"ambiguous({n})", None, []

    why, override = rules.violation(off, prop, waiver=bool(f.get("redline_waiver")), category=f["category"])
    if why:
        return False, why, None, []

    if rules.tc in langpair.LATIN_TARGETS:
        v_off, v_prop = len(langpair.visible(off)), len(langpair.visible(prop))
        if v_off >= REWRITE_MIN_VISIBLE and not (REWRITE_RATIO[0] <= v_prop / max(1, v_off) <= REWRITE_RATIO[1]):
            return False, f"rewrite_length({v_prop}/{v_off})", None, []
    else:
        h_off, h_prop = len(HAN.findall(off)), len(HAN.findall(prop))
        if h_off >= REWRITE_MIN_HAN and not (REWRITE_RATIO[0] <= h_prop / h_off <= REWRITE_RATIO[1]):
            return False, f"rewrite_length({h_prop}/{h_off})", None, []

    new = old.replace(off, prop, 1)
    num = int(f["line_num"])
    probe_old = {**seg, "trans_message": old}
    probe_new = {**seg, "trans_message": new}
    hard, soft_new = audit.lint_line(
        probe_new,
        source_lang=rules.source_lang,
        target_lang=rules.target_lang,
        token_exceptions=rules.token_exc,
        rules=rules.lint_rules,
    )
    if hard:
        return False, "tag:" + ",".join(hard), None, []
    _, soft_old = audit.lint_line(
        probe_old,
        source_lang=rules.source_lang,
        target_lang=rules.target_lang,
        token_exceptions=rules.token_exc,
        rules=rules.lint_rules,
    )
    added = (set(soft_new) - set(soft_old)) & rules.soft_block
    if added:
        return False, "soft:" + ",".join(sorted(added)), None, []

    if _protected_in_span(off, seg, rules) != _protected_in_span(prop, seg, rules):
        if not (f.get("latin_change") and f["category"] == "A"):
            return False, "name_touch", None, []

    back = [x for x in rules.protected.get(num, ()) if x in new and x not in old]
    if back:
        return False, "E_reverts_fix", None, []
    return True, "", new, sorted(override)


def _seg(segs: dict[int, dict], ln_id) -> dict | None:
    if isinstance(ln_id, int) and not isinstance(ln_id, bool):
        return segs.get(ln_id)
    if isinstance(ln_id, str) and ln_id.isdigit():
        return segs.get(int(ln_id))
    return None


def _flag_ids(paths: Paths, g: str) -> set | None:
    fp = paths.f(f"flags_{g}.jsonl")
    return {x.get("id") for x in read_jsonl(fp)} if os.path.exists(fp) else None


def check_file(paths: Paths, rules: Rules, g: str, path: str | None = None) -> list[str]:
    path = path or paths.f(f"findings_{g}.jsonl")
    segs = paths.group_src(g)
    flag_ids = _flag_ids(paths, g)
    errs, seen, cat, sev = [], set(), collections.Counter(), collections.Counter()
    with open(path, encoding="utf-8-sig") as fh:
        lines = fh.readlines()
    for ln, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            f = _normalize_finding(json.loads(raw))
        except ValueError as e:
            errs.append(f"L{ln}: bad JSON ({e})")
            continue
        i = f.get("id") or f"L{ln}"
        miss = [k for k in ("id", "line_num", "category", "severity", "offending", "proposed", "reason")
                if f.get(k) in (None, "")]
        if miss:
            errs.append(f"{i}: missing {miss}")
            continue
        if i in seen:
            errs.append(f"{i}: duplicate id")
        seen.add(i)
        c, s = f["category"], f["severity"]
        if s not in (1, 2, 3):
            errs.append(f"{i}: severity must be 1/2/3")
        if c == "D" and g != "D":
            errs.append(f"{i}: no D findings (cross-line consistency belongs to Consistency auditor)")
        elif c == "C" and s == 1:
            errs.append(f"{i}: drop C severity 1 (not adopted by default)")
        if c in ("A", "C") and not f.get("source_evidence"):
            errs.append(f"{i}: source_evidence required for {c}")
        if flag_ids is not None and set(f.get("flags") or ()) - flag_ids:
            errs.append(f"{i}: unknown flags {sorted(set(f['flags']) - flag_ids)}")
        ok, why, _, _ = check(f, _seg(segs, f["line_num"]), rules)
        if not ok:
            errs.append(f"{i}: gate {why}")
        cat[c] += 1
        sev[s] += 1
    print("\n".join(errs) if errs else "OK")
    print(f"[{g}] findings={len(seen)} cat={dict(sorted(cat.items(), key=str))} sev={dict(sorted(sev.items(), key=str))} errors={len(errs)}")
    return errs


def pre(paths: Paths, rules: Rules, files: list[str]) -> list[dict]:
    out = []
    for p in files:
        g = group_of(p)
        segs = paths.group_src(g)
        ok_rows, bad_rows, stats = [], [], collections.Counter()
        for f in read_jsonl(p):
            ok, why, new, override = check(f, _seg(segs, f.get("line_num")), rules)
            if ok:
                f["_new_text"] = new
                if override:
                    f["_settled_override"] = override
                if f.get("redline_waiver") or override:
                    f["_force_challenge"] = True
                if f.get("latin_change") and f["category"] == "A":
                    f["_human"] = True
                ok_rows.append(f)
                stats[f["category"]] += 1
            else:
                f["_reject"] = why
                bad_rows.append(f)
                stats["rej:" + why.split("(")[0].split(":")[0]] += 1
        write_jsonl(paths.f(f"findings_{g}.pre.jsonl"), ok_rows)
        write_jsonl(paths.f(f"rejected_{g}.jsonl"), bad_rows)
        row = {"group": g, "in": len(ok_rows) + len(bad_rows), "ok": len(ok_rows), "rejected": len(bad_rows), "stats": dict(stats)}
        out.append(row)
        print(f"[{g}] in={row['in']} ok={row['ok']} rejected={row['rejected']}  {row['stats']}")
    return out


MODES = ("all", "tier", "slim")


def needs_challenge(f: dict, min_sev: int = 3, sample: float = 0.0, mode: str = "tier") -> str:
    if f.get("_force_challenge") or f.get("redline_waiver"):
        return "waiver"
    if f.get("latin_change"):
        return "latin"
    if mode == "all":
        return "all"
    if mode == "slim":
        if f.get("category") in ("A", "B"):
            return "ab"
        return "" if f.get("flags") else "unflagged"
    if not f.get("flags"):
        return "unflagged"
    if int(f.get("severity") or 0) >= min_sev:
        return "severity"
    if sample and int(hashlib.md5(str(f["id"]).encode()).hexdigest(), 16) % 10000 < sample * 10000:
        return "sample"
    return ""


def segs_for(paths: Paths, files: list[str], tier: bool = False, min_sev: int = 3, sample: float = 0.0, mode: str | None = None) -> None:
    mode = mode or ("tier" if tier else "all")
    note = {
        "tier": "auto: corroborated by Blind Reader flag",
        "slim": "auto: flagged C/D, goes to human review list",
    }.get(mode, "")
    for p in files:
        g = group_of(p)
        segs = paths.group_src(g)
        fs = read_jsonl(p)
        why = {f["id"]: needs_challenge(f, min_sev, sample, mode) for f in fs}
        chal = [f for f in fs if why[f["id"]]]
        auto = [{"id": f["id"], "verdict": "accept", "reason": note} for f in fs if not why[f["id"]]]
        write_jsonl(paths.f(f"challenge_{g}.jsonl"), [{k: v for k, v in f.items() if k != "_new_text"} for f in chal])
        ap = paths.f(f"verdicts_{g}.auto.jsonl")
        if auto:
            write_jsonl(ap, auto)
        elif os.path.exists(ap):
            os.remove(ap)
        idx = sorted({int(f["line_num"]) for f in chal})
        rows = [
            {
                "line_num": i,
                "file": segs[i].get("file", ""),
                "name": segs[i].get("name"),
                "message": segs[i]["message"],
                "trans_name": segs[i].get("trans_name"),
                "trans_message": segs[i]["trans_message"],
            }
            for i in idx if i in segs
        ]
        op = paths.f(f"segs_{g}.json")
        write_json(op, rows)
        mix = collections.Counter(why[f["id"]] for f in chal)
        print(f"[{g}] challenge={len(chal)} auto={len(auto)} segs={len(rows)} {dict(mix)} -> {op}"
              + ("" if chal else "  (nothing to challenge)"))


def blind(paths: Paths, groups: list[str]) -> None:
    for g in groups:
        segs = paths.group_src(g)
        rows = [
            {
                "line_num": i,
                "file": r.get("file", ""),
                "trans_name": r.get("trans_name"),
                "trans_message": r["trans_message"],
            }
            for i, r in sorted(segs.items())
        ]
        ctx_p = os.path.join(paths.groups, f"grp_{g}_ctx.json")
        ctx = []
        if os.path.exists(ctx_p):
            with open(ctx_p, encoding="utf-8-sig") as f:
                raw_ctx = json.load(f)
            arr = raw_ctx.get("context_before", []) if isinstance(raw_ctx, dict) else raw_ctx
            ctx = [
                {"line_num": _line_num(r), "trans_name": r.get("trans_name"), "trans_message": r.get("trans_message") or ""}
                for r in arr
            ]
        op = os.path.join(paths.groups, f"blind_{g}.json")
        write_json(op, {"context": ctx, "lines": rows})
        print(f"[{g}] blind lines={len(rows)} context={len(ctx)} -> {op}")


def hints(paths: Paths, files: list[str]) -> list[dict]:
    out = []
    for p in files:
        g = group_of(p)
        segs = paths.group_src(g)
        per, bad = collections.defaultdict(list), []
        for fl in read_jsonl(p):
            num = fl.get("line_num")
            seg = _seg(segs, num)
            q = (fl.get("quote") or "").strip()
            if seg is None:
                fl["_reject"] = "unknown_index"
            elif not q or (q not in seg["trans_message"] and q not in (seg.get("trans_name") or "")):
                fl["_reject"] = "quote_not_found"
            else:
                per[int(num)].append({k: fl.get(k) for k in ("id", "quote", "why", "severity") if fl.get(k) is not None})
                continue
            bad.append(fl)
        rows = [
            {
                "line_num": i,
                "file": segs[i].get("file", ""),
                "name": segs[i].get("name"),
                "message": segs[i]["message"],
                "trans_name": segs[i].get("trans_name"),
                "trans_message": segs[i]["trans_message"],
                "flags": fl,
            }
            for i, fl in sorted(per.items())
        ]
        write_json(paths.f(f"hints_{g}.json"), rows)
        write_jsonl(paths.f(f"rejected_flags_{g}.jsonl"), bad)
        row = {"group": g, "flags": sum(len(v) for v in per.values()), "lines": len(rows), "rejected": len(bad)}
        out.append(row)
        print(f"[{g}] flags={row['flags']} on {row['lines']} lines, rejected={row['rejected']} -> hints_{g}.json")
    return out


def _apply_verdicts(findings: dict, verdicts: dict, segs: dict, rules: Rules):
    per_seg, rej = collections.defaultdict(list), []
    for fid, f in findings.items():
        v = verdicts.get(fid)
        if not v or v.get("verdict") == "reject":
            f["_reject"] = "challenger:" + (v.get("reason", "") if v else "no_verdict")
            rej.append(f)
            continue
        if v.get("verdict") == "amend" and v.get("amended"):
            f["proposed"] = v["amended"]
            ok, why, _, _ = check(f, segs.get(int(f["line_num"])), rules)
            if not ok:
                f["_reject"] = "amend_failed:" + why
                rej.append(f)
                continue
        reason = v.get("reason", "") or ""
        f["_verdict_reason"] = reason
        m = CATEGORY_RE.search(reason)
        if m:
            f["category"] = m.group(1).upper()
        m = SEVERITY_RE.search(reason)
        if m:
            f["severity"] = int(m.group(2))
        per_seg[int(f["line_num"])].append(f)
    return per_seg, rej


def final(paths: Paths, rules: Rules, groups: list[str]) -> list[dict]:
    out = []
    for g in groups:
        fp, vp = paths.f(f"findings_{g}.pre.jsonl"), paths.f(f"verdicts_{g}.jsonl")
        if not os.path.exists(fp):
            print(f"[{g}] no {os.path.basename(fp)}, skip (run `pre` first)")
            continue
        findings = {f["id"]: f for f in read_jsonl(fp)}
        autop = paths.f(f"verdicts_{g}.auto.jsonl")
        if os.path.exists(vp) or os.path.exists(autop):
            verdicts = {v["id"]: v for v in read_jsonl(autop)} if os.path.exists(autop) else {}
            if os.path.exists(vp):
                verdicts.update({v["id"]: v for v in read_jsonl(vp)})
            elif not (os.path.exists(cp := paths.f(f"challenge_{g}.jsonl")) and not read_jsonl(cp)):
                print(f"[{g}] WARNING: no {os.path.basename(vp)}; challenged findings count as no_verdict")
        else:
            verdicts = {fid: {"verdict": "accept", "reason": "no challenger"} for fid in findings}
        segs = paths.group_src(g)
        per_seg, rej = _apply_verdicts(findings, verdicts, segs, rules)
        apply_rows, review_rows = [], []
        for idx, fs in per_seg.items():
            seg = segs[idx]
            text = seg["trans_message"]
            auto = [f for f in fs if f["category"] in ("A", "B") and not f.get("_human")]
            manual = [f for f in fs if f not in auto]
            kept = []
            for f in auto:
                if text.count(f["offending"]) == 1:
                    text = text.replace(f["offending"], f["proposed"], 1)
                    kept.append(f)
                else:
                    f["_reject"] = "apply_conflict"
                    rej.append(f)
            if kept:
                hard, _ = audit.lint_line(
                    {**seg, "trans_message": text},
                    source_lang=rules.source_lang,
                    target_lang=rules.target_lang,
                    token_exceptions=rules.token_exc,
                )
                if hard:
                    for f in kept:
                        f["_reject"] = "combined_tag"
                        rej.append(f)
                else:
                    apply_rows.append({"line_num": idx, "polished_text": text, "_findings": [f["id"] for f in kept]})
            review_rows.extend(manual)
        apply_rows.sort(key=lambda r: r["line_num"])
        review_rows.sort(key=lambda r: (-int(r.get("severity") or 0), int(r["line_num"])))
        write_json(paths.f(f"apply_{g}.json"), [{k: v for k, v in r.items() if not k.startswith("_")} for r in apply_rows])
        write_json(paths.f(f"apply_{g}.meta.json"), apply_rows)
        _write_review_md(paths.f(f"review_{g}.md"), review_rows, f"Review List ({g}) — C/D & Human-Only A")
        append_jsonl(paths.f(f"rejected_{g}.jsonl"), rej)
        row = {"group": g, "apply_lines": len(apply_rows), "review": len(review_rows), "rejected": len(rej)}
        out.append(row)
        print(f"[{g}] apply(A/B)={row['apply_lines']} lines  review(C/D/human)={row['review']}  rejected={row['rejected']}")
    return out


def rules_slice(paths: Paths, groups: list[str], locked: str | None, examples: list[str]) -> list[dict]:
    gl = {}
    if locked and os.path.exists(locked):
        with open(locked, encoding="utf-8-sig") as f:
            gl = json.load(f)
    bullets = []
    for ex in examples:
        if not os.path.exists(ex):
            continue
        cur = None
        with open(ex, encoding="utf-8-sig") as f:
            for line in f:
                if re.match(r"\s*(?:[-*]|\d+\.|\|)\s", line):
                    cur = [line.rstrip("\n")]
                    bullets.append(cur)
                elif cur is not None and line.strip() and line.startswith((" ", "\t")):
                    cur.append(line.rstrip("\n"))
                else:
                    cur = None
    bullets = ["\n".join(b) for b in bullets]
    lat_words = [
        {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z’'\-]{2,}", normalize_apostrophes(b)) if w.lower() not in EX_STOP}
        for b in bullets
    ]
    cjk_words = [set(JP_TERM.findall(b)) for b in bullets]
    full = sum(len(b) for b in bullets)

    out = []
    for g in groups:
        segs = paths.group_src(g)
        src_texts = [r["message"] for r in segs.values()]
        src_names = [r["name"] for r in segs.values() if r.get("name")]
        corpus_raw = normalize_apostrophes("\n".join(src_texts + src_names))
        corpus_low = corpus_raw.lower()
        general, hit = [], []
        for b, lw, cw in zip(bullets, lat_words, cjk_words):
            if not lw and not cw:
                general.append(b)
            elif any(latin_boundary_search(x, corpus_low, ignore_case=True) for x in lw) or any(x in corpus_raw for x in cw):
                hit.append(b)
        sub = glossary_mod.filter_locked(gl, src_texts, src_names) if gl else {}
        nums = sorted(segs)
        obj = {
            "group": g,
            "glossary": sub.get("terms", []),
            "characters": sub.get("characters", []),
            "general": general,
            "rulings": hit,
            "decisions": state.card(paths.project, nums[0], nums[-1]) if nums else "",
        }
        op = paths.f(f"rules_{g}.json")
        write_json(op, obj)
        size = sum(len(b) for b in general + hit)
        row = {"group": g, "glossary": len(obj["glossary"]), "rulings": len(hit), "general": len(general), "chars": size, "of": full}
        out.append(row)
        print(f"[{g}] glossary={row['glossary']} rulings={row['rulings']} general={row['general']} ({size}/{full} chars) -> {op}")
    return out


def stats(paths: Paths, groups: list[str]) -> str:
    flags = used = 0
    gate = collections.Counter()
    tot, rej = collections.Counter(), collections.Counter()
    for g in groups:
        fp = paths.f(f"findings_{g}.jsonl")
        if not os.path.exists(fp):
            continue
        F = read_jsonl(fp)
        fl = _flag_ids(paths, g) or set()
        flags += len(fl)
        used += len(fl & {x for f in F for x in (f.get("flags") or [])})
        rp = paths.f(f"rejected_{g}.jsonl")
        if os.path.exists(rp):
            for r in read_jsonl(rp):
                gate[str(r.get("_reject", "")).split("(")[0].split(":")[0]] += 1
        vp = paths.f(f"verdicts_{g}.jsonl")
        V = {v["id"]: v for v in read_jsonl(vp)} if os.path.exists(vp) else {}
        for f in F:
            if f["id"] in V:
                k = ("flag" if f.get("flags") else "noflag", f.get("category"), int(f.get("severity") or 0))
                tot[k] += 1
                rej[k] += V[f["id"]].get("verdict") == "reject"
    L = [
        f"# review stats ({len(groups)} groups)", "",
        f"- Blind flags: {flags}, used by a finding: {used}" + (f" ({used / flags:.0%})" if flags else ""),
        "- Gate rejects: " + (", ".join(f"{k} {v}" for k, v in gate.most_common()) or "none"), "",
        "| flag | cat | sev | challenged | rejected | rate |",
        "|---|---|---|---|---|---|",
    ]
    for k in sorted(tot):
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | {tot[k]} | {rej[k]} | {rej[k] / tot[k]:.1%} |")
    for side in ("flag", "noflag"):
        t = sum(v for k, v in tot.items() if k[0] == side)
        r = sum(v for k, v in rej.items() if k[0] == side)
        if t:
            L.append(f"| **{side}** | | | {t} | {r} | {r / t:.1%} |")
    txt = "\n".join(L) + "\n"
    with open(paths.f("stats.md"), "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)
    return txt


def _esc(s) -> str:
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def _write_review_md(path: str, rows: list[dict], title: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {title} ({len(rows)} items, sorted by severity)\n\n")
        f.write("Pick IDs with `review pick ... --ids ...` or `--min-sev 2 --exclude ...`, then `batch apply --source user`.\n\n")
        f.write("| id | line | cat/sev | current | proposed | reviewer | challenger |\n|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(
                f"| {r['id']} | {r['line_num']} | {r['category']}/{r.get('severity', '')} | "
                f"{_esc(r['offending'])} | {_esc(r['proposed'])} | {_esc(r.get('reason', ''))[:80]} | "
                f"{_esc(r.get('_verdict_reason', ''))[:80]} |\n"
            )


def leftover(paths: Paths, groups: list[str]) -> list[dict]:
    rows = []
    for g in groups:
        fp = paths.f(f"findings_{g}.pre.jsonl")
        if not os.path.exists(fp):
            continue
        fs = {f["id"]: f for f in read_jsonl(fp)}
        vp = paths.f(f"verdicts_{g}.jsonl")
        vs = {v["id"]: v for v in read_jsonl(vp)} if os.path.exists(vp) else {}
        mp = paths.f(f"apply_{g}.meta.json")
        applied = set()
        if os.path.exists(mp):
            with open(mp, encoding="utf-8-sig") as f:
                applied = {i for r in json.load(f) for i in r.get("_findings", [])}
        for fid, f in fs.items():
            v = vs.get(fid, {"verdict": "accept", "reason": "no challenger"})
            if v.get("verdict") == "reject" or fid in applied:
                continue
            f = dict(f)
            if v.get("amended"):
                f["proposed"] = v["amended"]
            f["_verdict_reason"] = v.get("reason", "")
            m = CATEGORY_RE.search(f["_verdict_reason"] or "")
            if m:
                f["category"] = m.group(1).upper()
            m = SEVERITY_RE.search(f["_verdict_reason"] or "")
            if m:
                f["severity"] = int(m.group(2))
            rows.append(f)
    rows.sort(key=lambda r: (-int(r.get("severity") or 0), int(r["line_num"])))
    return rows


def merge(paths: Paths, groups: list[str], out: str | None = None) -> int:
    rows = leftover(paths, groups)
    out = out or paths.f("review_ALL.md")
    _write_review_md(out, rows, f"Merged Review List ({', '.join(groups)})")
    tally = dict(collections.Counter(f"{r['category']}/{r.get('severity', '')}" for r in rows))
    print(f"merged {len(rows)} -> {out}  {tally}")
    return len(rows)


def pick(paths: Paths, rules: Rules, ids: list[str], groups: list[str], out: str | None = None, min_sev: int | None = None, exclude=()) -> int:
    want = set(ids or ())
    if min_sev is not None:
        want |= {f["id"] for f in leftover(paths, groups) if int(f.get("severity") or 0) >= min_sev}
    want -= set(exclude or ())
    chosen = collections.defaultdict(list)
    for g in groups:
        fp = paths.f(f"findings_{g}.pre.jsonl")
        if not os.path.exists(fp):
            continue
        vp = paths.f(f"verdicts_{g}.jsonl")
        vs = {v["id"]: v for v in read_jsonl(vp)} if os.path.exists(vp) else {}
        for f in read_jsonl(fp):
            if f["id"] in want:
                if vs.get(f["id"], {}).get("amended"):
                    f["proposed"] = vs[f["id"]]["amended"]
                chosen[int(f["line_num"])].append(f)
                want.discard(f["id"])
    if want:
        print(f"unknown ids: {sorted(want)}")
    data = cstl_io.ensure_cstl(cstl_io.load_cstl(paths.project))
    cur = {int(ln["line_num"]): ln for ln in data.get("lines", [])}
    rows, skipped = [], []
    for idx, fs in chosen.items():
        ln = cur.get(idx)
        if ln is None:
            skipped.append((idx, "unknown_index"))
            continue
        text = ln.get("trans_message") or ""
        applied = []
        for f in fs:
            if text.count(f["offending"]) != 1:
                skipped.append((f["id"], "offending not found once in current text"))
                continue
            text = text.replace(f["offending"], f["proposed"], 1)
            applied.append(f["id"])
        if applied:
            hard, _ = audit.lint_line(
                {**ln, "trans_message": text},
                source_lang=rules.source_lang,
                target_lang=rules.target_lang,
                token_exceptions=rules.token_exc,
            )
            if hard:
                skipped.append((idx, "tag:" + ",".join(hard)))
                continue
            rows.append({"line_num": idx, "polished_text": text, "_findings": applied})
    rows.sort(key=lambda r: r["line_num"])
    out = out or paths.f("apply_pick.json")
    write_json(out, [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])
    write_json(out.replace(".json", ".meta.json"), rows)
    print(f"pick: {len(rows)} line(s) -> {out}" + (f"; skipped {skipped}" if skipped else ""))
    return len(rows)


# --------------------------------------------------------------- Benchmark ----
def benchmark(paths: Paths, rules: Rules, baseline: str, lo: int, hi: int) -> dict:
    cur_data = cstl_io.ensure_cstl(cstl_io.load_cstl(paths.project))
    old_data = cstl_io.ensure_cstl(cstl_io.load_cstl(baseline))
    cur = {int(ln["line_num"]): ln for ln in cur_data.get("lines", [])}
    old = {int(ln["line_num"]): ln for ln in old_data.get("lines", [])}
    changed, substantive, term_only = [], [], []
    for i in sorted(cur):
        if not (lo <= i <= hi and i in old):
            continue
        c, o = cur[i].get("trans_message") or "", old[i].get("trans_message") or ""
        if c == o:
            continue
        changed.append(i)
        (term_only if rules.normalize(o) == rules.normalize(c) else substantive).append(i)
    res = {"range": [lo, hi], "baseline": baseline, "changed_all": changed, "term_only": term_only,
           "changed": substantive, "count": len(substantive), "count_all": len(changed)}
    write_json(paths.f("benchmark.json"), res)
    print(json.dumps({k: v for k, v in res.items() if k not in ("changed", "changed_all", "term_only")}, ensure_ascii=False))
    return res


def _leaked_examples(paths: Paths, rules: Rules) -> set[str]:
    files = [paths.f(n) for n in rules.leak_files]
    files.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "references", "review_taxonomy.md"))
    out = set()
    for fn in files:
        if not os.path.exists(fn):
            continue
        with open(fn, encoding="utf-8-sig") as f:
            for line in f:
                if not line.startswith("|"):
                    continue
                for cell in line.split("|"):
                    for piece in re.split(r"[／/、；;，,→（）()\s]+", cell):
                        piece = piece.strip("*` ")
                        if len(piece) >= 6:
                            out.add(piece)
    return out


def score(paths: Paths, rules: Rules, groups: list[str]) -> str:
    with open(paths.f("benchmark.json"), encoding="utf-8-sig") as f:
        bm = json.load(f)
    changed = set(bm["changed"])
    leak = _leaked_examples(paths, rules)
    lines = []
    for g in groups:
        raw = read_jsonl(paths.f(f"findings_{g}.jsonl"))
        pp = paths.f(f"findings_{g}.pre.jsonl")
        pre_ = read_jsonl(pp) if os.path.exists(pp) else []
        vp = paths.f(f"verdicts_{g}.jsonl")
        verd = {v["id"]: v for v in read_jsonl(vp)} if os.path.exists(vp) else {}
        segs = paths.group_src(g)
        in_range = {i for i in changed if i in segs}
        leaked = {i for i in in_range if any(ex in segs[i]["trans_message"] for ex in leak)}
        clean = in_range - leaked
        found_all = {int(f["line_num"]) for f in raw}
        found_pre = {int(f["line_num"]) for f in pre_}
        acc = lambda f: verd.get(f["id"], {}).get("verdict") in ("accept", "amend")
        found_acc = {int(f["line_num"]) for f in pre_ if acc(f)}
        found_ab = {int(f["line_num"]) for f in pre_ if f["category"] in ("A", "B") and acc(f)}
        acc_rate = (sum(1 for f in pre_ if acc(f)) / len(pre_)) if pre_ and verd else None
        pct = lambda a, b: f"{len(a)}/{len(b)} = {len(a) / max(1, len(b)):.0%}"
        lines.append(
            f"[{g}] human-changed {len(in_range)} ({len(leaked)} leaked) | "
            f"Reviewer {len(raw)} findings/{len(found_all)} | gate {len(found_pre)} | Challenger {len(found_acc)}\n"
            f"     recall(gated): {pct(found_pre & in_range, in_range)} | leak-free: {pct(found_pre & clean, clean)}\n"
            f"     recall(Challenger ok): {pct(found_acc & in_range, in_range)} | A/B ok: {pct(found_ab & in_range, in_range)}\n"
            f"     Challenger accept rate: {acc_rate if acc_rate is None else f'{acc_rate:.0%}'}"
        )
    out = "\n".join(lines)
    print(out)
    with open(paths.f("scores.md"), "a", encoding="utf-8") as f:
        f.write(f"\n## score {datetime.datetime.now():%Y-%m-%d %H:%M}\n```\n{out}\n```\n")
    return out


# --------------------------------------------------------------- Inventory ----
_WORD = re.compile(r"[A-Za-z][A-Za-z’'\-]+")
_TAGS = re.compile(r"</?[ib]>")


def _target_phrases(text: str, tc: str) -> set[str]:
    if tc not in langpair.LATIN_TARGETS:
        out = set()
        for run in re.findall(r"[\u4e00-\u9fff]+", text):
            for n in range(2, 7):
                out.update(run[i:i + n] for i in range(len(run) - n + 1))
        return out
    words = [w.lower() for w in _WORD.findall(normalize_apostrophes(text))]
    out = {w for w in words if len(w) >= 3 and w not in _STOP}
    for n in (2, 3):
        for i in range(len(words) - n + 1):
            ws = words[i:i + n]
            if ws[0] not in _STOP and ws[-1] not in _STOP:
                out.add(" ".join(ws))
    return out


def inventory(paths: Paths, lo: int, hi: int, locked: str | None, min_count: int = 2, max_terms: int = 200) -> dict:
    data = cstl_io.ensure_cstl(cstl_io.load_cstl(paths.project))
    tc = langpair.lang_code(data.get("target_lang") or "Indonesian")
    items = [
        ln for ln in cstl_io.ordered_lines(data)
        if not ln.get("_hidden") and lo <= int(ln["line_num"]) <= hi
        and ln.get("is_translated") and (ln.get("message") or "").strip()
    ]
    segs = {
        int(ln["line_num"]): {
            "name": ln.get("name"),
            "message": ln.get("message") or "",
            "trans_name": ln.get("trans_name"),
            "trans_message": ln.get("trans_message") or "",
        }
        for ln in items
    }
    gl = {}
    if locked and os.path.exists(locked):
        with open(locked, encoding="utf-8-sig") as f:
            gl = json.load(f)
    chars = gl.get("characters", [])
    names = {c.get("canonical", "") for c in chars} | {al for c in chars for al in (c.get("aliases") or [])}
    gl_src = {t["src"] for t in gl.get("terms", []) if t.get("src")} - names

    lower_seen = set()
    for ln in items:
        lower_seen.update(w for w in _WORD.findall(_TAGS.sub("", ln.get("message") or "")) if w[0].islower())

    term_segs: dict[str, set[int]] = collections.defaultdict(set)
    for ln in items:
        s = _TAGS.sub("", ln.get("message") or "")
        i = int(ln["line_num"])
        for t in gl_src:
            if (t in s) if has_cjk(t) else latin_boundary_search(t, s, ignore_case=True):
                term_segs[t].add(i)
        # Japanese kanji/katakana compounds
        for m in JP_TERM.finditer(s):
            term_segs[m.group()].add(i)
        # English capitalized & multiword phrases
        words = [w.lower() for w in _WORD.findall(s)]
        for n in (2, 3):
            for k in range(len(words) - n + 1):
                ws = words[k:k + n]
                if ws[0] in _STOP or ws[-1] in _STOP or all(w in _STOP for w in ws):
                    continue
                term_segs[" ".join(ws)].add(i)
        for w in _WORD.findall(s):
            if w[0].isupper() and w.lower() not in _STOP and w not in gl_src and w not in names and w.lower() not in lower_seen:
                term_segs[w].add(i)

    terms = sorted(((t, sorted(v)) for t, v in term_segs.items() if len(v) >= min_count),
                   key=lambda kv: (-len(kv[1]), kv[0]))[:max_terms]

    all_subs, seg_subs = collections.Counter(), {}
    for i, sg in segs.items():
        ss = _target_phrases(sg["trans_message"], tc)
        seg_subs[i] = ss
        all_subs.update(ss)

    out_terms = []
    for t, idxs in terms:
        cov = collections.Counter()
        for i in idxs:
            cov.update(seg_subs.get(i, ()))
        hints_map = {
            sub: [i for i in idxs if sub in seg_subs[i]]
            for sub, c in cov.most_common(40)
            if c >= max(2, len(idxs) * 0.5) and c / max(1, all_subs[sub]) >= 0.6
        }
        keep: dict[str, list[int]] = {}
        for sub in sorted(hints_map, key=len, reverse=True):
            if not any(sub in k and sub != k for k in keep):
                keep[sub] = hints_map[sub]
        out_terms.append({"src": t, "count": len(idxs), "segments": idxs, "hints": dict(list(keep.items())[:4])})

    # Repeated verbatim lines (callbacks / catchphrases)
    sent_segs: dict[str, list[int]] = collections.defaultdict(list)
    for ln in items:
        plain = _TAGS.sub("", ln.get("message") or "").strip()
        if len(_WORD.findall(plain)) >= 6 or len(re.findall(r"[\u3040-\u9fff]", plain)) >= 6:
            sent_segs[plain].append(int(ln["line_num"]))
    callbacks = [
        {"source": s, "lines": [{"line_num": i, "trans_message": segs[i]["trans_message"]} for i in v]}
        for s, v in sent_segs.items() if len(set(v)) >= 2
    ]

    # Speaker name drift check across the range
    spk_map: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for ln in items:
        if (ln.get("name") or "").strip():
            spk_map[(ln.get("name") or "").strip()][(ln.get("trans_name") or "").strip()] += 1
    speaker_drift = [{"name": k, "renderings": dict(v)} for k, v in spk_map.items() if len(v) > 1]

    inv = {
        "range": [lo, hi],
        "terms": out_terms,
        "callbacks": callbacks,
        "speaker_drift": speaker_drift,
        "lines": {str(k): v for k, v in segs.items()},
    }
    op = paths.f("inventory.json")
    write_json(op, inv)
    print(json.dumps({"range": [lo, hi], "lines": len(segs), "terms": len(out_terms),
                      "callbacks": len(callbacks), "speaker_drift": len(speaker_drift), "out": op}, ensure_ascii=False))
    return inv


# ----------------------------------------------------------- Log & External ----
def log(
    paths: Paths,
    stage: str,
    group: str | None,
    model: str | None,
    agent: str | None,
    file: str | None,
    note: str | None = None,
    tokens: int | None = None,
    segments: int | None = None,
) -> dict:
    row = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "stage": stage,
        "group": group,
        "model": model,
        "agent": agent,
        "file": file,
    }
    if tokens:
        row["tokens"] = tokens
    if segments:
        row["segments"] = segments
    if file and os.path.exists(file):
        if file.lower().endswith(".jsonl"):
            rows = read_jsonl(file)
        else:
            with open(file, encoding="utf-8-sig") as f:
                rows = json.load(f)
        row["count"] = len(rows)
        if stage in ("apply", "revert"):
            row["finding_ids"] = [i for r in rows for i in r.get("_findings", [])]
    if note:
        row["note"] = note
    os.makedirs(paths.dir, exist_ok=True)
    append_jsonl(paths.f("review_log.jsonl"), [row])
    print(json.dumps(row, ensure_ascii=False))
    return row


def ledger(paths: Paths) -> str:
    p = paths.f("review_log.jsonl")
    rows = read_jsonl(p) if os.path.exists(p) else []
    agg = collections.defaultdict(lambda: {"agents": 0, "tokens": 0, "lines": 0})
    for r in rows:
        if r.get("tokens"):
            a = agg[(r["stage"], r.get("model") or "")]
            a["agents"] += 1
            a["tokens"] += int(r["tokens"])
            a["lines"] += int(r.get("segments") or r.get("lines") or 0)
    L = ["| stage | model | agents | tokens | lines | tokens/line |", "|---|---|---|---|---|---|"]
    for (st, m), a in sorted(agg.items()):
        per = f"{a['tokens'] / a['lines']:.0f}" if a["lines"] else ""
        L.append(f"| {st} | {m} | {a['agents']} | {a['tokens']:,} | {a['lines']} | {per} |")
    tot = sum(a["tokens"] for a in agg.values())
    L.append(f"| **total** | | {sum(a['agents'] for a in agg.values())} | {tot:,} | | |")
    txt = "\n".join(L) + "\n"
    print(txt)
    return txt


def import_findings(paths: Paths, src: str, group: str, source: str = "external") -> int:
    if src.lower().endswith(".jsonl"):
        rows = read_jsonl(src)
    else:
        with open(src, encoding="utf-8-sig") as f:
            rows = json.load(f)
    out, skipped = [], 0
    for n, r in enumerate(rows, 1):
        try:
            ti = _line_num(r)
        except Exception:
            skipped += 1
            continue
        off = r.get("offending") or r.get("current")
        prop = r.get("proposed") or r.get("fix") or r.get("replacement")
        if not off or not prop:
            skipped += 1
            continue
        sev = int(r.get("severity") or r.get("sev") or 1)
        cat = r.get("category") if r.get("category") in ("A", "B", "C", "D") else ("A" if sev >= 2 else "C")
        out.append({
            "id": f"{group}-{n:03d}",
            "line_num": int(ti),
            "category": cat,
            "severity": sev,
            "offending": off,
            "proposed": prop,
            "reason": r.get("reason") or r.get("issue") or "",
            "source_evidence": r.get("source_evidence") or "",
            "source": source,
        })
    os.makedirs(paths.dir, exist_ok=True)
    write_jsonl(paths.f(f"findings_{group}.jsonl"), out)
    print(f"imported {len(out)}/{len(rows)} finding(s) from {source} -> findings_{group}.jsonl"
          + (f"; {skipped} skipped" if skipped else ""))
    return len(out)


def dual_merge(project: str, files: list[str], out: str) -> dict:
    data = cstl_io.ensure_cstl(cstl_io.load_cstl(project))
    cur = {int(ln["line_num"]): ln for ln in data.get("lines", [])}
    per: dict[int, list] = collections.defaultdict(list)
    for p in files:
        by = os.path.basename(p).split("_")[0]
        for r in read_jsonl(p):
            ti = _line_num(r)
            per[ti].append({"by": r.get("by", by), **{k: r[k] for k in ("cat", "sev", "issue", "fix") if k in r}})
    rows = []
    for ti, iss in per.items():
        ln = cur.get(ti)
        if ln is None:
            continue
        rows.append({
            "line_num": ti,
            "name": ln.get("name"),
            "message": ln.get("message") or "",
            "trans_name": ln.get("trans_name"),
            "current": ln.get("trans_message") or "",
            "agree": len({x["by"] for x in iss}),
            "maxsev": max(int(x.get("sev") or 1) for x in iss),
            "issues": iss,
        })
    rows.sort(key=lambda r: (-r["agree"], -r["maxsev"], r["line_num"]))
    write_json(out, rows)
    rep = {
        "lines": len(rows),
        "findings": sum(len(r["issues"]) for r in rows),
        "agree>1": sum(r["agree"] > 1 for r in rows),
        "sev>=2": sum(r["maxsev"] >= 2 for r in rows),
    }
    print(json.dumps(rep, ensure_ascii=False) + f" -> {out}")
    return rep


# -------------------------------------------------------------------- CLI ----
def main(argv=None):
    ap = argparse.ArgumentParser(description="Adversarial & dual-model review helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, files=None, groups=None):
        p.add_argument("cstl_path")
        p.add_argument("--dir", help="Review root (default <project_dir>/review)")
        p.add_argument("--run", help="Run subdirectory under review root")
        if files:
            p.add_argument("files", nargs="+", metavar=files)
        if groups:
            p.add_argument("groups", nargs="+", metavar="GROUP")

    b = sub.add_parser("benchmark")
    common(b)
    b.add_argument("--baseline", required=True)
    b.add_argument("--range", required=True, metavar="A-B")

    inv = sub.add_parser("inventory")
    common(inv)
    inv.add_argument("--range", required=True, metavar="A-B")
    inv.add_argument("--locked")
    inv.add_argument("--min-count", type=int, default=2)
    inv.add_argument("--max-terms", type=int, default=200)

    ck = sub.add_parser("check")
    common(ck, groups=True)
    ck.add_argument("--file")

    common(sub.add_parser("pre"), files="FINDINGS_JSONL")

    sg = sub.add_parser("segs")
    common(sg, files="FINDINGS_PRE_JSONL")
    sg.add_argument("--mode", choices=MODES)
    sg.add_argument("--tier", action="store_true")
    sg.add_argument("--min-sev", type=int, default=3)
    sg.add_argument("--sample", type=float, default=0.05)

    rs = sub.add_parser("rules")
    common(rs, groups=True)
    rs.add_argument("--locked")
    rs.add_argument("--examples", nargs="+")

    common(sub.add_parser("stats"), groups=True)
    common(sub.add_parser("blind"), groups=True)
    common(sub.add_parser("hints"), files="FLAGS_JSONL")
    common(sub.add_parser("final"), groups=True)

    m = sub.add_parser("merge")
    common(m, groups=True)
    m.add_argument("--out")

    pk = sub.add_parser("pick")
    common(pk, groups=True)
    pk.add_argument("--ids", nargs="*", default=[])
    pk.add_argument("--min-sev", type=int)
    pk.add_argument("--exclude", nargs="*", default=[])
    pk.add_argument("--out")

    im = sub.add_parser("import")
    common(im)
    im.add_argument("file")
    im.add_argument("--group", required=True)
    im.add_argument("--source", default="external")

    dm = sub.add_parser("dual-merge")
    dm.add_argument("cstl_path")
    dm.add_argument("files", nargs="+")
    dm.add_argument("--out", required=True)

    common(sub.add_parser("ledger"))
    common(sub.add_parser("score"), groups=True)

    lg = sub.add_parser("log")
    common(lg)
    lg.add_argument("--stage", required=True)
    lg.add_argument("--group")
    lg.add_argument("--model")
    lg.add_argument("--agent")
    lg.add_argument("--file")
    lg.add_argument("--note")
    lg.add_argument("--tokens", type=int)
    lg.add_argument("--segments", type=int)

    a = ap.parse_args(argv)
    if a.cmd == "dual-merge":
        dual_merge(a.cstl_path, a.files, a.out)
        return 0
    paths = Paths(a.cstl_path, a.dir, a.run)
    if a.cmd == "log":
        log(paths, a.stage, a.group, a.model, a.agent, a.file, a.note, a.tokens, a.segments)
        return 0
    if a.cmd == "ledger":
        ledger(paths)
        return 0
    if a.cmd == "import":
        import_findings(paths, a.file, a.group, a.source)
        return 0

    rules = load_rules(paths, getattr(a, "locked", None))
    if a.cmd == "check":
        if a.file and len(a.groups) != 1:
            ap.error("--file takes exactly one GROUP")
        return 1 if sum(len(check_file(paths, rules, g, a.file)) for g in a.groups) else 0

    if a.cmd in ("benchmark", "inventory"):
        try:
            lo, hi = (int(x) for x in a.range.split("-", 1))
        except ValueError:
            ap.error(f"bad --range {a.range!r}")

    os.makedirs(paths.dir, exist_ok=True)
    if a.cmd == "benchmark":
        benchmark(paths, rules, a.baseline, lo, hi)
    elif a.cmd == "inventory":
        locked = a.locked or os.path.join(os.path.dirname(os.path.abspath(a.cstl_path)), "glossary.locked.json")
        inventory(paths, lo, hi, locked, a.min_count, a.max_terms)
    elif a.cmd == "pre":
        pre(paths, rules, a.files)
    elif a.cmd == "segs":
        if a.mode and a.tier and a.mode != "tier":
            ap.error("--tier conflicts with --mode " + a.mode)
        segs_for(paths, a.files, a.tier, a.min_sev, a.sample, a.mode)
    elif a.cmd == "rules":
        locked = a.locked or os.path.join(os.path.dirname(os.path.abspath(a.cstl_path)), "glossary.locked.json")
        rules_slice(paths, a.groups, locked, a.examples or [paths.shared("EXAMPLES.md")])
    elif a.cmd == "stats":
        stats(paths, a.groups)
    elif a.cmd == "blind":
        blind(paths, a.groups)
    elif a.cmd == "hints":
        hints(paths, a.files)
    elif a.cmd == "final":
        final(paths, rules, a.groups)
    elif a.cmd == "merge":
        merge(paths, a.groups, a.out)
    elif a.cmd == "pick":
        if not a.ids and a.min_sev is None:
            ap.error("pick needs --ids and/or --min-sev")
        pick(paths, rules, a.ids, a.groups, a.out, a.min_sev, a.exclude)
    elif a.cmd == "score":
        score(paths, rules, a.groups)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
