"""Exercise resumed context and guarded writes on isolated VN project fixtures."""
from __future__ import annotations

import base64
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cstl_translate import batch, cstl_io, integrity, polish, prompt, verify


class LocalizationQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="copas_quality_")
        self.root = Path(self.temp.name)
        self.project = self.root / "project.copas"
        self.data = cstl_io.build_minimal_cstl("Quality fixture")
        self.data.update({"prompt_header": "Keep -san; use the project's character voices.",
                          "ai_check_prompt": "Fix meaning errors only.",
                          "file_order": ["scene.json"], "future_setting": {"keep": True},
                          "lines": [
            {"line_num": 1, "file": "scene.json", "name": "麦", "message": "<i>待って</i>、{hero}。\\n%s  ",
             "trans_message": None, "is_translated": False, "custom_index": {"scene": 2, "text": 8}},
            {"line_num": 2, "file": "scene.json", "name": None, "message": "風。",
             "trans_message": "Angin.", "trans_name": None, "is_translated": True},
            {"line_num": 3, "file": "scene.json", "name": "麦", "message": "こんにちは。",
             "trans_message": "Halo.", "trans_name": "Mugi", "is_translated": True},
        ]})
        cstl_io.save_cstl(str(self.project), self.data)

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, module, *args, success=True):
        env = dict(os.environ, PYTHONPATH=str(SCRIPTS), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-B", "-m", "cstl_translate." + module, *map(str, args)],
                                env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def valid_translation(self):
        return [{"line_num": 1, "trans_name": "Mugi", "trans_message": "<i>Tunggu</i>, {hero}.<br>%s  "}]

    def test_checked_batch_rejects_corrupt_tokens_empty_text_and_non_strings_atomically(self):
        packet = batch.read_context_batch(str(self.project))
        pristine = self.project.read_bytes()
        for text in ("<i>Tunggu</i>, {hero}.\\n  ", "<i>Tunggu</i>, {other}.\\n%s  ",
                     "<i>Tunggu<i>, {hero}.\\n%s  ", "<i>Tunggu</i>, {hero}.%s  ",
                     "<i>Tunggu</i>, {hero}.\\n%s", "", {"text": "Tunggu"}):
            with self.subTest(text=text), self.assertRaises(ValueError):
                batch.write_back(str(self.project), [{"line_num": 1, "trans_name": "Mugi", "trans_message": text}], packet)
            self.assertEqual(self.project.read_bytes(), pristine)
        self.assertEqual(list(self.root.glob("*.bak.*")), [])

    def test_structural_check_accepts_newline_normalization_and_natural_placeholder_order(self):
        self.assertEqual(integrity.message_issues("{who}は{where}にいる。", "Di {where} ada {who}."), [])
        self.assertEqual(integrity.message_issues("100%元気。", "100% sehat."), [])
        self.assertEqual(integrity.message_issues("一\r\n二", "Satu<br>Dua"), [])
        batch.write_back(str(self.project), self.valid_translation(), batch.read_context_batch(str(self.project)))
        saved = cstl_io.load_cstl(str(self.project))
        self.assertEqual(saved["lines"][0]["trans_message"], "<i>Tunggu</i>, {hero}.\\n%s  ")
        self.assertEqual(saved["lines"][0]["custom_index"], {"scene": 2, "text": 8})
        self.assertEqual(saved["future_setting"], {"keep": True})

    def test_checked_batch_rejects_stale_translation_even_with_unchanged_source(self):
        packet = batch.read_context_batch(str(self.project))
        batch.write_back(str(self.project), self.valid_translation(), packet)
        pristine = self.project.read_bytes()
        with self.assertRaises(ValueError):
            batch.write_back(str(self.project), self.valid_translation(), packet)
        self.assertEqual(self.project.read_bytes(), pristine)

    def test_guarded_polish_allows_subset_and_preserves_speakers_flags_and_metadata(self):
        packet = batch.read_context_batch(str(self.project), task="ai-check")
        self.assertEqual(polish.apply_polish(str(self.project), [{"line_num": 3, "polished_text": "Hai.", "reason": "greeting"}], packet), 1)
        saved = cstl_io.load_cstl(str(self.project))
        self.assertEqual(saved["lines"][1]["trans_message"], "Angin.")
        self.assertEqual(saved["lines"][2]["trans_name"], "Mugi")
        self.assertTrue(saved["lines"][2]["is_translated"])
        self.assertEqual(saved["lines"][0]["custom_index"], {"scene": 2, "text": 8})

    def test_guarded_polish_rejects_duplicate_foreign_ids_and_speaker_changes(self):
        packet = batch.read_context_batch(str(self.project), task="ai-check")
        pristine = self.project.read_bytes()
        cases = [
            [{"line_num": 1, "polished_text": "Tunggu."}],
            [{"line_num": 2, "polished_text": "Bayu."}, {"line_num": 2, "polished_text": "Angin."}],
            [{"line_num": 2, "polished_text": "Angin.", "polished_name": "Mugi"}],
            [{"line_num": 3, "polished_text": "Hai.", "polished_name": None}],
            [{"line_num": 3, "polished_text": {"text": "Hai"}}],
            [{"line_num": True, "polished_text": "Hai."}],
        ]
        for updates in cases:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                polish.apply_polish(str(self.project), updates, packet)
            self.assertEqual(self.project.read_bytes(), pristine)
        self.assertEqual(list(self.root.glob("*.bak.*")), [])

    def test_guarded_polish_rejects_stale_source_translation_and_speaker(self):
        for key, value in (("message", "different"), ("trans_message", "Selamat siang."), ("trans_name", "Mugi-san")):
            with self.subTest(key=key):
                cstl_io.save_cstl(str(self.project), copy.deepcopy(self.data))
                packet = batch.read_context_batch(str(self.project), task="ai-check")
                current = cstl_io.load_cstl(str(self.project))
                current["lines"][2][key] = value
                cstl_io.save_cstl(str(self.project), current)
                pristine = self.project.read_bytes()
                with self.assertRaises(ValueError):
                    polish.apply_polish(str(self.project), [{"line_num": 3, "polished_text": "Hai."}], packet)
                self.assertEqual(self.project.read_bytes(), pristine)

    def test_polish_checks_source_tokens_and_can_repair_an_already_broken_translation(self):
        self.data["lines"][2].update(message="<b>こんにちは</b>{0}。", trans_message="Halo.")
        cstl_io.save_cstl(str(self.project), self.data)
        packet = batch.read_context_batch(str(self.project), task="ai-check")
        with self.assertRaises(ValueError):
            polish.apply_polish(str(self.project), [{"line_num": 3, "polished_text": "Hai."}], packet)
        polish.apply_polish(str(self.project), [{"line_num": 3, "polished_text": "<b>Hai</b>{0}."}], packet)
        self.assertEqual(cstl_io.load_cstl(str(self.project))["lines"][2]["trans_message"], "<b>Hai</b>{0}.")

    def test_empty_review_is_a_read_only_noop(self):
        pristine = self.project.read_bytes()
        self.assertEqual(polish.apply_polish(str(self.project), [], batch.read_context_batch(str(self.project), task="ai-check")), 0)
        self.assertEqual(self.project.read_bytes(), pristine)
        self.assertEqual(list(self.root.glob("*.bak.*")), [])

    def test_review_cli_accepts_utf8_bom_and_rejects_bad_correction_without_mutating(self):
        packet_path = self.root / "review.json"
        packet_path.write_text(self.run_cli("batch", "read-translated", self.project).stdout, encoding="utf-8-sig")
        correction = self.root / "correction.json"
        correction.write_text(json.dumps([{"line_num": 3, "polished_text": "Hai."}]), encoding="utf-8-sig")
        self.run_cli("polish", "write", self.project, correction, "--expect-batch", packet_path)
        pristine = self.project.read_bytes()
        self.run_cli("polish", "write", self.project, correction, "--expect-batch", packet_path, success=False)
        self.assertEqual(self.project.read_bytes(), pristine)

    def test_project_brief_is_reloaded_for_each_task_without_changing_saved_prompts(self):
        brief = Path(str(self.project) + ".brief.md")
        pristine = self.project.read_bytes()
        for text in ("Mugi kepada guru: saya/Pak. Bukti scene.json #3.", "Mugi kepada teman: aku/kamu. Bukti scene.json #3."):
            brief.write_text(text, encoding="utf-8-sig")
            for task in ("translate", "agent", "glossary", "ai-check"):
                packet = batch.read_context_batch(str(self.project), task=task)
                self.assertEqual(packet["project_brief"], text)
                self.assertEqual(Path(packet["project_brief_source"]), brief)
                self.assertEqual(packet["prompts"]["prompt_header"], self.data["prompt_header"])
        self.assertEqual(self.project.read_bytes(), pristine)

    def test_brief_cli_override_missing_file_and_legacy_route(self):
        other = self.root / "voice.md"
        other.write_text("Only a confirmed relationship.", encoding="utf-8")
        packet = json.loads(self.run_cli("batch", "read", self.project, "--brief", other).stdout)
        self.assertEqual(packet["project_brief"], other.read_text(encoding="utf-8"))
        self.run_cli("batch", "read", self.project, "--brief", self.root / "missing.md", success=False)
        self.run_cli("batch", "read", self.project, "--brief", other, "--lines-only", success=False)
        legacy = json.loads(self.run_cli("batch", "read", self.project, "--lines-only").stdout)
        self.assertIsInstance(legacy, list)
        self.assertEqual([line["line_num"] for line in legacy], [1])

    def test_zip_review_and_brief_preserve_binary_source_and_engine_index(self):
        self.project = self.root / "project.copas.zip"
        raw = b"\x00\xff\x80fixture"
        self.data["customRawBuffers"] = {"scenario.bin": base64.b64encode(raw).decode("ascii")}
        cstl_io.save_cstl(str(self.project), self.data)
        Path(str(self.project) + ".brief.md").write_text("Confirmed voices.", encoding="utf-8")
        packet = batch.read_context_batch(str(self.project), task="ai-check")
        polish.apply_polish(str(self.project), [{"line_num": 3, "polished_text": "Hai."}], packet)
        saved = cstl_io.load_cstl(str(self.project))
        self.assertEqual(base64.b64decode(saved["customRawBuffers"]["scenario.bin"]), raw)
        self.assertEqual(saved["lines"][0]["custom_index"], self.data["lines"][0]["custom_index"])
        self.assertEqual(packet["project_brief"], "Confirmed voices.")

    def test_verify_reports_token_losses_in_an_existing_translation(self):
        self.data["lines"][0].update(is_translated=True, trans_message="Tunggu.", trans_name="Mugi")
        cstl_io.save_cstl(str(self.project), self.data)
        kinds = {issue["kind"] for issue in verify.verify(str(self.project), "") if issue["line_num"] == 1}
        self.assertTrue({"structural_tokens", "markup_order", "trailing_space"} <= kinds)

    def test_repeated_backups_do_not_overwrite_the_first_snapshot(self):
        first = cstl_io.backup_cstl(str(self.project))
        self.data["projectName"] = "Updated"
        cstl_io.save_cstl(str(self.project), self.data)
        second = cstl_io.backup_cstl(str(self.project))
        self.assertNotEqual(first, second)
        self.assertEqual(cstl_io.load_cstl(first)["projectName"], "Quality fixture")
        self.assertEqual(cstl_io.load_cstl(second)["projectName"], "Updated")

    def test_jp_id_rules_apply_only_to_new_templates_and_missing_matching_task_prompts(self):
        # Use a distinct marker to test routing rather than assert generated prose.
        with patch.object(prompt, "JP_ID_RULES", "JP_ID_PROFILE"), patch.object(prompt, "JP_ID_REVIEW_RULES", "JP_ID_REVIEW"):
            self.assertIn("JP_ID_PROFILE", prompt.build_prompt("batch", "Japanese", "Indonesian"))
            self.assertNotIn("JP_ID_PROFILE", prompt.build_prompt("batch", "English", "Indonesian"))
            self.assertNotIn("JP_ID_PROFILE", prompt.project_prompt_info(self.data)["instruction"])
            data = copy.deepcopy(self.data)
            data["prompt_header"] = ""
            data["ai_check_prompt"] = ""
            self.assertIn("JP_ID_PROFILE", prompt.project_prompt_info(data)["instruction"])
            self.assertIn("JP_ID_REVIEW", prompt.project_prompt_info(data, "ai-check")["instruction"])
            self.assertNotIn("JP_ID_PROFILE", prompt.project_prompt_info(data, "glossary")["instruction"])
            data["source_lang"] = "English"
            self.assertNotIn("JP_ID_PROFILE", prompt.project_prompt_info(data)["instruction"])


if __name__ == "__main__":
    unittest.main()
