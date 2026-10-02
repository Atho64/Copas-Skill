"""In-process end-to-end tests for copas_reverse.

Builds a fake game folder (XP3 marker + a CP932 script blob), then walks the
whole pipeline: detect -> carve -> VNTP translate -> build-spec -> apply ->
verify. Run with:

    python -B -m unittest discover -s tests -v
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
sys.path.insert(0, SCRIPTS)

from copas_reverse import carve, detect, patch, vntp  # noqa: E402

JP_LINES = [
    ("ため子", "今日はとても良い天気ですね。\n散歩に行きましょう。"),
    (None, "空が青いですね。"),
    ("ため子", "そうね、行きましょう！"),
]
ID_LINES = [
    ("Tameko", "Cuaca hari ini indah sekali.\nAyo berjalan-jalan."),
    (None, "Langit biru."),
    ("Tameko", "Iya, ayo pergi!"),
]


def _build_script_bin() -> bytes:
    """A fake CP932 script blob: header, then strings separated by 0x00."""
    parts = [b"SCRIPT\x00\x01\x02"]
    for name, msg in JP_LINES:
        if name:
            parts.append(name.encode("cp932") + b"\x00")
        segs = msg.split("\n")
        # display lines are separate slots joined by a 0x0A newline byte
        parts.append(b"\x0a".join(s.encode("cp932") for s in segs) + b"\x00")
    parts.append(b"END\x00")
    return b"".join(parts)


class PipelineTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="copas_reverse_test_"))
        self.game = self.tmp / "MyGame"
        (self.game / "data").mkdir(parents=True)
        (self.game / "script.xp3").write_bytes(b"XP3\x0d\x0a\x20\x0a\x1a\x0b\x0d\x0a" + b"\x00" * 32)
        (self.game / "Data.wolf").write_bytes(b"DX\x00\x00\x00\x01" + b"\x00" * 26)
        (self.game / "data" / "script.bin").write_bytes(_build_script_bin())
        self.work = self.tmp / "MyGame_extract"
        for d in ("original", "id_input", "id_output", "metadata", "reports"):
            (self.work / d).mkdir(parents=True)
        shutil.copy2(self.game / "data" / "script.bin", self.work / "original" / "script.bin")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture(self, fn, *args):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            fn(*args)
        return buf_out.getvalue(), buf_err.getvalue()

    def _carve(self, out_name="carve_script.json") -> Path:
        out = self.work / "metadata" / out_name
        self._capture(carve.main, ["file", str(self.work / "original" / "script.bin"),
                      "--encoding", "cp932", "--min-len", "3", "--out", str(out)])
        return out


class TestDetect(PipelineTestBase):
    def test_finds_kirikiri(self):
        out, _ = self._capture(detect.main, [str(self.game)])
        self.assertIn("kirikiri", out)
        self.assertIn("XP3 archive header", out)

    def test_finds_wolf_rpg(self):
        out, _ = self._capture(detect.main, [str(self.game)])
        self.assertIn("wolf", out)
        self.assertIn("Wolf RPG Editor archive", out)

    def test_unknown_family_maps_to_catalog(self):
        self.assertEqual(detect._page_for("liarsoft"),
                         "references/engines/catalog.md")
        self.assertEqual(detect._page_for("kirikiri"),
                         "references/engines/kirikiri.md")

    def test_read_only(self):
        before = (self.game / "data" / "script.bin").read_bytes()
        self._capture(detect.main, [str(self.game)])
        self.assertEqual(before, (self.game / "data" / "script.bin").read_bytes())


class TestCarve(PipelineTestBase):
    def test_offsets_are_exact(self):
        out = self._capture(carve.main, ["file",
                            str(self.work / "original" / "script.bin"),
                            "--encoding", "cp932", "--min-len", "3"])[0]
        dump = json.loads(out)
        texts = [run["text"] for run in dump["runs"]]
        self.assertIn("今日はとても良い天気ですね。", texts)
        self.assertIn("空が青いですね。", texts)
        self.assertIn("ため子", texts)
        raw = (self.work / "original" / "script.bin").read_bytes()
        target = next(run for run in dump["runs"] if run["text"] == "空が青いですね。")
        self.assertEqual(raw[target["offset"]:target["offset"] + target["length"]],
                         "空が青いですね。".encode("cp932"))


class TestVntp(PipelineTestBase):
    def test_validate_flags_kana(self):
        f = self.tmp / "bad.json"
        f.write_text(json.dumps([{"name": "Tameko", "message": "まだ日本語です"}],
                                ensure_ascii=False), encoding="utf-8")
        res = vntp.check_file(str(f))
        self.assertTrue(any("kana" in w for w in res["warnings"]))

    def test_pair_reports_count_mismatch(self):
        d1 = self.tmp / "in"; d2 = self.tmp / "out"
        d1.mkdir(); d2.mkdir()
        a = d1 / "script.json"; b = d2 / "script.json"
        a.write_text(json.dumps([{"name": None, "message": "x"}]), encoding="utf-8")
        b.write_text(json.dumps([{"name": None, "message": "y"},
                                 {"name": None, "message": "z"}]), encoding="utf-8")
        rows, ok = vntp.pair_dirs(str(a), str(b))
        self.assertFalse(ok)
        self.assertEqual(rows[0]["status"], "COUNT MISMATCH")

    def test_pair_ok(self):
        inp = [{"name": n, "message": m} for n, m in JP_LINES]
        out = [{"name": n, "message": m} for n, m in ID_LINES]
        (self.work / "id_input" / "script.json").write_text(
            json.dumps(inp, ensure_ascii=False), encoding="utf-8")
        (self.work / "id_output" / "script.json").write_text(
            json.dumps(out, ensure_ascii=False), encoding="utf-8")
        rows, ok = vntp.pair_dirs(str(self.work / "id_input"),
                                  str(self.work / "id_output"))
        self.assertTrue(ok)
        self.assertEqual(rows[0]["status"], "OK")


class TestPatchPipeline(PipelineTestBase):
    def setUp(self):
        super().setUp()
        self.inp = self.work / "id_input" / "script.json"
        self.out = self.work / "id_output" / "script.json"
        self.inp.write_text(json.dumps([{"name": n, "message": m} for n, m in JP_LINES],
                                       ensure_ascii=False), encoding="utf-8")
        self.out.write_text(json.dumps([{"name": n, "message": m} for n, m in ID_LINES],
                                       ensure_ascii=False), encoding="utf-8")

    def _spec(self, out_name="patch_script.json"):
        spec = self.work / "metadata" / out_name
        out, err = self._capture(
            patch.main, ["build-spec",
            "--carve", str(self._carve()),
            "--input", str(self.inp), "--output", str(self.out),
            "--file-label", "data/script.bin",
            "--encoding", "cp932", "--newline-hex", "0a",
            "--pad", "space", "--out", str(spec)])
        return spec, out, err

    def test_full_translation_round_trip(self):
        spec, summary_out, err = self._spec()
        summary = json.loads(summary_out)
        self.assertEqual(summary["unmatched"], 0, summary)
        self.assertEqual(summary["matched"], 6, summary)  # 3 names + 3 messages

        patched = self.tmp / "patched" / "script.bin"
        self._capture(patch.main, ["apply", "--spec", str(spec),
                      "--src", str(self.work / "original" / "script.bin"),
                      "--out", str(patched)])
        self._capture(patch.main, ["verify", "--spec", str(spec),
                      "--src", str(self.work / "original" / "script.bin"),
                      "--dst", str(patched)])

        orig = (self.work / "original" / "script.bin").read_bytes()
        new = patched.read_bytes()
        self.assertEqual(len(orig), len(new), "same-length patch must keep file size")
        self.assertIn("Cuaca hari ini indah sekali.".encode("cp932"), new)
        self.assertIn("Ayo berjalan-jalan.".encode("cp932"), new)
        self.assertNotIn("今日はとても良い天気ですね。".encode("cp932"), new)
        # the 0x0A newline byte between display-line slots is preserved untouched
        self.assertIn("indah sekali.\x0aAyo".encode("cp932"), new)

    def test_identity_round_trip_is_byte_identical(self):
        spec = self.work / "metadata" / "patch_identity.json"
        out, err = self._capture(
            patch.main, ["build-spec",
            "--carve", str(self._carve()),
            "--input", str(self.inp),
            "--file-label", "data/script.bin",
            "--encoding", "cp932", "--newline-hex", "0a",
            "--pad", "space", "--out", str(spec)])
        patched = self.tmp / "patched" / "identity.bin"
        self._capture(patch.main, ["apply", "--spec", str(spec),
                      "--src", str(self.work / "original" / "script.bin"),
                      "--out", str(patched)])
        self.assertEqual(patched.read_bytes(),
                         (self.work / "original" / "script.bin").read_bytes(),
                         "backfilling untranslated text must be byte-identical")

    def test_overflow_is_refused(self):
        (self.work / "id_output" / "script.json").write_text(
            json.dumps([{"name": n, "message": "x" * 500} for n, m in JP_LINES],
                       ensure_ascii=False), encoding="utf-8")
        spec, _, _ = self._spec("patch_overflow.json")
        patched = self.tmp / "patched" / "overflow.bin"
        with self.assertRaises(SystemExit) as cm:
            self._capture(patch.main, ["apply", "--spec", str(spec),
                          "--src", str(self.work / "original" / "script.bin"),
                          "--out", str(patched)])
        self.assertEqual(cm.exception.code, 1)
        self.assertFalse(patched.exists(), "no output may be written on overflow")

    def test_stale_source_is_rejected(self):
        spec, _, _ = self._spec()
        # flip one byte INSIDE the first spec slot (the speaker-name run at offset 9)
        orig = (self.work / "original" / "script.bin").read_bytes()
        stale = self.tmp / "stale.bin"
        stale.write_bytes(orig[:10] + bytes([orig[10] ^ 0xFF]) + orig[11:])
        with self.assertRaises(SystemExit):
            self._capture(patch.main, ["apply", "--spec", str(spec),
                          "--src", str(stale),
                          "--out", str(self.tmp / "patched" / "stale_out.bin")])


if __name__ == "__main__":
    unittest.main()
