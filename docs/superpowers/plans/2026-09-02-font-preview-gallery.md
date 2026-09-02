# Local Font Preview Gallery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained local HTML gallery for browsing, filtering, inspecting, and copying prompts from archived lettering cases.

**Architecture:** A dependency-free Python generator reads `library/index.jsonl`, parses each `case.md`, embeds reference images as data URLs, and writes `library/preview.html`. The browser page contains no network requests and performs search, filtering, sorting, modal display, and clipboard actions entirely in client-side JavaScript.

**Tech Stack:** Python 3 standard library, HTML5, CSS, vanilla JavaScript, `unittest`.

---

## File Structure

- Create `font-effect-prompt-builder/scripts/build_preview.py`: parse archive records and generate a self-contained HTML gallery.
- Create `tests/test_build_preview.py`: validate parsing, embedding, errors, missing-case degradation, CLI output, and offline markup.
- Modify `font-effect-prompt-builder/SKILL.md`: rebuild the preview page after successful archive creation.
- Modify `font-effect-prompt-builder/references/case-schema.md`: document the preview build command and result.
- Generate `/Users/archerowo/.codex/skills/font-effect-prompt-builder/library/preview.html`: installed local gallery containing all current cases.

### Task 1: Case loading and Markdown parsing

**Files:**
- Create: `tests/test_build_preview.py`
- Create: `font-effect-prompt-builder/scripts/build_preview.py`

- [ ] **Step 1: Write failing parser and loader tests**

```python
class PreviewBuilderTests(unittest.TestCase):
    def test_load_cases_parses_copy_analysis_and_prompts(self):
        cases, warnings = build_preview.load_cases(self.library)
        self.assertEqual(warnings, [])
        self.assertEqual(cases[0]["source_text"], "萬頃琉璃")
        self.assertEqual(cases[0]["category"], "客製粗筆行楷毛筆展示字")
        self.assertEqual(cases[0]["final_prompt"], "FINAL PROMPT")
        self.assertTrue(cases[0]["image_url"].startswith("data:image/png;base64,"))

    def test_invalid_jsonl_raises_preview_error(self):
        (self.library / "index.jsonl").write_text("{broken\n", encoding="utf-8")
        with self.assertRaisesRegex(build_preview.PreviewError, "line 1"):
            build_preview.load_cases(self.library)

    def test_missing_case_files_are_skipped_with_warning(self):
        (self.library / "cases" / self.case_id / "reference.png").unlink()
        cases, warnings = build_preview.load_cases(self.library)
        self.assertEqual(cases, [])
        self.assertIn(self.case_id, warnings[0])
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m unittest tests.test_build_preview.PreviewBuilderTests.test_load_cases_parses_copy_analysis_and_prompts -v`

Expected: FAIL because `build_preview.py` does not exist.

- [ ] **Step 3: Implement the parser and loader**

```python
class PreviewError(Exception):
    pass


def parse_case_markdown(raw):
    sections = {}
    current = None
    for line in raw.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    def body(name):
        return "\n".join(sections.get(name, [])).strip()

    def bullet_map(name):
        result = {}
        for line in sections.get(name, []):
            if line.startswith("- ") and ": " in line:
                key, value = line[2:].split(": ", 1)
                result[key] = value
        return result

    copy = bullet_map("Copy")
    analysis = bullet_map("Font analysis")
    return {
        "source_text": copy.get("Source", ""),
        "target_text": copy.get("Target", ""),
        "category": analysis.get("Category", ""),
        "evidence": analysis.get("Evidence", ""),
        "custom_modifications": analysis.get("Custom modifications", ""),
        "visual_analysis": body("Visual analysis"),
        "original_prompt": body("Original prompt"),
        "final_prompt": body("Final prompt"),
    }


def load_cases(library):
    library = Path(library)
    index_path = library / "index.jsonl"
    if not index_path.is_file():
        raise PreviewError("index.jsonl is missing")
    records = []
    for number, line in enumerate(index_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise PreviewError("invalid index JSON at line {}".format(number)) from error
    cases, warnings = [], []
    for record in records:
        case_id = record.get("case_id", "unknown")
        case_dir = library / "cases" / case_id
        case_md = case_dir / "case.md"
        image_path = library / record.get("reference", "")
        if not case_md.is_file() or not image_path.is_file():
            warnings.append("{}: missing case.md or reference image".format(case_id))
            continue
        parsed = parse_case_markdown(case_md.read_text(encoding="utf-8"))
        mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        parsed.update(record)
        parsed["image_url"] = "data:{};base64,{}".format(
            mime, base64.b64encode(image_path.read_bytes()).decode("ascii")
        )
        cases.append(parsed)
    return cases, warnings
```

- [ ] **Step 4: Run parser and loader tests**

Run: `python3 -m unittest tests.test_build_preview -v`

Expected: parser and loader tests PASS.

- [ ] **Step 5: Commit the parser**

```bash
git add tests/test_build_preview.py font-effect-prompt-builder/scripts/build_preview.py
git commit -m "feat: load lettering cases for preview"
```

### Task 2: Self-contained gallery rendering

**Files:**
- Modify: `tests/test_build_preview.py`
- Modify: `font-effect-prompt-builder/scripts/build_preview.py`

- [ ] **Step 1: Write failing HTML and CLI tests**

