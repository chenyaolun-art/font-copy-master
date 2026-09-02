import base64
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "font-effect-prompt-builder"
    / "scripts"
    / "build_preview.py"
)


def load_preview_module(test_case):
    if not MODULE_PATH.is_file():
        test_case.fail("build_preview.py is missing")
    spec = importlib.util.spec_from_file_location("build_preview", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreviewBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.library = Path(self.temporary_directory.name) / "library"
        self.case_id = "20260902-abc123def456"
        self.case_directory = self.library / "cases" / self.case_id
        self.case_directory.mkdir(parents=True)
        self.reference_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
            "AScY42YAAAAASUVORK5CYII="
        )
        (self.case_directory / "reference.png").write_bytes(self.reference_bytes)
        (self.case_directory / "case.md").write_text(
            """# Lettering case 20260902-abc123def456

- Date: 2026-09-02
- Reference: reference.png
- Language: traditional-chinese

## Copy

- Source: 萬頃琉璃
- Target: 百日同行

## Font analysis

- Candidates: —
- Category: 客製粗筆行楷毛筆展示字
- Confidence: high
- Evidence: 寬厚圓潤的主筆與長弧掃尾。
- Custom modifications: 字距緊密，末筆加長。

## Visual analysis

冰白色主體融入淡青紫漸變，表面平滑。

## Original prompt

ORIGINAL PROMPT

## Final prompt

FINAL PROMPT

## Classification notes

適用繁體中文。
""",
            encoding="utf-8",
        )
        record = {
            "case_id": self.case_id,
            "created_at": "2026-09-02",
            "reference": "cases/{}/reference.png".format(self.case_id),
            "source_text": "萬頃琉璃",
            "target_text": "百日同行",
            "language": "traditional-chinese",
            "script": "han",
            "font_confidence": "high",
            "style_tags": ["elegant", "handwritten"],
            "effect_tags": ["brush", "gradient", "shadow"],
        }
        self.record = record
        (self.library / "index.jsonl").write_text(
            json.dumps(record, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def test_load_cases_parses_copy_analysis_and_prompts(self):
        build_preview = load_preview_module(self)

        cases, warnings = build_preview.load_cases(self.library)

        self.assertEqual(warnings, [])
        self.assertEqual(len(cases), 1)
        case = cases[0]
        self.assertEqual(case["source_text"], "萬頃琉璃")
        self.assertEqual(case["target_text"], "百日同行")
        self.assertEqual(case["category"], "客製粗筆行楷毛筆展示字")
        self.assertEqual(case["evidence"], "寬厚圓潤的主筆與長弧掃尾。")
        self.assertEqual(case["final_prompt"], "FINAL PROMPT")
        self.assertTrue(case["image_url"].startswith("data:image/png;base64,"))

    def test_make_prompt_template_replaces_archived_target(self):
        build_preview = load_preview_module(self)
        prompt = (
            "製作孤立美術字，唯一目標是渲染精確文字"
            "「百日同行\n青丘再聚」。保留藍色筆觸。"
        )

        template = build_preview.make_prompt_template(
            prompt,
            target_text="百日同行\n青丘再聚",
            source_text="萬頃琉璃",
        )

        self.assertIn(build_preview.TARGET_TEXT_TOKEN, template)
        self.assertNotIn("百日同行", template)
        self.assertIn("保留藍色筆觸", template)

    def test_make_prompt_template_falls_back_to_quoted_prompt_text(self):
        build_preview = load_preview_module(self)

        template = build_preview.make_prompt_template(
            "渲染精確文字「舊文案」，保留平滑金屬效果。",
            target_text="未匹配文案",
            source_text="另一段文字",
        )

        self.assertIn(
            "渲染精確文字「{}」".format(build_preview.TARGET_TEXT_TOKEN),
            template,
        )
        self.assertNotIn("舊文案", template)

    def test_invalid_jsonl_raises_preview_error(self):
        build_preview = load_preview_module(self)
        (self.library / "index.jsonl").write_text("{broken\n", encoding="utf-8")

        with self.assertRaisesRegex(build_preview.PreviewError, "line 1"):
            build_preview.load_cases(self.library)

    def test_missing_case_files_are_skipped_with_warning(self):
        build_preview = load_preview_module(self)
        (self.case_directory / "reference.png").unlink()

        cases, warnings = build_preview.load_cases(self.library)

        self.assertEqual(cases, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn(self.case_id, warnings[0])

    def test_build_gallery_writes_offline_gallery(self):
        build_preview = load_preview_module(self)

        result = build_preview.build_gallery(self.library)
        html = Path(result["preview_path"]).read_text(encoding="utf-8")

        self.assertEqual(result["case_count"], 1)
        self.assertEqual(result["warnings"], [])
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("萬頃琉璃", html)
        self.assertIn("复制终版提示词", html)
        self.assertIn('id="search-input"', html)
        self.assertIn('id="case-grid"', html)
        self.assertIn('id="detail-dialog"', html)
        self.assertIn('id="target-copy-input"', html)
        self.assertIn('id="generate-prompt"', html)
        self.assertIn('id="generated-tab"', html)
        self.assertIn("function buildTargetPrompt", html)
        self.assertIn("本次文案排版覆盖", html)
        self.assertIn("navigator.clipboard", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

    def test_prompt_preview_expands_without_nested_scrolling(self):
        build_preview = load_preview_module(self)

        result = build_preview.build_gallery(self.library)
        html = Path(result["preview_path"]).read_text(encoding="utf-8")
        prompt_box_css = html.split("    .prompt-box {", 1)[1].split("    }", 1)[0]

        self.assertIn("max-height: none;", prompt_box_css)
        self.assertIn("overflow: visible;", prompt_box_css)
        self.assertNotIn("max-height: 310px;", prompt_box_css)
        self.assertNotIn("overflow: auto;", prompt_box_css)

    def test_generated_prompt_opens_a_full_height_focus_view(self):
        build_preview = load_preview_module(self)

        result = build_preview.build_gallery(self.library)
        html = Path(result["preview_path"]).read_text(encoding="utf-8")

        self.assertIn('id="expand-prompt"', html)
        self.assertIn("function setPromptFocus(enabled)", html)
        self.assertIn('dialog.classList.toggle("prompt-focus", enabled)', html)
        self.assertIn("setPromptFocus(true);", html)
        self.assertIn(".prompt-focus .prompt-box {", html)
        focus_css = html.split("    .prompt-focus .prompt-box {", 1)[1].split("    }", 1)[0]
        self.assertIn("height: 100%;", focus_css)
        self.assertIn("overflow: auto;", focus_css)

    def test_empty_library_renders_empty_state(self):
        build_preview = load_preview_module(self)
        (self.library / "index.jsonl").write_text("", encoding="utf-8")

        result = build_preview.build_gallery(self.library)
        html = Path(result["preview_path"]).read_text(encoding="utf-8")

        self.assertEqual(result["case_count"], 0)
        self.assertIn("还没有归档字体", html)

    def test_cli_prints_json_result(self):
        build_preview = load_preview_module(self)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            code = build_preview.main(["--library", str(self.library)])

        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["case_count"], 1)
        self.assertTrue(Path(result["preview_path"]).is_absolute())


if __name__ == "__main__":
    unittest.main()
