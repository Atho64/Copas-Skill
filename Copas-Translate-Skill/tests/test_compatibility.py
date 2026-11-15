"""Exercise CopasTool backup translation without launching the app or calling an AI."""
from __future__ import annotations

import base64
import contextlib
import copy
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cstl_translate import batch, cstl_io, export, glossary, parse, prompt


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="copas_skill_test_")
        self.root = Path(self.temp.name)
        self.project = self.root / "project.copas"
        self.data = cstl_io.build_minimal_cstl("Fixture")
        self.data.update({
            "file_order": ["opening.json", "later.json"],
            "context_lines": 1,
            "context_lines_after": 1,
            "context_type": "both",
            "glossary_text": "[character] 麦 = Mugi {given name}",
            "glossary_in_loop": True,
            "ai_check_deep_mode": True,
            "gameEngineCacheDir": "fixture/cache",
            "gameEngineGameDir": "fixture/game-copy",
            "future_setting": {"unknown": [1, 2]},
            "lines": [
                {"line_num": 4, "file": "later.json", "name": None, "message": "後で。", "is_translated": False},
                {"line_num": 1, "file": "opening.json", "name": "麦", "message": "先に。", "trans_message": "Duluan.", "trans_name": "Mugi", "is_translated": True},
                {"line_num": 2, "file": "opening.json", "name": "Nino, Shin'ichirō", "message": "こんにちは。  ", "is_translated": False,
                 "ref_lang_1": "Hello.  ", "ref_lang_1_name": "Nino, Shin'ichirō", "custom_index": {"scene_index": 8, "text_index": 0},
                 "_ai_checked": True, "future_line_field": {"keep": True}},
                {"line_num": 3, "file": "opening.json", "name": None, "message": "風。", "is_translated": False},
                {"line_num": 5, "file": "opening.json", "name": None, "message": "hidden", "_hidden": True, "is_translated": False},
                {"line_num": 6, "file": "opening.json", "name": None, "message": "  ", "is_translated": False},
            ],
        })
        cstl_io.save_cstl(str(self.project), self.data)

    def tearDown(self):
        self.temp.cleanup()

    def translation(self, num=2):
        return {"line_num": num, "trans_message": "Halo.<br>{0}  ", "trans_name": "Nino, Shin'ichirō"}

    def test_context_uses_display_order_without_translating_context(self):
        view = batch.read_context_batch(str(self.project), size=1)
        self.assertEqual([line["line_num"] for line in view["lines"]], [2])
        self.assertEqual([line["line_num"] for line in view["context_before"]], [1])
        self.assertEqual([line["line_num"] for line in view["context_after"]], [3])
        self.assertEqual(view["lines"][0]["ref_lang_1"], "Hello.  ")
        self.assertEqual(view["context_before"][0]["trans_name"], "Mugi")
        self.assertEqual(view["context_type"], "both")
        self.assertEqual(view["glossary_text"], self.data["glossary_text"])
        self.assertEqual([line["line_num"] for line in batch.read_batch(str(self.project))], [2, 3, 4])

    def test_context_overrides_and_completed_project(self):
        view = batch.read_context_batch(str(self.project), size=1, before=0, after=0)
        self.assertEqual(view["context_before"], [])
        self.assertEqual(view["context_after"], [])
        for line in self.data["lines"]:
            line["is_translated"] = True
        cstl_io.save_cstl(str(self.project), self.data)
        view = batch.read_context_batch(str(self.project))
        self.assertEqual(view["lines"], [])
        self.assertEqual(view["context_before"], [])
        self.assertEqual(view["context_after"], [])

    def test_invalid_batch_options_fail(self):
        with self.assertRaises(ValueError):
            batch.read_batch(str(self.project), size=0)
        with self.assertRaises(ValueError):
            batch.read_context_batch(str(self.project), after=-1)
        with self.assertRaises(ValueError):
            batch.read_translated_batch(str(self.project), offset=-1)

    def test_checked_write_preserves_metadata_and_advances(self):
        view = batch.read_context_batch(str(self.project), size=1)
        self.assertEqual(batch.write_back(str(self.project), [self.translation()], view), 1)
        saved = cstl_io.load_cstl(str(self.project))
        line = next(line for line in saved["lines"] if line["line_num"] == 2)
        self.assertEqual(line["trans_message"], "Halo.\\n{0}  ")
        self.assertEqual(line["trans_name"], "Nino, Shin'ichirō")
        self.assertEqual(line["message"], "こんにちは。  ")
        self.assertEqual(line["custom_index"], {"scene_index": 8, "text_index": 0})
        self.assertTrue(line["_ai_checked"])
        self.assertEqual(line["future_line_field"], {"keep": True})
        for key in ("future_setting", "gameEngineCacheDir", "gameEngineGameDir", "glossary_in_loop", "ai_check_deep_mode"):
            self.assertEqual(saved[key], self.data[key])
        self.assertEqual(batch.read_batch(str(self.project), size=1)[0]["line_num"], 3)
        self.assertEqual(len(list(self.root.glob("project.copas.bak.*"))), 1)

    def test_checked_write_rejects_misalignment_before_mutation(self):
        view = batch.read_context_batch(str(self.project), size=2)
        cases = [
            [self.translation()],
            [{"line_num": 3, "trans_message": "Angin."}, self.translation()],
            [self.translation(), self.translation()],
            [self.translation(), {"line_num": 4, "trans_message": "Nanti."}],
        ]
        pristine = self.project.read_bytes()
        for updates in cases:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                batch.write_back(str(self.project), updates, view)
            self.assertEqual(self.project.read_bytes(), pristine)
        self.assertEqual(list(self.root.glob("*.bak.*")), [])

    def test_checked_write_rejects_speaker_changes(self):
        view = batch.read_context_batch(str(self.project), size=2)
        for updates in (
            [{"line_num": 2, "trans_message": "Halo."}, {"line_num": 3, "trans_message": "Angin."}],
            [self.translation(), {"line_num": 3, "trans_message": "Angin.", "trans_name": "Invented"}],
        ):
            with self.assertRaises(ValueError):
                batch.write_back(str(self.project), updates, view)
        self.assertEqual(list(self.root.glob("*.bak.*")), [])

    def test_checked_write_rejects_changed_source(self):
        snapshot = batch.read_batch(str(self.project), size=1)
        self.data["lines"][2]["message"] = "different source"
        cstl_io.save_cstl(str(self.project), self.data)
        pristine = self.project.read_bytes()
        with self.assertRaises(ValueError):
            batch.write_back(str(self.project), [self.translation()], snapshot)
        self.assertEqual(self.project.read_bytes(), pristine)

    def test_narration_checked_write_clears_stale_translated_speaker(self):
        self.data["lines"][3]["trans_name"] = "Stale"
        self.data["lines"][2]["is_translated"] = True
        cstl_io.save_cstl(str(self.project), self.data)
        snapshot = batch.read_batch(str(self.project), size=1)
        batch.write_back(str(self.project), [{"line_num": 3, "trans_message": "Angin.", "trans_name": None}], snapshot)
        saved = cstl_io.load_cstl(str(self.project))
        self.assertIsNone(next(line for line in saved["lines"] if line["line_num"] == 3)["trans_name"])

    def test_legacy_partial_write_and_review_pagination(self):
        self.assertEqual(batch.write_back(str(self.project), [self.translation(), self.translation(999)]), 1)
        first = batch.read_translated_batch(str(self.project), size=1)
        second = batch.read_translated_batch(str(self.project), size=1, offset=1)
        self.assertEqual(first[0]["line_num"], 1)
        self.assertEqual(second[0]["line_num"], 2)
        self.assertEqual(batch.read_translated_batch(str(self.project), size=1, offset=2), [])

    def test_json_and_zip_backups_preserve_engine_and_binary_data(self):
        raw = b"\x00\xff\x80AST fixture\r\n"
        data = copy.deepcopy(self.data)
        data["use_dialogue_tags"] = False
        data["customRawBuffers"] = {"nested/scenario.bin": base64.b64encode(raw).decode("ascii")}
        for extension in (".copas", ".cstl", ".copas.zip", ".cstl.zip"):
            with self.subTest(extension=extension):
                path = self.root / ("roundtrip" + extension)
                cstl_io.save_cstl(str(path), data)
                snapshot = batch.read_context_batch(str(path), size=1)
                batch.write_back(str(path), [self.translation()], snapshot)
                saved = cstl_io.load_cstl(str(path))
                self.assertEqual(saved["future_setting"], data["future_setting"])
                self.assertEqual(saved["gameEngineCacheDir"], data["gameEngineCacheDir"])
                self.assertIs(saved["use_dialogue_tags"], False)
                self.assertEqual(base64.b64decode(saved["customRawBuffers"]["nested/scenario.bin"]), raw)
                if extension.endswith(".zip"):
                    with zipfile.ZipFile(path) as archive:
                        self.assertEqual(archive.read("custom_sources/nested/scenario.bin"), raw)

    def test_vntp_roundtrip_keeps_spaces_newlines_and_comma_names(self):
        path = self.root / "source.json"
        source = [{"name": "Nino, Shin'ichirō", "message": "  一行\n二行。  "}]
        path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        data = parse.parse_inputs(str(path))
        self.assertEqual(data["lines"][0]["message"], "  一行\\n二行。  ")
        cstl_io.save_cstl(str(self.project), data)
        paths = export.export_json(str(self.project), str(self.root / "out"))
        self.assertEqual(json.loads(Path(paths[0]).read_text(encoding="utf-8")), source)

    def test_ampersand_speakers_remain_one_translation_row(self):
        for index, name in enumerate(("Nino & Menoa", "Nino&Menoa", "Nino, Menoa & Ichito", "ニノ＆メノア", "??? & ???")):
            with self.subTest(name=name):
                source = self.root / f"group_{index}.json"
                source.write_text(json.dumps([{"name": name, "message": "こんにちは。"}], ensure_ascii=False), encoding="utf-8")
                data = parse.parse_inputs(str(source))
                cstl_io.save_cstl(str(self.project), data)
                snapshot = batch.read_batch(str(self.project))
                self.assertEqual(len(snapshot), 1)
                self.assertEqual(snapshot[0]["name"], name)
                batch.write_back(str(self.project), [{"line_num": 1, "trans_name": name, "trans_message": "Halo."}], snapshot)
                output = export.export_json(str(self.project), str(self.root / f"out_group_{index}"))
                self.assertEqual(json.loads(Path(output[0]).read_text(encoding="utf-8")), [{"name": name, "message": "Halo."}])

    def test_context_reports_saved_and_legacy_dialogue_tag_preference(self):
        self.assertIs(cstl_io.build_minimal_cstl("new")["use_dialogue_tags"], True)
        self.data.pop("use_dialogue_tags", None)
        cstl_io.save_cstl(str(self.project), self.data)
        self.assertIs(batch.read_context_batch(str(self.project))["use_dialogue_tags"], True)
        self.data["use_dialogue_tags"] = False
        cstl_io.save_cstl(str(self.project), self.data)
        snapshot = batch.read_context_batch(str(self.project), size=1)
        self.assertIs(snapshot["use_dialogue_tags"], False)
        batch.write_back(str(self.project), [self.translation()], snapshot)
        self.assertIs(cstl_io.load_cstl(str(self.project))["use_dialogue_tags"], False)

    def test_numbered_prompt_tag_toggle_preserves_other_formats(self):
        plain = prompt.build_prompt("numbered", "Japanese", "Indonesian", 2, dialogue_tags=False)
        self.assertNotIn("[D]", plain)
        self.assertNotIn("[N]", plain)
        self.assertIn('12. Spica: "[translated dialogue]"', plain)
        self.assertIn("13. [translated narration]", plain)
        kagikakko = prompt.build_prompt("numbered", kagikakko=True, dialogue_tags=False)
        self.assertIn("Spica: 「[translated dialogue]」", kagikakko)
        for fmt in ("batch", "block", "xml", "jsonl", "jsonarray"):
            self.assertEqual(prompt.build_prompt(fmt, dialogue_tags=False), prompt.build_prompt(fmt))
        self.assertIn("[D]", prompt.build_prompt("numbered"))

    def test_keep_source_policy_survives_glossary_injection(self):
        locked = {"characters": [{"canonical": "麦", "render": "Mugi", "keep_source": True}],
                  "terms": [{"src": "炬燵", "dst": "kotatsu", "keep_source": True}]}
        locked_path = self.root / "glossary.locked.json"
        locked_path.write_text(json.dumps(locked), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            glossary.inject_into_cstl(str(self.project), str(locked_path))
        saved = cstl_io.load_cstl(str(self.project))
        converted = glossary.parse_glossary_text(saved["glossary_text"])
        self.assertEqual(converted["characters"][0]["render"], "麦")
        self.assertEqual(converted["terms"][0]["dst"], "炬燵")
        self.assertEqual(saved["gameEngineCacheDir"], self.data["gameEngineCacheDir"])

    @unittest.skipUnless(importlib.util.find_spec("bs4") and importlib.util.find_spec("lxml"), "optional EPUB dependencies not installed")
    def test_basic_epub_import_translation_and_export(self):
        epub = self.root / "book.epub"
        with zipfile.ZipFile(epub, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
            archive.writestr("OEBPS/content.opf", '<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="chapter" href="chapter.xhtml"/></manifest><spine><itemref idref="chapter"/></spine></package>')
            archive.writestr("OEBPS/chapter.xhtml", '<html><body><p>朝。</p><p>風。</p></body></html>')
            archive.writestr("OEBPS/image.bin", b"unchanged asset")
        data = parse.parse_inputs(str(epub))
        self.assertEqual([line["message"] for line in data["lines"]], ["朝。", "風。"])
        cstl_io.save_cstl(str(self.project), data)
        snapshot = batch.read_batch(str(self.project))
        batch.write_back(str(self.project), [{"line_num": 1, "trans_message": "Pagi."},
                                             {"line_num": 2, "trans_message": "Angin."}], snapshot)
        out = export.export_epub(str(self.project), str(self.root / "epub_out"))
        with zipfile.ZipFile(out[0]) as archive:
            chapter = archive.read("OEBPS/chapter.xhtml").decode("utf-8")
            self.assertIn("Pagi.", chapter)
            self.assertIn("Angin.", chapter)
            self.assertNotIn("朝。", chapter)
            self.assertEqual(archive.read("OEBPS/image.bin"), b"unchanged asset")

    def test_prompt_cli_and_checked_batch_cli(self):
        env = dict(os.environ, PYTHONPATH=str(SCRIPTS), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")

        def run(module, *args):
            result = subprocess.run([sys.executable, "-B", "-m", "cstl_translate." + module, *map(str, args)],
                                    env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        for fmt in prompt.PROMPT_HEADERS:
            out = self.root / (fmt + ".md")
            run("prompt", "init", "--format", fmt, "--source-lang", "Japanese", "--target-lang", "Indonesian", "--line-count", 1, "--out", out)
            text = out.read_text(encoding="utf-8")
            self.assertNotIn("{{", text)
            self.assertIn("Japanese", text)
            self.assertIn("Indonesian", text)
        untagged = self.root / "numbered_untagged.md"
        run("prompt", "init", "--format", "numbered", "--no-dialogue-tags", "--kagikakko", "--out", untagged)
        content = untagged.read_text(encoding="utf-8")
        self.assertNotIn("[D]", content)
        self.assertNotIn("[N]", content)
        self.assertIn("Spica: 「[translated dialogue]」", content)
        snapshot = self.root / "batch.json"
        snapshot.write_text(run("batch", "read", self.project, "--size", 1, "--with-context"), encoding="utf-8")
        updates = self.root / "translations.json"
        updates.write_text(json.dumps([self.translation()]), encoding="utf-8-sig")
        run("batch", "write", self.project, updates, "--expect-batch", snapshot)
        self.assertEqual(json.loads(run("batch", "read", self.project, "--size", 1))[0]["line_num"], 3)


if __name__ == "__main__":
    unittest.main()
