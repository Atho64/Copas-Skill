"""Comprehensive end-to-end tests for the cstl_translate pipeline (ja-id, en-id, ja-en)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cstl_translate import (
    audit,
    batch,
    cache,
    cstl_io,
    glossary,
    helpers,
    langpair,
    polish,
    precedents,
    progress,
    prompt,
    review,
    scan,
    state,
    verify,
)


class PipelineSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cstl_sys_")
        self.root = Path(self.temp.name)
        self.project = self.root / "project.copas"
        self.env = dict(
            os.environ,
            PYTHONPATH=str(SCRIPTS),
            PYTHONIOENCODING="utf-8",
            PYTHONDONTWRITEBYTECODE="1",
        )

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, module: str, *args, check: bool = True):
        res = subprocess.run(
            [sys.executable, "-B", "-m", f"cstl_translate.{module}", *map(str, args)],
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if check:
            self.assertEqual(res.returncode, 0, res.stderr + "\n" + res.stdout)
        return res

    def _save_sample_project(self, source_lang="Japanese", target_lang="Indonesian", lines=None):
        data = cstl_io.build_minimal_cstl("SampleVN", source_lang=source_lang, target_lang=target_lang)
        data["file_order"] = ["ch1.json", "ch2.json"]
        data["lines"] = lines or [
            {"line_num": 1, "file": "ch1.json", "name": "麦", "message": "おはよう、スピカ。{0}",
             "trans_name": "Mugi", "trans_message": "Pagi, Spica.{0}", "is_translated": True},
            {"line_num": 2, "file": "ch1.json", "name": None, "message": "旧校舎へ行く。",
             "trans_name": None, "trans_message": "Pergi ke gedung sekolah lama.", "is_translated": True},
            {"line_num": 3, "file": "ch2.json", "name": "麦", "message": "待ってくれ、スピカ！",
             "trans_name": None, "trans_message": None, "is_translated": False},
            {"line_num": 4, "file": "ch2.json", "name": "スピカ", "message": "はい、行きます。",
             "trans_name": None, "trans_message": None, "is_translated": False},
        ]
        cstl_io.save_cstl(str(self.project), data)
        return data

    def test_langpair_and_prompt_profiles(self):
        self.assertEqual(langpair.pair_key("jp", "Bahasa Indonesia"), "ja-id")
        self.assertEqual(langpair.pair_key("English", "Indonesian"), "en-id")
        self.assertEqual(langpair.pair_key("日本語", "en"), "ja-en")
        self.assertEqual(langpair.guide_ref("jp", "id"), "references/language_pairs.md#ja-id")

        self.assertIn("kana_residue", langpair.soft_checks("おはよう", "Pagi おは", "Japanese", "Indonesian"))
        self.assertIn("kanji_residue", langpair.soft_checks("旧校舎", "Gedung 旧", "Japanese", "Indonesian"))
        self.assertIn("jp_punct", langpair.soft_checks("おはよう。", "Pagi。", "Japanese", "Indonesian"))
        self.assertIn("register_mix", langpair.soft_checks("なんだ", "Saya tidak tahu lo mau apa.", "Japanese", "Indonesian"))
        self.assertIn("english_residue", langpair.soft_checks("You are here with that.", "You are here with that.", "English", "Indonesian"))

        p_en_id = prompt.build_prompt("batch", "English", "Indonesian")
        self.assertIn("English to Indonesian localization", p_en_id)
        p_jp_en = prompt.build_prompt("batch", "Japanese", "English")
        self.assertIn("Japanese to English localization", p_jp_en)

        data = cstl_io.build_minimal_cstl("P", source_lang="English", target_lang="Indonesian")
        data["prompt_header"] = ""
        data["ai_check_prompt"] = ""
        info_t = prompt.project_prompt_info(data, "translate")
        info_r = prompt.project_prompt_info(data, "ai-check")
        self.assertEqual(info_t["language_pair"], "en-id")
        self.assertIn("English to Indonesian localization", info_t["instruction"])
        self.assertIn("English to Indonesian review", info_r["instruction"])

    def test_helpers_kana_range_boundary_and_backup_retention(self):
        # Verify the fixed [\u3040-\u30ff] range matches arbitrary kana (not just U+3040 and U+30FF)
        for ch in ("あ", "ん", "ア", "ン", "っ", "ヶ"):
            self.assertTrue(helpers.has_kana(ch), ch)
        self.assertFalse(helpers.has_kana("abc 123"))

        self.assertIsNone(helpers.latin_boundary_search("ai", "baik hati", ignore_case=True))
        self.assertIsNotNone(helpers.latin_boundary_search("Mugi", "Dia menatap Mugi-san.", ignore_case=False))
        self.assertIsNone(helpers.latin_boundary_search("Will", "William went home.", ignore_case=False))

        target = self.root / "sample.txt"
        manual = self.root / "sample.txt.pre_review"
        manual.write_text("keep", encoding="utf-8")
        for i in range(5):
            target.write_text(f"v{i}", encoding="utf-8")
            helpers.backup_file(str(target), keep=3)
        baks = list(self.root.glob("sample.txt.bak.*"))
        self.assertEqual(len(baks), 3)
        self.assertTrue(manual.exists())

    def test_state_and_provenance(self):
        self._save_sample_project()
        self.run_cli("state", "settle", self.project, "--src", "旧校舎", "--dst", "gedung sekolah lama")
        self.run_cli("state", "errata", self.project, 2, "--note", "Intentional fragment")
        self.run_cli("state", "tag-exception", self.project, 1, "--reason", "Extra italic tag")
        self.run_cli("state", "lint-rule", self.project, "no_anda", "--re", r"\bAnda\b", "--msg", "Use aku/kamu")

        card = self.run_cli("state", "card", self.project, "--range", "1-2").stdout
        self.assertIn("gedung sekolah lama", card)
        self.assertIn("Intentional fragment", card)
        self.assertIn("Extra italic tag", card)
        self.assertIn("no_anda", card)

        # Apply fix with provenance -> check removed_snippets recorded for Indonesian text
        fixes = self.root / "fixes.jsonl"
        fixes.write_text(
            json.dumps({"line_num": 2, "patches": [["lama", "kuno"]], "reason": "Confirmed antique"}) + "\n",
            encoding="utf-8",
        )
        self.run_cli("batch", "apply", self.project, fixes, "--source", "dual")
        prot = state.protected_removals(str(self.project))
        self.assertIn(2, prot)
        self.assertTrue(any("lama" in s for s in prot[2]))

    def test_audit_and_cache_commands(self):
        self._save_sample_project(lines=[
            {"line_num": 1, "file": "ch1.json", "name": "麦", "message": "旧校舎。{0}",
             "trans_name": "Mugi", "trans_message": "Gedung lama.{0}", "is_translated": True},
            {"line_num": 2, "file": "ch1.json", "name": None, "message": "はい。",
             "trans_name": None, "trans_message": "Ya.", "is_translated": True},
            {"line_num": 3, "file": "ch1.json", "name": None, "message": "はい。",
             "trans_name": None, "trans_message": None, "is_translated": False},
            {"line_num": 4, "file": "ch2.json", "name": None, "message": "おはよう。",
             "trans_name": None, "trans_message": "Pagi おは", "is_translated": True},
        ])
        # fill-dupes copies line 2 -> line 3
        self.run_cli("cache", "fill-dupes", self.project, "--apply")
        saved = cstl_io.load_cstl(str(self.project))
        self.assertEqual(saved["lines"][2]["trans_message"], "Ya.")
        self.assertTrue(saved["lines"][2]["is_translated"])

        # set-hidden hides line 4
        self.run_cli("cache", "set-hidden", self.project, "--range", "4-4", "--apply")
        self.assertEqual(cache.stats(cstl_io.load_cstl(str(self.project)))["hidden"], 1)

        # unhide line 4 and audit -> soft kana warning exits 0
        self.run_cli("cache", "set-hidden", self.project, "--range", "4-4", "--unhide", "--apply")
        res = self.run_cli("audit", self.project, "--out", self.root / "audit.json")
        rep = json.loads((self.root / "audit.json").read_text(encoding="utf-8"))
        self.assertIn("kana_residue", rep)
        self.assertEqual(res.returncode, 0)

        # dump & show
        self.run_cli("cache", "dump", self.project, "--range", "1-3", "--out", self.root / "dump.json")
        dumped = json.loads((self.root / "dump.json").read_text(encoding="utf-8"))
        self.assertEqual(len(dumped), 3)

    def test_glossary_filter_lint_and_merge_newterms(self):
        self._save_sample_project()
        locked_path = self.root / "glossary.locked.json"
        locked_data = {
            "characters": [
                {"canonical": "速川麦", "render": "Hayakawa Mugi", "aliases": ["麦", "Mugi-san", "Captain Mugi"], "type": "character"},
                {"canonical": "速川花", "render": "Hayakawa Hana", "aliases": ["花"], "type": "character"},
                {"canonical": "スピカ", "render": "Spica", "aliases": [], "type": "character"},
            ],
            "terms": [
                {"src": "旧校舎", "dst": "gedung sekolah lama", "category": "place"},
                {"src": "Coastguard", "dst": "Penjaga Pantai", "category": "org"},
                {"src": "MissingDst", "dst": ""},
            ],
        }
        locked_path.write_text(json.dumps(locked_data, ensure_ascii=False), encoding="utf-8")

        lint_issues = glossary.lint_locked(locked_data)
        kinds = {i["kind"] for i in lint_issues}
        self.assertTrue({"alias_has_title", "shared_surname", "term_missing_dst"} <= kinds)

        sub = glossary.filter_locked(locked_data, ["旧校舎へ行く。"], ["速川麦"])
        self.assertEqual([c["canonical"] for c in sub["characters"]], ["速川麦"])
        self.assertEqual([t["src"] for t in sub["terms"]], ["旧校舎"])

        # merge-newterms with conflict detection
        nt1 = self.root / "newterms_1.txt"
        nt2 = self.root / "newterms_2.txt"
        nt1.write_text("[place] 保健室 = ruang UKS {school infirmary}\n生徒会\tOSIS\nConflicted => VersiA\n", encoding="utf-8")
        nt2.write_text("生徒会\tOSIS\nConflicted => VersiB\n", encoding="utf-8")

        out = self.run_cli("glossary", "merge-newterms", "--locked", locked_path, nt1, nt2, "--apply", "--inject", self.project).stdout
        self.assertIn("CONFLICT conflicted", out)
        updated = json.loads(locked_path.read_text(encoding="utf-8"))
        term_srcs = {t["src"] for t in updated["terms"]}
        self.assertIn("保健室", term_srcs)
        self.assertIn("生徒会", term_srcs)
        self.assertNotIn("Conflicted", term_srcs)
        self.assertIn("保健室", cstl_io.load_cstl(str(self.project))["glossary_text"])

    def test_parallel_split_bundle_validate_write_and_progress(self):
        self._save_sample_project()
        locked_path = self.root / "glossary.locked.json"
        locked_path.write_text(json.dumps({
            "characters": [
                {"canonical": "麦", "render": "Mugi", "aliases": []},
                {"canonical": "スピカ", "render": "Spica", "aliases": []},
            ],
            "terms": [{"src": "旧校舎", "dst": "gedung sekolah lama", "category": "place"}],
        }, ensure_ascii=False), encoding="utf-8")
        self.run_cli("state", "settle", self.project, "--dst", "gedung sekolah lama")

        par = self.root / "par"
        self.run_cli("batch", "split", self.project, "--target", 10, "--out-dir", par, "--context", 2)
        src_file = par / "grp_1_src.json"
        self.assertTrue(src_file.exists())
        self.assertTrue((par / "grp_1_ctx.json").exists())

        self.run_cli("batch", "bundle", self.project, src_file, "--locked", locked_path)
        bundle_txt = (par / "bundle_1.md").read_text(encoding="utf-8")
        self.assertIn("Filtered Group Glossary", bundle_txt)
        self.assertIn("Mugi", bundle_txt)
        self.assertIn("Context Before", bundle_txt)
        self.assertIn("gedung sekolah lama", bundle_txt)

        # Progress before write: pending -> running -> ready -> written
        self.assertEqual(progress.snapshot(str(self.project), str(par))["groups"][0]["state"], "pending")

        trans_file = par / "trans_1.jsonl"
        trans_file.write_text(
            json.dumps({"line_num": 3, "trans_name": "Mugi", "trans_message": "Tunggu, Spica!"}) + "\n"
            + json.dumps({"line_num": 4, "trans_name": "Spica", "trans_message": "Baik, aku ikut."}) + "\n",
            encoding="utf-8",
        )
        self.run_cli("batch", "validate", src_file, trans_file, "--project", self.project)
        self.assertEqual(progress.snapshot(str(self.project), str(par))["groups"][0]["state"], "ready")

        self.run_cli("batch", "write", self.project, trans_file)
        snap = progress.snapshot(str(self.project), str(par))
        self.assertEqual(snap["groups"][0]["state"], "written")
        self.assertEqual(snap["total"]["done_pct"], 100.0)
        self.assertIn("100%", progress.one_line(snap))

    def test_verify_scan_pending_and_precedents(self):
        self._save_sample_project(lines=[
            {"line_num": 1, "file": "ch1.json", "name": "麦", "message": "旧校舎へ行く。",
             "trans_name": "Mugi", "trans_message": "Pergi ke gedung sekolah lama.", "is_translated": True},
            {"line_num": 2, "file": "ch1.json", "name": "麦", "message": "図書館へ。",
             "trans_name": "Gandum", "trans_message": "Ke perpustakaan.", "is_translated": True},
            {"line_num": 3, "file": "ch2.json", "name": "スピカ", "message": "生徒会と旧校舎。",
             "trans_name": None, "trans_message": None, "is_translated": False},
            {"line_num": 4, "file": "ch2.json", "name": "スピカ", "message": "生徒会へ行こう。",
             "trans_name": None, "trans_message": None, "is_translated": False},
            {"line_num": 5, "file": "ch2.json", "name": "スピカ", "message": "生徒会はどこ？",
             "trans_name": None, "trans_message": None, "is_translated": False},
        ])
        locked_path = self.root / "glossary.locked.json"
        locked_path.write_text(json.dumps({
            "characters": [{"canonical": "麦", "render": "Mugi", "aliases": []}],
            "terms": [{"src": "旧校舎", "dst": "gedung sekolah lama"}],
        }, ensure_ascii=False), encoding="utf-8")

        issues = verify.verify(str(self.project), str(locked_path))
        self.assertTrue(any(i["kind"] == "speaker_not_preserved" and i["line_num"] == 2 for i in issues))

        # Baseline hides reviewed issue
        base = self.root / "baseline.json"
        self.run_cli("verify", self.project, locked_path, "--write-baseline", base)
        out = self.run_cli("verify", self.project, locked_path, "--baseline", base, "--json").stdout
        self.assertEqual(json.loads(out), [])

        # scan --mode pending discovers recurring unglossed term 生徒会 and speaker スピカ
        pending_res = scan.scan(str(self.project), str(locked_path), mode="pending")
        pend_toks = {r["token"] for r in pending_res["pending"]}
        self.assertTrue({"生徒会", "スピカ"} <= pend_toks)

        # precedents builds BOOK_BIBLE from translated lines
        md = precedents.build(
            cstl_io.load_cstl(str(self.project))["lines"],
            [{"line_num": 3, "name": "スピカ", "message": "生徒会と旧校舎。"}],
            json.loads(locked_path.read_text(encoding="utf-8")),
        )
        self.assertIn("スピカ", md)
        self.assertIn("gedung sekolah lama", md)

    def test_adversarial_review_pipeline_for_indonesian_and_dual_merge(self):
        self._save_sample_project(lines=[
            {"line_num": 1, "file": "ch1.json", "name": "麦", "message": "知らん顔するな、スピカ。",
             "trans_name": "Mugi", "trans_message": "Jangan tidak tahu ya, Spica.", "is_translated": True},
            {"line_num": 2, "file": "ch1.json", "name": None, "message": "旧校舎へ歩いた。",
             "trans_name": None, "trans_message": "Dia telah berjalan menuju ke gedung sekolah lama.", "is_translated": True},
            {"line_num": 3, "file": "ch1.json", "name": None, "message": "旧校舎へ歩いた。",
             "trans_name": None, "trans_message": "Berjalan ke gedung sekolah lama.", "is_translated": True},
        ])
        locked_path = self.root / "glossary.locked.json"
        locked_path.write_text(json.dumps({
            "characters": [{"canonical": "スピカ", "render": "Spica", "aliases": []}],
            "terms": [{"src": "旧校舎", "dst": "gedung sekolah lama"}],
        }, ensure_ascii=False), encoding="utf-8")

        rev = self.root / "review"
        rev.mkdir()
        (rev / "config.json").write_text(json.dumps({
            "redline": ["Spica"],
            "settled": ["gedung sekolah lama"],
            "glossary_settled": True,
        }), encoding="utf-8")

        # 1. split + rules + blind
        self.run_cli("batch", "split", self.project, "--stage", "review", "--range", "1-3", "--target", 10, "--prefix", "g", "--out-dir", rev / "groups")
        self.run_cli("review", "rules", self.project, "g1", "--locked", locked_path)
        self.run_cli("review", "blind", self.project, "g1")
        blind_data = json.loads((rev / "groups" / "blind_g1.json").read_text(encoding="utf-8"))
        self.assertNotIn("message", blind_data["lines"][0])

        # 2. flags -> hints
        (rev / "flags_g1.jsonl").write_text(
            json.dumps({"id": "g1-b001", "line_num": 2, "quote": "telah berjalan menuju ke", "why": "telah spam", "severity": 2}) + "\n",
            encoding="utf-8",
        )
        self.run_cli("review", "hints", self.project, rev / "flags_g1.jsonl")
        hints_data = json.loads((rev / "hints_g1.json").read_text(encoding="utf-8"))
        self.assertEqual(hints_data[0]["message"], "旧校舎へ歩いた。")

        # 3. Reviewer findings (good A, good C backed by flag, plus bad finding touching settled term & redline)
        findings = [
            {"id": "g1-001", "line_num": 1, "category": "A", "severity": 3, "offending": "Jangan tidak tahu ya",
             "source_evidence": "知らん顔するな", "proposed": "Jangan pura-pura bodoh", "reason": "feign ignorance"},
            {"id": "g1-002", "line_num": 2, "category": "C", "severity": 2, "offending": "telah berjalan menuju ke",
             "source_evidence": "歩いた", "proposed": "berjalan ke", "reason": "remove telah bloat", "flags": ["g1-b001"]},
            {"id": "g1-003", "line_num": 2, "category": "B", "severity": 2, "offending": "gedung sekolah lama",
             "proposed": "bangunan tua", "reason": "test settled block"},
            {"id": "g1-004", "line_num": 1, "category": "B", "severity": 2, "offending": "Spica",
             "proposed": "Supika", "reason": "test name_touch/redline"},
        ]
        (rev / "findings_g1.jsonl").write_text("\n".join(json.dumps(x) for x in findings) + "\n", encoding="utf-8")

        # check fails before removing invalid items
        self.assertEqual(self.run_cli("review", "check", self.project, "g1", check=False).returncode, 1)

        # pre separates valid (g1-001, g1-002) and rejected (g1-003, g1-004)
        self.run_cli("review", "pre", self.project, rev / "findings_g1.jsonl")
        pre_ok = review.read_jsonl(str(rev / "findings_g1.pre.jsonl"))
        rej = review.read_jsonl(str(rev / "rejected_g1.jsonl"))
        self.assertEqual([x["id"] for x in pre_ok], ["g1-001", "g1-002"])
        self.assertEqual(len(rej), 2)

        # 4. segs --mode slim: g1-001 (A) challenged, g1-002 (flagged C) auto-accepted
        self.run_cli("review", "segs", self.project, "--mode", "slim", rev / "findings_g1.pre.jsonl")
        chal = review.read_jsonl(str(rev / "challenge_g1.jsonl"))
        auto = review.read_jsonl(str(rev / "verdicts_g1.auto.jsonl"))
        self.assertEqual([x["id"] for x in chal], ["g1-001"])
        self.assertEqual([x["id"] for x in auto], ["g1-002"])

        # Challenger accepts g1-001 -> final creates apply_g1.json + review_g1.md
        (rev / "verdicts_g1.jsonl").write_text(json.dumps({"id": "g1-001", "verdict": "accept", "reason": "valid"}) + "\n", encoding="utf-8")
        self.run_cli("review", "final", self.project, "g1")
        apply_rows = json.loads((rev / "apply_g1.json").read_text(encoding="utf-8"))
        self.assertEqual(len(apply_rows), 1)
        self.assertEqual(apply_rows[0]["line_num"], 1)
        self.assertIn("Jangan pura-pura bodoh", apply_rows[0]["polished_text"])

        # Apply A/B fixes with provenance -> protected against later revert
        self.run_cli("batch", "apply", self.project, rev / "apply_g1.json", "--source", "dual", "--reason", "Meaning fix")
        # Attempt to revert "pura-pura bodoh" back to "tidak tahu ya" fails E_reverts_fix in check()
        rules = review.load_rules(review.Paths(str(self.project)), str(locked_path))
        ok, why, _, _ = review.check(
            {"id": "g1-999", "line_num": 1, "category": "C", "offending": "Jangan pura-pura bodoh, Spica.",
             "proposed": "Jangan tidak tahu ya, Spica."},
            {"line_num": 1, "name": "麦", "message": "知らん顔するな、スピカ。", "trans_name": "Mugi",
             "trans_message": "Jangan pura-pura bodoh, Spica."},
            rules,
        )
        self.assertFalse(ok)
        self.assertEqual(why, "E_reverts_fix")

        # 5. merge + pick for C finding g1-002
        self.run_cli("review", "merge", self.project, "g1")
        self.run_cli("review", "pick", self.project, "g1", "--ids", "g1-002")
        self.run_cli("batch", "apply", self.project, rev / "apply_pick.json", "--source", "user")
        saved = cstl_io.load_cstl(str(self.project))
        self.assertEqual(saved["lines"][1]["trans_message"], "Dia berjalan ke gedung sekolah lama.")

        # 6. inventory + dual-merge + log + ledger
        self.run_cli("review", "inventory", self.project, "--range", "1-3", "--locked", locked_path)
        inv = json.loads((rev / "inventory.json").read_text(encoding="utf-8"))
        self.assertTrue(any(cb["source"] == "旧校舎へ歩いた。" for cb in inv["callbacks"]))

        m1 = self.root / "opus_g1.jsonl"
        m2 = self.root / "fable_g1.jsonl"
        m1.write_text(json.dumps({"line_num": 3, "cat": "style", "sev": 2, "issue": "short", "fix": "Dia berjalan..."}) + "\n", encoding="utf-8")
        m2.write_text(json.dumps({"line_num": 3, "cat": "meaning", "sev": 3, "issue": "subject", "fix": "Dia berjalan..."}) + "\n", encoding="utf-8")
        self.run_cli("review", "dual-merge", self.project, m1, m2, "--out", self.root / "fix_input.json")
        dm = json.loads((self.root / "fix_input.json").read_text(encoding="utf-8"))
        self.assertEqual(dm[0]["agree"], 2)

        self.run_cli("review", "log", self.project, "--stage", "reviewer", "--group", "g1", "--model", "opus", "--tokens", 12000, "--segments", 3)
        led = self.run_cli("review", "ledger", self.project).stdout
        self.assertIn("12,000", led)


if __name__ == "__main__":
    unittest.main()
