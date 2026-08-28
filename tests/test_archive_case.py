import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
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
        self.image = Path(self.temporary_directory.name) / "reference.PNG"
        self.image_bytes = b"not-a-real-png-but-nonempty"
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
        case_id = archive_case.archive_case(
            self.metadata, self.image, self.root, today=date(2026, 8, 28)
        )

        self.assertRegex(case_id, r"^20260828-[0-9a-f]{12}$")
        case_directory = self.library / "cases" / case_id
        self.assertTrue((case_directory / "case.md").is_file())
        self.assertEqual(
            (case_directory / "reference.png").read_bytes(), self.image_bytes
        )
        index_lines = (self.library / "index.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(index_lines), 1)
        record = json.loads(index_lines[0])
        self.assertEqual(record["case_id"], case_id)
        self.assertEqual(record["source_text"], "夏日氣泡")
        self.assertEqual(record["target_text"], "週末放風計畫")
        self.assertEqual(record["style_tags"], ["cute", "playful"])

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
        with mock.patch.object(
            archive_case.os,
            "replace",
            side_effect=[real_replace, OSError("index swap failed")],
        ):
            with self.assertRaisesRegex(OSError, "index swap failed"):
                archive_case.archive_case(
                    self.metadata, self.image, self.root, today=date(2026, 8, 28)
                )

        self.assertFalse((self.library / "cases").exists())
        self.assertEqual((self.library / "index.jsonl").read_text(encoding="utf-8"), "\n")


if __name__ == "__main__":
    unittest.main()
