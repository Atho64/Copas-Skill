"""Check that saved project prompts reach each agent task without changing the backup."""
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

from cstl_translate import batch, cstl_io, prompt


class ProjectPromptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="copas_prompt_test_")
        self.root = Path(self.temp.name)
        self.project = self.root / "project.copas"
        self.prompts = {
            "prompt_header": 'Translate {{lineCount}} lines from {{sourceLang}} to {{targetLang}}.\r\nKeep -sama and use aku/kau.\nReturn numbered text.  ',
            "glossary_prompt": 'Extract {{lineCount}} lines: names and ships only. Retain the spelling of 麦.',
            "ai_check_prompt": 'Review {{lineCount}} lines. Keep every existing honorific; fix mistaken subjects only.',
            "agent_prompt": 'Use the protagonist POV. Translate {{sourceLang}} to {{targetLang}} with the project glossary.',
            "summary_prompt": 'Summarize only established relationships.',
            "ai_check_summary_prompt": 'Record accepted corrections, never rejected rewrites.',
            "dictionary_prompt": 'Explain this word in {{targetLang}}, with its scene context.',
        }
        self.data = cstl_io.build_minimal_cstl("Prompt fixture", source_lang="Japanese", target_lang="Indonesian")
        self.data.update(self.prompts)
        self.data.update({
            "glossary_text": "[character] 麦 = Mugi {given name}",
            "file_order": ["scene.json"],
            "lines": [
                {"line_num": 1, "file": "scene.json", "name": "麦", "message": "こんにちは。", "is_translated": False},
                {"line_num": 2, "file": "scene.json", "name": None, "message": "風。", "is_translated": True, "trans_message": "Angin."},
                {"line_num": 3, "file": "scene.json", "name": None, "message": "雨。", "is_translated": False},
            ],
        })
        cstl_io.save_cstl(str(self.project), self.data)
        self.env = dict(os.environ, PYTHONPATH=str(SCRIPTS), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, module, *args, success=True):
        result = subprocess.run([sys.executable, "-B", "-m", "cstl_translate." + module, *map(str, args)],
                                env=self.env, capture_output=True, text=True, encoding="utf-8")
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_default_read_includes_saved_instruction_and_actual_batch_count(self):
        pristine = self.project.read_bytes()
        packet = json.loads(self.run_cli("batch", "read", self.project, "--size", 1).stdout)
        self.assertEqual(packet["prompt_source"], "project")
        self.assertEqual(packet["prompt_field"], "prompt_header")
        self.assertEqual(packet["prompts"], self.prompts)
        self.assertIn("Translate 1 lines from Japanese to Indonesian", packet["instruction"])
        self.assertIn("Keep -sama and use aku/kau.", packet["instruction"])
        self.assertIn("line_num, trans_message, and trans_name", packet["instruction"])
        self.assertEqual(packet["prompts"]["prompt_header"], self.prompts["prompt_header"])
        self.assertEqual(self.project.read_bytes(), pristine)

    def test_task_routing_does_not_mix_glossary_and_translation_instructions(self):
        for task, field, ids in (
            ("translate", "prompt_header", [1, 3]),
            ("agent", "agent_prompt", [1, 3]),
            ("glossary", "glossary_prompt", [1, 2, 3]),
            ("ai-check", "ai_check_prompt", [2]),
        ):
            with self.subTest(task=task):
                packet = batch.read_context_batch(str(self.project), task=task)
                self.assertEqual(packet["prompt_field"], field)
                self.assertEqual([line["line_num"] for line in packet["lines"]], ids)
                self.assertTrue(packet["instruction"].startswith(prompt.render_variables(self.prompts[field], self.data, len(ids))))
                if task == "translate":
                    self.assertNotIn("names and ships only", packet["instruction"])
                if task == "glossary":
                    self.assertNotIn("Keep -sama", packet["instruction"])

    def test_review_default_loads_ai_check_prompt_and_current_translation(self):
        packet = json.loads(self.run_cli("batch", "read-translated", self.project).stdout)
        self.assertEqual(packet["task"], "ai-check")
        self.assertEqual(packet["prompt_field"], "ai_check_prompt")
        self.assertIn("Review 1 lines", packet["instruction"])
        self.assertEqual(packet["lines"][0]["trans_message"], "Angin.")
        self.assertIn("polished_text", packet["instruction"])

    def test_explicit_lines_only_keeps_legacy_array_available(self):
        result = json.loads(self.run_cli("batch", "read", self.project, "--lines-only").stdout)
        self.assertIsInstance(result, list)
        self.assertEqual([line["line_num"] for line in result], [1, 3])
        self.assertNotIn("instruction", result[0])

    def test_prompt_init_uses_saved_prompt_instead_of_template(self):
        for task in ("translate", "glossary", "ai-check", "agent", "summary", "ai-check-summary", "dictionary"):
            with self.subTest(task=task):
                output = self.root / (task + ".md")
                self.run_cli("prompt", "init", "--project", self.project, "--task", task, "--line-count", 2, "--out", output)
                text = output.read_text(encoding="utf-8")
                selected = prompt.render_variables(self.prompts[prompt.TASK_FIELDS[task]], self.data, 2).replace("\r\n", "\n")
                self.assertTrue(text.startswith(selected))
                self.assertNotIn("{{", text)

    def test_exact_prompt_extraction_is_idempotent_and_does_not_overwrite_edits(self):
        root = self.root / "prompts"
        self.run_cli("prompt", "extract", self.project, "--out-dir", root)
        for field, text in self.prompts.items():
            self.assertEqual((root / (field + ".md")).read_bytes().decode("utf-8"), text)
        self.run_cli("prompt", "extract", self.project, "--out-dir", root)
        edited = root / "prompt_header.md"
        edited.write_text("user edit", encoding="utf-8")
        self.run_cli("prompt", "extract", self.project, "--out-dir", root, success=False)
        self.assertEqual(edited.read_text(encoding="utf-8"), "user edit")
        self.run_cli("prompt", "extract", self.project, "--out-dir", root, "--overwrite")
        self.assertEqual(edited.read_bytes().decode("utf-8"), self.prompts["prompt_header"])

    def test_zip_prompts_survive_task_read_and_checked_write(self):
        project = self.root / "project.copas.zip"
        cstl_io.save_cstl(str(project), self.data)
        packet = batch.read_context_batch(str(project), size=1)
        batch.write_back(str(project), [{"line_num": 1, "trans_name": "Mugi", "trans_message": "Halo."}], packet)
        saved = cstl_io.load_cstl(str(project))
        for field, text in self.prompts.items():
            self.assertEqual(saved[field], text)
        self.assertEqual(packet["prompts"], self.prompts)

    def test_missing_task_prompt_uses_fallback_without_replacing_saved_fields(self):
        data = dict(self.data)
        data["glossary_prompt"] = " \n "
        data.pop("agent_prompt")
        for task in ("glossary", "agent"):
            info = prompt.project_prompt_info(data, task, 3)
            self.assertEqual(info["prompt_source"], "fallback")
            self.assertNotIn("{{sourceLang}}", info["instruction"])
        self.assertEqual(data["glossary_prompt"], " \n ")
        self.assertNotIn("agent_prompt", data)

    def test_saved_glossary_is_loaded_from_project(self):
        locked = self.root / "glossary.locked.json"
        self.run_cli("glossary", "from-project", self.project, "--out", locked)
        data = json.loads(locked.read_text(encoding="utf-8"))
        self.assertEqual(data["characters"][0]["canonical"], "麦")
        self.assertEqual(data["characters"][0]["render"], "Mugi")

    def test_worker_packet_keeps_context_outside_assigned_files_and_checked_output(self):
        self.data.update({"file_order": ["before.json", "worker.json", "after.json"],
                          "context_lines": 1, "context_lines_after": 1, "context_type": "both"})
        self.data["lines"] = [
            {"line_num": 30, "file": "after.json", "name": None, "message": "後で。", "is_translated": False},
            {"line_num": 20, "file": "worker.json", "name": None, "message": "雨。", "is_translated": False},
            {"line_num": 10, "file": "before.json", "name": "麦", "message": "風。", "is_translated": True,
             "trans_name": "Mugi", "trans_message": "Angin."},
        ]
        cstl_io.save_cstl(str(self.project), self.data)
        packet = json.loads(self.run_cli("batch", "read", self.project, "--file", "worker.json").stdout)
        self.assertEqual([line["line_num"] for line in packet["lines"]], [20])
        self.assertEqual([line["line_num"] for line in packet["context_before"]], [10])
        self.assertEqual([line["line_num"] for line in packet["context_after"]], [30])
        self.assertEqual(packet["context_before"][0]["trans_message"], "Angin.")
        self.assertEqual(packet["context_type"], "both")
        self.assertIn("Translate 1 lines", packet["instruction"])
        pristine = self.project.read_bytes()
        with self.assertRaises(ValueError):
            batch.write_back(str(self.project), [{"line_num": 20, "trans_message": "Hujan."},
                                                 {"line_num": 30, "trans_message": "Nanti."}], packet)
        self.assertEqual(self.project.read_bytes(), pristine)
        batch.write_back(str(self.project), [{"line_num": 20, "trans_message": "Hujan."}], packet)
        saved = cstl_io.load_cstl(str(self.project))
        self.assertFalse(next(line for line in saved["lines"] if line["line_num"] == 30)["is_translated"])

    def test_worker_file_filter_paginates_in_display_order_and_allows_context_overrides(self):
        packet = json.loads(self.run_cli("batch", "read", self.project, "--file", "scene.json",
                                         "--file", "other.json", "--size", 1, "--offset", 1,
                                         "--context-before", 0, "--context-after", 0).stdout)
        self.assertEqual([line["line_num"] for line in packet["lines"]], [3])
        self.assertEqual(packet["context_before"], [])
        self.assertEqual(packet["context_after"], [])


if __name__ == "__main__":
    unittest.main()