```python
def test_build_preview_writes_offline_gallery(self):
    result = build_preview.build_gallery(self.library)
    html = Path(result["output_path"]).read_text(encoding="utf-8")
    self.assertEqual(result["case_count"], 1)
    self.assertIn("data:image/png;base64,", html)
    self.assertIn("萬頃琉璃", html)
    self.assertIn("复制终版提示词", html)
    self.assertIn('id="search-input"', html)
    self.assertNotIn("https://", html)
    self.assertNotIn("http://", html)

def test_cli_prints_json_result(self):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = build_preview.main(["--library", str(self.library)])
    self.assertEqual(code, 0)
    self.assertEqual(json.loads(output.getvalue())["case_count"], 1)
```

- [ ] **Step 2: Run the rendering tests and verify RED**

Run: `python3 -m unittest tests.test_build_preview.PreviewBuilderTests.test_build_preview_writes_offline_gallery -v`

Expected: FAIL because `build_gallery` is not implemented.

- [ ] **Step 3: Implement atomic HTML generation**

```python
def build_gallery(library, output_path=None):
    library = Path(library).resolve()
    cases, warnings = load_cases(library)
    output = Path(output_path).resolve() if output_path else library / "preview.html"
    payload = json.dumps(cases, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__CASE_DATA__", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(output.parent), delete=False
    ) as temporary:
        temporary.write(html)
        temporary_path = Path(temporary.name)
    os.replace(str(temporary_path), str(output))
    return {
        "output_path": str(output),
        "case_count": len(cases),
        "warnings": warnings,
    }
```

The `HTML_TEMPLATE` must contain:

- A sticky header with title, case count, search, newest/oldest sorting, and clear filters.
- Language, style, and effect filter controls derived from case data.
- A responsive image-first card grid with source text, target text, and tags.
- A keyboard-accessible detail dialog with large preview image, analysis, case ID, and both prompts.
- Clipboard buttons using `navigator.clipboard.writeText`, with a textarea selection fallback.
- Empty, loading, and missing-field states.
- CSS focus indicators, readable contrast, `prefers-reduced-motion`, and one-column narrow-screen layout.
- No external URLs, fonts, scripts, stylesheets, or network calls.

- [ ] **Step 4: Run all preview tests**

Run: `python3 -m unittest tests.test_build_preview -v`

Expected: all preview tests PASS.

- [ ] **Step 5: Commit the gallery renderer**

```bash
git add tests/test_build_preview.py font-effect-prompt-builder/scripts/build_preview.py
git commit -m "feat: generate offline font preview gallery"
```

### Task 3: Archive workflow integration

**Files:**
- Modify: `font-effect-prompt-builder/SKILL.md`
- Modify: `font-effect-prompt-builder/references/case-schema.md`

- [ ] **Step 1: Document the post-archive build command**

Add this required follow-up after a successful `archive_case.py` call:

```text
python3 /absolute/path/font-effect-prompt-builder/scripts/build_preview.py \
  --library /absolute/path/font-effect-prompt-builder/library
```

Report `preview_path` and `case_count`. A preview failure does not undo a committed archive; report the warning and preserve the archive success.

- [ ] **Step 2: Validate the Skill package and documentation**

Run: `python3 /Users/archerowo/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/archerowo/font-master/font-effect-prompt-builder`

Expected: `Skill is valid!` when the validator dependency is available. If local PyYAML remains unavailable, run YAML frontmatter validation with Ruby and report the validator limitation.

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 3: Commit workflow documentation**

```bash
git add font-effect-prompt-builder/SKILL.md font-effect-prompt-builder/references/case-schema.md
git commit -m "docs: rebuild preview after case archive"
```

### Task 4: Install, generate, and verify the current gallery

**Files:**
- Copy: `font-effect-prompt-builder/scripts/build_preview.py` to the installed Skill.
- Copy: updated `SKILL.md` and `references/case-schema.md` to the installed Skill.
- Generate: `/Users/archerowo/.codex/skills/font-effect-prompt-builder/library/preview.html`

- [ ] **Step 1: Run the full automated test suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: all archive and preview tests PASS with zero failures.

- [ ] **Step 2: Sync implementation files to the installed Skill**

```bash
cp font-effect-prompt-builder/scripts/build_preview.py /Users/archerowo/.codex/skills/font-effect-prompt-builder/scripts/build_preview.py
cp font-effect-prompt-builder/SKILL.md /Users/archerowo/.codex/skills/font-effect-prompt-builder/SKILL.md
cp font-effect-prompt-builder/references/case-schema.md /Users/archerowo/.codex/skills/font-effect-prompt-builder/references/case-schema.md
```

- [ ] **Step 3: Generate the installed preview**

Run: `python3 /Users/archerowo/.codex/skills/font-effect-prompt-builder/scripts/build_preview.py --library /Users/archerowo/.codex/skills/font-effect-prompt-builder/library`

Expected: JSON with `case_count: 4`, an empty warning list, and an absolute `preview_path`.

- [ ] **Step 4: Verify offline behavior and indexed-case coverage**

Check that the generated HTML:

- Contains each case ID from the installed `index.jsonl`.
- Contains four embedded `data:image/` URLs.
- Contains no external `http://` or `https://` resources.
- Opens through `file://` with visible cards, working filters, detail dialog, and copy feedback.

- [ ] **Step 5: Open the gallery in Codex**

Open `/Users/archerowo/.codex/skills/font-effect-prompt-builder/library/preview.html` in a browser panel so the user can use it immediately.
