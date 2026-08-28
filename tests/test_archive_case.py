import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "font-effect-prompt-builder"
    / "scripts"
    / "archive_case.py"
)
SPEC = importlib.util.spec_from_file_location("archive_case", MODULE_PATH)
archive_case = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = archive_case
SPEC.loader.exec_module(archive_case)


class ArchiveCaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "skill"
        self.library = self.root / "library"
        self.library.mkdir(parents=True)
        (self.library / "index.jsonl").write_text("\n", encoding="utf-8")
        self.image = Path(self.temporary_directory.name) / "reference.JPEG"
        self.image_bytes = b"not-a-real-jpeg-but-nonempty"
        self.image.write_bytes(self.image_bytes)
        self.metadata = {
            "confirmed": True,
            "source_text": "夏日氣泡",
            "target_text": "週末放風計畫",
            "language": "traditional-chinese",
            "script": "han",
            "font_analysis": {
                "candidates": ["rounded display sans"],
                "category": "rounded display",
                "confidence": "medium",
                "evidence": "rounded terminals and inflated counters",
                "custom_modifications": "inflated width and softened corners",
            },
            "visual_analysis": "pink-orange fill/cream inline/white outline/short extrusion",
            "original_prompt": "Original prompt exact text",
            "final_prompt": "Final prompt exact text",
            "style_tags": ["playful", "cute"],
            "effect_tags": ["gradient", "outline", "extrusion-3d", "glossy"],
            "classification_notes": "",
        }

    def test_success_archives_metadata_image_and_index(self):
        result = archive_case.archive_case(
            self.metadata, self.image, self.root, today=date(2026, 8, 28)
        )
        case_id = result["case_id"]

        expected_case_id = "20260828-{}".format(
            hashlib.sha256(self.image_bytes).hexdigest()[:12]
        )
        self.assertEqual(case_id, expected_case_id)
        case_directory = self.library / "cases" / case_id
        self.assertTrue((case_directory / "case.md").is_file())
        self.assertEqual(
            (case_directory / "reference.jpeg").read_bytes(), self.image_bytes
        )
        index_lines = (self.library / "index.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(index_lines), 1)
        record = json.loads(index_lines[0])
        self.assertEqual(record["case_id"], case_id)
        self.assertEqual(record["created_at"], "2026-08-28")
        self.assertTrue(record["reference"].endswith("reference.jpeg"))
        self.assertEqual(
            record["sha256"],
            hashlib.sha256((case_directory / "reference.jpeg").read_bytes()).hexdigest(),
        )
        self.assertEqual(record["source_text"], "夏日氣泡")
        self.assertEqual(record["target_text"], "週末放風計畫")
        self.assertEqual(record["style_tags"], ["cute", "playful"])
        self.assertEqual(
            record["effect_tags"], ["extrusion-3d", "glossy", "gradient", "outline"]
        )

    def test_missing_final_prompt_leaves_no_archive(self):
        metadata = dict(self.metadata)
        metadata["final_prompt"] = ""

        with self.assertRaisesRegex(archive_case.ArchiveError, "final_prompt"):
            archive_case.archive_case(metadata, self.image, self.root)

        self.assertEqual((self.library / "index.jsonl").read_text(encoding="utf-8"), "\n")
        self.assertFalse((self.library / "cases").exists())

    def test_unconfirmed_metadata_is_rejected(self):
        metadata = dict(self.metadata)
        metadata["confirmed"] = False

        with self.assertRaisesRegex(archive_case.ArchiveError, "confirmation"):
            archive_case.archive_case(metadata, self.image, self.root)

    def test_unknown_effect_tag_is_rejected(self):
        metadata = dict(self.metadata)
        metadata["effect_tags"] = ["sparkle-vortex"]

        with self.assertRaisesRegex(archive_case.ArchiveError, "effect tag"):
            archive_case.archive_case(metadata, self.image, self.root)

    def test_unknown_language_and_script_are_rejected(self):
        for key, value in (("language", "made-up-language"), ("script", "made-up-script")):
            with self.subTest(key=key):
                metadata = dict(self.metadata)
                metadata[key] = value
                with self.assertRaisesRegex(archive_case.ArchiveError, key):
                    archive_case.archive_case(metadata, self.image, self.root)

    def test_missing_reference_image_is_rejected(self):
        with self.assertRaisesRegex(archive_case.ArchiveError, "reference image"):
            archive_case.archive_case(
                self.metadata,
                self.image.with_name("missing.png"),
                self.root,
            )

    def test_duplicate_image_is_rejected_without_second_case_or_index_line(self):
        archive_case.archive_case(self.metadata, self.image, self.root, today=date(2026, 8, 28))

        with self.assertRaisesRegex(archive_case.ArchiveError, "duplicate"):
            archive_case.archive_case(self.metadata, self.image, self.root, today=date(2026, 8, 28))

        self.assertEqual(len(list((self.library / "cases").iterdir())), 1)
        self.assertEqual(
            len((self.library / "index.jsonl").read_text(encoding="utf-8").splitlines()),
            1,
        )

    def test_index_replace_failure_rolls_back_destination_case(self):
        real_replace = os.replace
        replace_calls = 0

        def replace_once_then_fail(source, destination):
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 1:
                return real_replace(source, destination)
            raise OSError("index swap failed")

        with mock.patch.object(
            archive_case.os,
            "replace",
            side_effect=replace_once_then_fail,
        ):
            with self.assertRaisesRegex(OSError, "index swap failed"):
                archive_case.archive_case(
                    self.metadata, self.image, self.root, today=date(2026, 8, 28)
                )

        self.assertFalse((self.library / "cases").exists())
        self.assertEqual((self.library / "index.jsonl").read_text(encoding="utf-8"), "\n")

    def test_concurrent_distinct_archives_keep_both_cases_and_records(self):
        second_image = Path(self.temporary_directory.name) / "second.png"
        second_image.write_bytes(b"second nonempty image")
        original_read_index = archive_case._read_index
        read_barrier = threading.Barrier(2)
        return_barrier = threading.Barrier(2)

        def synchronized_read_index(index_path):
            records = original_read_index(index_path)
            for barrier in (read_barrier, return_barrier):
                try:
                    barrier.wait(timeout=0.2)
                except threading.BrokenBarrierError:
                    pass
            return records

        results = []
        errors = []

        def archive(image):
            try:
                results.append(
                    archive_case.archive_case(
                        self.metadata, image, self.root, today=date(2026, 8, 28)
                    )
                )
            except BaseException as error:
                errors.append(error)

        with mock.patch.object(archive_case, "_read_index", synchronized_read_index):
            first = threading.Thread(target=archive, args=(self.image,))
            second = threading.Thread(target=archive, args=(second_image,))
            first.start()
            second.start()
            first.join(timeout=3)
            second.join(timeout=3)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(len(list((self.library / "cases").iterdir())), 2)
        self.assertEqual(
            len((self.library / "index.jsonl").read_text(encoding="utf-8").splitlines()),
            2,
        )

    def test_keyboard_interrupt_during_index_swap_rolls_back_destination(self):
        expected_case_id = "20260828-{}".format(
            hashlib.sha256(self.image_bytes).hexdigest()[:12]
        )
        original_index = (self.library / "index.jsonl").read_text(encoding="utf-8")
        real_replace = os.replace
        replace_calls = 0

        def replace_once_then_interrupt(source, destination):
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 1:
                return real_replace(source, destination)
            raise KeyboardInterrupt("simulated interruption")

        with mock.patch.object(
            archive_case.os, "replace", side_effect=replace_once_then_interrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                archive_case.archive_case(
                    self.metadata, self.image, self.root, today=date(2026, 8, 28)
                )

        self.assertFalse((self.library / "cases" / expected_case_id).exists())
        self.assertEqual((self.library / "index.jsonl").read_text(encoding="utf-8"), original_index)

    def test_next_archive_removes_marked_orphan_but_keeps_unmarked_case(self):
        cases_directory = self.library / "cases"
        orphan = cases_directory / "orphaned"
        orphan.mkdir(parents=True)
        (orphan / ".pending-index").write_text("pending\n", encoding="utf-8")
        unmarked = cases_directory / "keep-me"
        unmarked.mkdir()
        (unmarked / "note.txt").write_text("preserve", encoding="utf-8")

        archive_case.archive_case(self.metadata, self.image, self.root, today=date(2026, 8, 28))

        self.assertFalse(orphan.exists())
        self.assertTrue(unmarked.exists())

    def test_malformed_font_analysis_types_raise_archive_error(self):
        malformed = (
            ("confidence", []),
            ("candidates", ["rounded display sans", 7]),
            ("category", ["rounded display"]),
            ("evidence", {"not": "text"}),
            ("custom_modifications", 4),
        )
        for field, value in malformed:
            with self.subTest(field=field):
                metadata = dict(self.metadata)
                metadata["font_analysis"] = dict(self.metadata["font_analysis"])
                metadata["font_analysis"][field] = value
                with self.assertRaises(archive_case.ArchiveError):
                    archive_case.archive_case(metadata, self.image, self.root)

    def test_cli_success_prints_case_and_absolute_paths(self):
        metadata_path = Path(self.temporary_directory.name) / "metadata.json"
        metadata_path.write_text(json.dumps(self.metadata), encoding="utf-8")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            result = archive_case.main(
                [
                    "--metadata", str(metadata_path), "--image", str(self.image),
                    "--skill-root", str(self.root),
                ]
            )

        response = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertIn("case_id", response)
        self.assertTrue(Path(response["case_dir"]).is_absolute())
        self.assertTrue(Path(response["index_path"]).is_absolute())

    def test_cli_invalid_utf8_metadata_returns_standard_error(self):
        metadata_path = Path(self.temporary_directory.name) / "invalid.json"
        metadata_path.write_bytes(b"\xff")
        errors = io.StringIO()

        with contextlib.redirect_stderr(errors):
            result = archive_case.main(
                [
                    "--metadata", str(metadata_path), "--image", str(self.image),
                    "--skill-root", str(self.root),
                ]
            )

        self.assertEqual(result, 2)
        self.assertTrue(errors.getvalue().startswith("archive failed:"))


if __name__ == "__main__":
    unittest.main()
