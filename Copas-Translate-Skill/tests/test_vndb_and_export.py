"""Tests for .copas-only ZIP export and VNDB Kana API v2 glossary fetching."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import zipfile

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cstl_translate import cstl_io, export, glossary, parse, vndb


class CopasZipExportAndVndbTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cstl_vndb_zip_")
        self.root = Path(self.temp.name)
        self.env = dict(
            os.environ,
            PYTHONPATH=str(SCRIPTS),
            PYTHONIOENCODING="utf-8",
            PYTHONDONTWRITEBYTECODE="1",
        )

    def tearDown(self):
        self.temp.cleanup()

    def _run_cli(self, module: str, *args) -> subprocess.CompletedProcess:
        res = subprocess.run(
            [sys.executable, "-B", "-m", f"cstl_translate.{module}", *map(str, args)],
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0, res.stderr + "\n" + res.stdout)
        return res

    def _sample_project(self, path: Path, project_name: str = "My Sample VN", source_lang: str = "Japanese"):
        data = cstl_io.build_minimal_cstl(project_name, source_lang=source_lang, target_lang="Indonesian")
        data["use_dialogue_tags"] = False
        data["lines"] = [
            {
                "line_num": 1,
                "file": "ch1.json",
                "name": "麦",
                "message": "おはようございます。",
                "trans_name": "Mugi",
                "trans_message": "Selamat pagi.",
                "is_translated": True,
            },
            {
                "line_num": 2,
                "file": "ch1.json",
                "name": None,
                "message": "早川麦は走った。",
                "trans_name": None,
                "trans_message": "Hayakawa Mugi berlari.",
                "is_translated": True,
            },
        ]
        cstl_io.save_cstl(str(path), data)
        return data

    def test_export_copas_zip_from_copas_contains_only_copas_file(self):
        proj = self.root / "project.copas"
        self._sample_project(proj, project_name="Summer:VN?")
        out_dir = self.root / "deliverable"

        res = self._run_cli("export", "--cstl", str(proj), "--output", str(out_dir), "--format", "copas-zip")
        produced = [Path(line.strip()) for line in res.stdout.splitlines() if line.strip()]
        self.assertEqual(len(produced), 1)
        zip_path = produced[0]
        self.assertEqual(zip_path.name, "Summer_VN_.zip")
        self.assertEqual(list(out_dir.iterdir()), [zip_path])

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            self.assertEqual(names, ["Summer_VN_.copas"])
            payload = json.loads(zf.read("Summer_VN_.copas").decode("utf-8"))
            self.assertEqual(payload["projectName"], "Summer:VN?")
            self.assertEqual(payload["lines"][0]["trans_message"], "Selamat pagi.")

        # Re-loading directly from the delivered .zip works transparently
        reloaded = cstl_io.load_cstl(str(zip_path))
        self.assertEqual(reloaded["lines"][1]["trans_message"], "Hayakawa Mugi berlari.")
        parsed = parse.parse_inputs(str(zip_path))
        self.assertEqual(len(parsed["lines"]), 2)
        self.assertIs(parsed["use_dialogue_tags"], False)

    def test_export_copas_alias_from_copas_zip_preserves_custom_sources(self):
        proj = self.root / "CustomEngine.copas.zip"
        raw = b"\x00\x01ENGINE_RAW"
        data = self._sample_project(proj, project_name="IgnoredTitle")
        data["customRawBuffers"] = {"scripts/01.ast": base64.b64encode(raw).decode("ascii")}
        cstl_io.save_cstl(str(proj), data)

        out_dir = self.root / "out_alias"
        paths = export.export_copas_zip(str(proj), str(out_dir))
        self.assertEqual(len(paths), 1)
        zip_path = Path(paths[0])
        self.assertEqual(zip_path.name, "CustomEngine.zip")

        with zipfile.ZipFile(zip_path, "r") as zf:
            self.assertEqual(zf.namelist(), ["CustomEngine.copas"])
            inner = json.loads(zf.read("CustomEngine.copas").decode("utf-8"))
            self.assertEqual(base64.b64decode(inner["customRawBuffers"]["scripts/01.ast"]), raw)

        # CLI --format copas also produces the .copas-only ZIP
        out_dir2 = self.root / "out_cli_alias"
        self._run_cli("export", "--cstl", str(proj), "--output", str(out_dir2), "--format", "copas", "--name", "Release_ID")
        z2 = out_dir2 / "Release_ID.zip"
        with zipfile.ZipFile(z2, "r") as zf:
            self.assertEqual(zf.namelist(), ["Release_ID.copas"])

    def test_invalid_zip_still_raises_missing_project_json(self):
        bad_zip = self.root / "invalid.copas.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("readme.txt", "not a project")
        with self.assertRaises(ValueError):
            cstl_io.load_cstl(str(bad_zip))

    def test_vndb_helpers_id_and_bbcode_cleanup(self):
        self.assertEqual(vndb.normalize_vn_id("v17"), "v17")
        self.assertEqual(vndb.normalize_vn_id("17"), "v17")
        self.assertEqual(vndb.normalize_vn_id("https://vndb.org/v20431/chars#chars"), "v20431")
        self.assertIsNone(vndb.normalize_vn_id("Summer Pockets"))

        raw = "Calm friend. [b]Heroine[/b] from [url=/v17]LeMU[/url].\n[spoiler]Secret twin[/spoiler]"
        self.assertEqual(vndb.clean_vndb_text(raw, include_spoilers=False), "Calm friend. Heroine from LeMU.")
        self.assertIn("Secret twin", vndb.clean_vndb_text(raw, include_spoilers=True))

    def test_vndb_build_glossary_handles_pagination_splits_collisions_and_merge(self):
        proj = self.root / "project.copas"
        self._sample_project(proj, project_name="Test VN")

        vn_payload = {
            "results": [{
                "id": "v99",
                "title": "Test VN",
                "alttitle": "テストVN",
                "titles": [{"lang": "ja", "title": "テストVN", "official": True, "main": True}],
                "aliases": [],
                "description": "A [b]school[/b] story. [spoiler]Aliens did it.[/spoiler]",
            }]
        }
        char_pages = [
            {
                "more": True,
                "results": [
                    {
                        "id": "c1",
                        "name": "Hayakawa Mugi",
                        "original": "早川 麦",
                        "aliases": ["ムギ", "Mugi-chan", "ムギちゃん", "Kid", "早川 麦"],
                        "sex": ["m", "m"],
                        "description": "Protagonist [spoiler]from space[/spoiler].",
                        "vns": [{"id": "v99", "role": "main", "spoiler": 0}],
                    },
                    {
                        "id": "c2",
                        "name": "Mary Smith",
                        "original": "メアリ・スミス",
                        "aliases": ["メアリ", "Mary", "ムギ"],  # "ムギ" collides with c1 -> must drop cleanly on both
                        "sex": ["f", "f"],
                        "description": "Transfer student.",
                        "vns": [{"id": "v99", "role": "primary", "spoiler": 0}],
                    },
                ],
            },
            {
                "more": False,
                "results": [
                    {
                        "id": "c3",
                        "name": "Hokuto",
                        "original": "ホクト",
                        "aliases": ["Kid", "ホクトン"],
                        "sex": ["m", "m"],
                        "description": "[spoiler]Spoiler-only char[/spoiler]",
                        "vns": [{"id": "v99", "role": "side", "spoiler": 2}],
                    }
                ],
            },
        ]
        seen_pages = []

        def fake_post(endpoint: str, payload: dict) -> dict:
            if endpoint == "vn":
                return vn_payload
            if endpoint == "character":
                page = payload.get("page", 1)
                seen_pages.append(page)
                return char_pages[page - 1]
            raise AssertionError(endpoint)

        chars = vndb.fetch_vn_characters("v99", post_fn=fake_post)
        self.assertEqual(seen_pages, [1, 2])
        self.assertEqual(len(chars), 3)

        existing = {
            "characters": [
                {"canonical": "スピカ", "render": "Spika", "aliases": [], "type": "character", "desc": "user custom"}
            ],
            "terms": [{"src": "旧校舎", "dst": "gedung sekolah lama"}],
            "non_translate": [],
        }
        locked, records = vndb.build_glossary_from_vndb(
            "v99",
            chars,
            vn_meta=vn_payload["results"][0],
            cstl_path=str(proj),
            max_spoiler=1,
            existing_locked=existing,
        )
        # c3 excluded because spoiler=2 > max_spoiler=1
        self.assertEqual([r["canonical"] for r in records], ["早川麦", "メアリ・スミス"])
        by_canon = {c["canonical"]: c for c in locked["characters"]}
        self.assertIn("スピカ", by_canon)  # existing entry preserved
        self.assertEqual(by_canon["スピカ"]["render"], "Spika")
        self.assertEqual(by_canon["早川麦"]["render"], "Hayakawa Mugi")
        self.assertIn("早川 麦", by_canon["早川麦"]["aliases"])
        # Honorific alias "Mugi-chan" / "ムギちゃん" excluded from match aliases so lint_locked stays clean
        self.assertNotIn("Mugi-chan", by_canon["早川麦"]["aliases"])
        self.assertNotIn("ムギちゃん", by_canon["早川麦"]["aliases"])
        # Shared colliding alias "ムギ" dropped cleanly from aliases on both colliding characters
        self.assertNotIn("ムギ", by_canon["早川麦"]["aliases"])
        self.assertNotIn("ムギ", by_canon["メアリ・スミス"]["aliases"])
        # Standalone speaker "麦" detected in project.copas -> auto split added cleanly!
        self.assertEqual(by_canon["麦"]["render"], "Mugi")
        # Western middle-dot name stays Given-Family even when Japanese order flips
        flipped, _ = vndb.build_glossary_from_vndb("v99", chars, name_order="given-family", split_names="none")
        flip_map = {c["canonical"]: c["render"] for c in flipped["characters"]}
        self.assertEqual(flip_map["早川麦"], "Mugi Hayakawa")
        self.assertEqual(flip_map["メアリ・スミス"], "Mary Smith")

        # Must pass glossary.lint_locked with ZERO issues
        self.assertEqual(glossary.lint_locked(locked), [])

        # Cast markdown excludes spoiler text by default
        md = vndb.format_cast_markdown(vn_payload["results"][0], records, include_spoilers=False)
        self.assertIn("Test VN (v99)", md)
        self.assertNotIn("Aliens did it", md)
        self.assertNotIn("from space", md)

    def test_vndb_cli_via_glossary_subcommand_and_inject(self):
        proj = self.root / "project.copas"
        self._sample_project(proj, project_name="My Sample VN")
        out_locked = self.root / "glossary.locked.json"
        cast_md = self.root / "vndb_cast.md"

        responses = {
            "vn": {
                "results": [{
                    "id": "v55",
                    "title": "My Sample VN",
                    "alttitle": "サンプルVN",
                    "titles": [{"lang": "en", "title": "My Sample VN", "official": True, "main": False}],
                    "aliases": [],
                    "description": "Synopsis text.",
                }]
            },
            "character": {
                "more": False,
                "results": [{
                    "id": "c10",
                    "name": "Hayakawa Mugi",
                    "original": "早川 麦",
                    "aliases": [],
                    "sex": ["m", "m"],
                    "description": "Hero.",
                    "vns": [{"id": "v55", "role": "main", "spoiler": 0}],
                }],
            },
        }

        def fake_post(endpoint: str, payload: dict) -> dict:
            return responses[endpoint]

        with mock.patch.object(vndb, "vndb_post", side_effect=fake_post):
            rc = glossary.main([
                "vndb",
                str(proj),
                "--out", str(out_locked),
                "--cast-out", str(cast_md),
                "--matched-only",
                "--inject",
            ])
        self.assertEqual(rc, 0)
        locked_data = json.loads(out_locked.read_text(encoding="utf-8"))
        self.assertEqual(locked_data["characters"][0]["canonical"], "早川麦")
        self.assertIn("My Sample VN (v55)", cast_md.read_text(encoding="utf-8"))
        saved = cstl_io.load_cstl(str(proj))
        self.assertIn("[character] 早川麦 = Hayakawa Mugi", saved["glossary_text"])

    def test_vndb_english_source_uses_keep_source(self):
        proj = self.root / "en_proj.copas"
        self._sample_project(proj, project_name="English VN", source_lang="English")
        chars = [{
            "id": "c7",
            "name": "Alice Carter",
            "original": None,
            "aliases": ["Ali", "Miss Carter"],
            "sex": ["f", "f"],
            "description": "Detective.",
            "vns": [{"id": "v88", "role": "main", "spoiler": 0}],
        }]
        locked, _ = vndb.build_glossary_from_vndb("v88", chars, cstl_path=str(proj))
        entry = locked["characters"][0]
        self.assertEqual(entry["canonical"], "Alice Carter")
        self.assertEqual(entry["render"], "Alice Carter")
        self.assertTrue(entry["keep_source"])
        self.assertIn("Ali", entry["aliases"])
        self.assertNotIn("Miss Carter", entry["aliases"])
        self.assertEqual(glossary.lint_locked(locked), [])

    def test_vndb_extracts_family_given_and_paired_nicknames_cleanly(self):
        chars = [
            {
                "id": "c1",
                "name": "Takahara Hairi",
                "original": "鷹原 羽依里",
                "aliases": ["タカ", "Taka", "パイリくん", "Pairi-kun"],
                "sex": ["m", "m"],
                "description": "Protagonist.",
                "vns": [{"id": "v20424", "role": "main", "spoiler": 0}],
            },
            {
                "id": "c2",
                "name": "Naruse Shiroha",
                "original": "鳴瀬 しろは",
                "aliases": ["Watermelon Bar-san", "スイカバーさん", "Suikabaa-san", "鷹原 しろは", "Takahara Shiroha"],
                "sex": ["f", "f"],
                "description": "Heroine.",
                "vns": [{"id": "v20424", "role": "primary", "spoiler": 0}],
            },
        ]
        locked, records = vndb.build_glossary_from_vndb("v20424", chars, split_names="all")
        by_canon = {c["canonical"]: c for c in locked["characters"]}
        # Full names + standalone family + given + paired nicknames
        self.assertEqual(by_canon["鷹原羽依里"]["render"], "Takahara Hairi")
        self.assertEqual(by_canon["鷹原"]["render"], "Takahara")
        self.assertEqual(by_canon["羽依里"]["render"], "Hairi")
        self.assertEqual(by_canon["タカ"]["render"], "Taka")
        self.assertEqual(by_canon["パイリ"]["render"], "Pairi")
        self.assertEqual(by_canon["鳴瀬"]["render"], "Naruse")
        self.assertEqual(by_canon["しろは"]["render"], "Shiroha")
        self.assertEqual(by_canon["スイカバー"]["render"], "Suikabaa")
        # Paired nicknames must NOT stay on the full-name entry's aliases
        self.assertNotIn("タカ", by_canon["鷹原羽依里"]["aliases"])
        # Multi-word alternate/spoiler name stays out of strict character entries
        self.assertNotIn("鷹原しろは", by_canon)
        self.assertIn("family=鷹原:Takahara; given=羽依里:Hairi; nick=タカ:Taka, パイリ:Pairi", by_canon["鷹原羽依里"]["desc"])
        # Cast markdown has Family | Given | Nicknames columns
        md = vndb.format_cast_markdown({"id": "v20424", "title": "Summer Pockets"}, records)
        self.assertIn("| Original | Render | Family | Given | Nicknames | Role | Sex | Aliases / Notes |", md)
        self.assertIn("タカ = Taka, パイリ = Pairi", md)
        self.assertEqual(glossary.lint_locked(locked), [])


if __name__ == "__main__":
    unittest.main()
