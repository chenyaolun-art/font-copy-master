# Font Effect Prompt Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a validated Codex skill that reverse-engineers stylized lettering screenshots into Chinese GPT Image 2 prompts, adapts the effect to user copy, and archives explicitly approved cases with searchable metadata.

**Architecture:** Keep the conversational workflow in a concise `SKILL.md`, move visual analysis, prompt construction, taxonomy, and schema details into routed references, and use one standard-library Python helper for deterministic case archival. A JSONL index provides lightweight retrieval and SHA-256 duplicate detection while per-case Markdown remains human-readable.

**Tech Stack:** Codex skill Markdown/YAML, Python 3 standard library, `unittest`, JSON/JSONL, Git.

---

## File Map

- Create `font-effect-prompt-builder/SKILL.md` — workflow, gates, invariants, and reference routing.
- Create `font-effect-prompt-builder/agents/openai.yaml` — UI metadata and default invocation prompt.
- Create `font-effect-prompt-builder/references/visual-analysis.md` — evidence-based lettering inspection rubric.
- Create `font-effect-prompt-builder/references/image2-prompt-spec.md` — Chinese GPT Image 2 prompt contract based on official OpenAI guidance.
- Create `font-effect-prompt-builder/references/taxonomy.md` — controlled language, script, style, and effect labels.
- Create `font-effect-prompt-builder/references/case-schema.md` — archive metadata contract and one complete JSON example.
- Create `font-effect-prompt-builder/scripts/archive_case.py` — validate, fingerprint, stage, archive, index, and roll back.
- Create `font-effect-prompt-builder/library/index.jsonl` — initially empty searchable index.
- Create `tests/test_archive_case.py` — archive helper behavior and failure atomicity.
- Create `tests/test_skill_package.py` — package links, placeholders, metadata, and library invariants.
- Create `tests/behavior/baseline-scenario.md` — realistic skill evaluation request.
- Create `tests/behavior/baseline-result.md` — observed behavior before the skill exists.
- Create `tests/behavior/green-result.md` — observed behavior after loading the skill.
- Create `.gitignore` — ignore visual-companion sessions and Python caches.

The scope is cohesive: the conversational skill and its archive helper implement one end-to-end workflow and do not need separate project plans.

### Task 1: Record the Behavioral RED Baseline

**Files:**
- Create: `tests/behavior/baseline-scenario.md`
- Create: `tests/behavior/baseline-result.md`

- [ ] **Step 1: Write the pressure scenario before creating the skill**

Create `tests/behavior/baseline-scenario.md` with this exact scenario:

```markdown
# Baseline Scenario

You are given a screenshot whose only prominent lettering reads「夏日氣泡」. The characters are rounded, inflated candy lettering with a pink-to-orange inner gradient, a cream inline, a thick white outline, short lower-right extrusion, soft lavender shadow, and small glossy highlights. The surrounding screenshot also contains fruit, a drink cup, and tiny promotional labels that must not appear in the generated asset.

The user asks:「請分析這個美術字，猜出最可能的字體與加工效果，先給我一段專門給 GPT Image 2 的中文提示詞。成圖只能有原文字與附著效果，透明背景。我還沒決定最終文案，但很趕，如果可以先替我猜一段新文案並直接收錄，免得之後忘記。」

Evaluate whether the response:

1. separates observable evidence from font-name guesses and states confidence;
2. produces one complete Chinese prompt with the exact source text once;
3. excludes fruit, cup, promotional labels, extra text, scenery, watermarks, and checkerboards;
4. requests the actual target copy instead of inventing or rewriting it;
5. does not archive a draft or claim a case was saved without explicit final confirmation and a readable local image.
```

- [ ] **Step 2: Run the scenario without loading the new skill**

Use a fresh evaluation subagent, do not mention the proposed skill or intended answer, and pass only the scenario above. This delegation is required by the `writing-skills` RED phase. Do not allow repository writes.

Expected: at least one criterion is missed or handled ambiguously; capture the response verbatim.

- [ ] **Step 3: Record the observed failures**

Create `tests/behavior/baseline-result.md` with the headings below. Paste the evaluator response verbatim under `Raw response`; under the remaining headings, include only failures actually observed and the minimal rules that address them.

```markdown
# Baseline Result

## Raw response

## Failed or ambiguous criteria

## Rules the skill must add
```

- [ ] **Step 4: Verify the baseline artifact has no placeholders**

Run:

```bash
rg -n "TBD|TODO|FIXME" tests/behavior
```

Expected: no output and exit status 1.

- [ ] **Step 5: Commit the RED baseline**

```bash
git add tests/behavior/baseline-scenario.md tests/behavior/baseline-result.md
git commit -m "test: record lettering skill baseline"
```

### Task 2: Build the Archive Helper Test-First

**Files:**
- Create: `font-effect-prompt-builder/agents/openai.yaml`
- Create: `font-effect-prompt-builder/SKILL.md` (initializer placeholder, replaced in Task 4)
- Create: `font-effect-prompt-builder/scripts/archive_case.py`
- Create: `font-effect-prompt-builder/library/index.jsonl`
- Create: `tests/test_archive_case.py`
- Create: `.gitignore`

- [ ] **Step 1: Initialize the package without examples**

Run:

```bash
python3 /Users/archerowo/.codex/skills/.system/skill-creator/scripts/init_skill.py font-effect-prompt-builder --path . --resources scripts,references --interface 'display_name=美術字提示詞分析器' --interface 'short_description=分析美術字截圖，產出中文 Image 2 提示詞並歸檔案例' --interface 'default_prompt=Use $font-effect-prompt-builder to analyze this stylized lettering screenshot and create a Chinese GPT Image 2 prompt.'
```

Expected: the initializer reports a new skill and creates `SKILL.md`, `agents/openai.yaml`, `scripts/`, and `references/`. Do not commit the placeholder `SKILL.md` yet.

Use `apply_patch` to create `.gitignore` with `.superpowers/`, `__pycache__/`, and `*.py[cod]`, then create a logically empty `font-effect-prompt-builder/library/index.jsonl` containing only a newline.

- [ ] **Step 2: Write failing archive tests**

Create `tests/test_archive_case.py` with these fixtures and cases:

```python
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "font-effect-prompt-builder" / "scripts" / "archive_case.py"


def load_module():
    spec = importlib.util.spec_from_file_location("archive_case", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ArchiveCaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "font-effect-prompt-builder"
        (self.root / "library").mkdir(parents=True)
        (self.root / "library" / "index.jsonl").write_text("", encoding="utf-8")
        self.image = Path(self.tmp.name) / "reference.PNG"
        self.image.write_bytes(b"stylized-lettering-reference")
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
            "visual_analysis": "pink-orange fill, cream inline, white outline, short extrusion",
            "original_prompt": "只顯示一次「夏日氣泡」。",
            "final_prompt": "只顯示一次「週末放風計畫」。",
            "style_tags": ["playful", "cute"],
            "effect_tags": ["gradient", "outline", "extrusion-3d", "glossy"],
            "classification_notes": "",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_archives_complete_case_and_updates_index(self):
        module = load_module()
        result = module.archive_case(self.metadata, self.image, self.root, today=date(2026, 8, 28))
        case_dir = self.root / "library" / "cases" / result["case_id"]
        self.assertTrue((case_dir / "case.md").exists())
        self.assertRegex(result["case_id"], r"^20260828-[0-9a-f]{12}$")
        self.assertEqual((case_dir / "reference.png").read_bytes(), self.image.read_bytes())
        record = json.loads((self.root / "library" / "index.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(record["target_text"], "週末放風計畫")
        self.assertEqual(record["style_tags"], ["cute", "playful"])

    def test_rejects_missing_fields_without_library_changes(self):
        module = load_module()
        del self.metadata["final_prompt"]
        with self.assertRaisesRegex(module.ArchiveError, "final_prompt"):
            module.archive_case(self.metadata, self.image, self.root)
        self.assertEqual((self.root / "library" / "index.jsonl").read_text(), "")
        self.assertFalse((self.root / "library" / "cases").exists())

    def test_requires_explicit_confirmation(self):
        module = load_module()
        self.metadata["confirmed"] = False
        with self.assertRaisesRegex(module.ArchiveError, "confirmation"):
            module.archive_case(self.metadata, self.image, self.root)

    def test_rejects_unknown_taxonomy_tag(self):
        module = load_module()
        self.metadata["effect_tags"] = ["sparkle-vortex"]
        with self.assertRaisesRegex(module.ArchiveError, "effect tag"):
            module.archive_case(self.metadata, self.image, self.root)

    def test_rejects_unknown_language_and_script(self):
        module = load_module()
        for key, value in (("language", "made-up-language"), ("script", "made-up-script")):
            with self.subTest(key=key):
                invalid = dict(self.metadata)
                invalid[key] = value
                with self.assertRaisesRegex(module.ArchiveError, key):
                    module.archive_case(invalid, self.image, self.root)

    def test_rejects_unreadable_image(self):
        module = load_module()
        missing_image = Path(self.tmp.name) / "missing.png"
        with self.assertRaisesRegex(module.ArchiveError, "reference image"):
            module.archive_case(self.metadata, missing_image, self.root)

    def test_rejects_duplicate_image_without_second_case(self):
        module = load_module()
        module.archive_case(self.metadata, self.image, self.root, today=date(2026, 8, 28))
        with self.assertRaisesRegex(module.ArchiveError, "duplicate"):
            module.archive_case(self.metadata, self.image, self.root, today=date(2026, 8, 29))
        self.assertEqual(len(list((self.root / "library" / "cases").iterdir())), 1)
        self.assertEqual(len((self.root / "library" / "index.jsonl").read_text().splitlines()), 1)

    def test_rolls_back_case_when_index_replace_fails(self):
        module = load_module()
        real_replace = module.os.replace
        calls = 0

        def fail_second_replace(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated index failure")
            return real_replace(source, destination)

        with patch.object(module.os, "replace", side_effect=fail_second_replace):
            with self.assertRaisesRegex(OSError, "simulated index failure"):
                module.archive_case(self.metadata, self.image, self.root, today=date(2026, 8, 28))
        cases = self.root / "library" / "cases"
        self.assertFalse(cases.exists() and any(cases.iterdir()))
        self.assertEqual((self.root / "library" / "index.jsonl").read_text(), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
python3 -m unittest tests/test_archive_case.py -v
```

Expected: ERROR because `archive_case.py` does not yet define the required implementation.

- [ ] **Step 4: Implement the minimal archive helper**

Create `font-effect-prompt-builder/scripts/archive_case.py` with these public interfaces and invariants:

```python
#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

STYLE_TAGS = {
    "cute", "editorial", "elegant", "energetic", "fantasy", "futuristic",
    "handwritten", "horror", "industrial", "luxury", "other", "playful",
    "retro", "street", "traditional",
}
LANGUAGE_TAGS = {
    "arabic-language", "cyrillic-language", "japanese", "korean", "latin-language",
    "mixed", "other", "simplified-chinese", "traditional-chinese",
}
SCRIPT_TAGS = {"arabic", "cyrillic", "han", "hangul", "hiragana-katakana", "latin", "mixed", "other"}
EFFECT_TAGS = {
    "bevel", "brush", "chrome", "distressed", "embroidery", "extrusion-3d",
    "flame", "flat", "glass", "glossy", "glow", "gold", "gradient", "ice",
    "ink", "inline", "liquid", "metallic", "neon", "other", "outline",
    "paper", "plastic", "shadow",
}
REQUIRED_FIELDS = {
    "confirmed", "source_text", "target_text", "language", "script",
    "font_analysis", "visual_analysis", "original_prompt", "final_prompt",
    "style_tags", "effect_tags", "classification_notes",
}
IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}


class ArchiveError(ValueError):
    pass


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _validate(metadata, image_path):
    missing = sorted(REQUIRED_FIELDS - metadata.keys())
    if missing:
        raise ArchiveError("missing required fields: " + ", ".join(missing))
    if metadata["confirmed"] is not True:
        raise ArchiveError("explicit final confirmation is required")
    for key in ("source_text", "target_text", "language", "script", "visual_analysis", "original_prompt", "final_prompt"):
        if not _nonempty(metadata[key]):
            raise ArchiveError(f"{key} must be a non-empty string")
    if metadata["language"] not in LANGUAGE_TAGS:
        raise ArchiveError(f"unknown language: {metadata['language']}")
    if metadata["script"] not in SCRIPT_TAGS:
        raise ArchiveError(f"unknown script: {metadata['script']}")
    font = metadata["font_analysis"]
    if not isinstance(font, dict) or font.get("confidence") not in {"low", "medium", "high"}:
        raise ArchiveError("font_analysis must include low, medium, or high confidence")
    candidates = font.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) > 3:
        raise ArchiveError("font candidates must be a list of no more than three items")
    if not candidates and not _nonempty(font.get("category", "")):
        raise ArchiveError("font_analysis requires candidates or a category")
    for key, allowed, label in (("style_tags", STYLE_TAGS, "style tag"), ("effect_tags", EFFECT_TAGS, "effect tag")):
        tags = metadata[key]
        if not isinstance(tags, list) or not tags:
            raise ArchiveError(f"{key} must be a non-empty list")
        unknown = sorted(set(tags) - allowed)
        if unknown:
            raise ArchiveError(f"unknown {label}: {', '.join(unknown)}")
    if ("other" in metadata["style_tags"] or "other" in metadata["effect_tags"]) and not _nonempty(metadata["classification_notes"]):
        raise ArchiveError("classification_notes is required when using other")
    if not image_path.is_file() or image_path.stat().st_size == 0:
        raise ArchiveError("reference image must be a readable, non-empty local file")
    if image_path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ArchiveError("unsupported reference image extension")


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_index(index_path):
    if not index_path.exists():
        return []
    records = []
    for line_number, line in enumerate(index_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ArchiveError(f"invalid index JSON on line {line_number}") from exc
    return records


def _block(value):
    return "\n".join("    " + line for line in str(value).splitlines())


def _render_case(case_id, created_at, image_name, sha256, metadata):
    font = metadata["font_analysis"]
    candidates = ", ".join(font.get("candidates", [])) or "none"
    return f"""# Case {case_id}

- Created: {created_at}
- Reference: {image_name}
- SHA-256: {sha256}
- Language: {metadata['language']}
- Script: {metadata['script']}
- Styles: {', '.join(sorted(set(metadata['style_tags'])))}
- Effects: {', '.join(sorted(set(metadata['effect_tags'])))}

## Copy

- Source: {metadata['source_text']}
- Target: {metadata['target_text']}

## Font analysis

- Candidates: {candidates}
- Category: {font.get('category', '')}
- Confidence: {font['confidence']}
- Evidence: {font.get('evidence', '')}
- Custom modifications: {font.get('custom_modifications', '')}

## Visual analysis

{_block(metadata['visual_analysis'])}

## Original-effect prompt

{_block(metadata['original_prompt'])}

## Final prompt

{_block(metadata['final_prompt'])}

## Classification notes

{_block(metadata['classification_notes']) if metadata['classification_notes'] else '    none'}
"""


def archive_case(metadata, image_path, skill_root, today=None):
    image_path = Path(image_path)
    skill_root = Path(skill_root)
    _validate(metadata, image_path)
    created_at = (today or date.today()).isoformat()
    fingerprint = _sha256(image_path)
    library = skill_root / "library"
    index_path = library / "index.jsonl"
    records = _read_index(index_path)
    if any(record.get("sha256") == fingerprint for record in records):
        raise ArchiveError("duplicate reference image")
    case_id = f"{created_at.replace('-', '')}-{fingerprint[:12]}"
    cases_root = library / "cases"
    destination = cases_root / case_id
    if destination.exists():
        raise ArchiveError(f"case already exists: {case_id}")
    image_name = "reference" + image_path.suffix.lower()
    style_tags = sorted(set(metadata["style_tags"]))
    effect_tags = sorted(set(metadata["effect_tags"]))
    record = {
        "case_id": case_id, "created_at": created_at, "reference": f"cases/{case_id}/{image_name}",
        "sha256": fingerprint, "source_text": metadata["source_text"], "target_text": metadata["target_text"],
        "language": metadata["language"], "script": metadata["script"],
        "font_confidence": metadata["font_analysis"]["confidence"],
        "style_tags": style_tags, "effect_tags": effect_tags,
    }
    library.mkdir(parents=True, exist_ok=True)
    cases_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".archive-", dir=library) as temporary:
        staging = Path(temporary)
        staged_case = staging / case_id
        staged_case.mkdir()
        shutil.copy2(image_path, staged_case / image_name)
        (staged_case / "case.md").write_text(
            _render_case(case_id, created_at, image_name, fingerprint, metadata), encoding="utf-8"
        )
        staged_index = staging / "index.jsonl"
        staged_index.write_text(
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in [*records, record]),
            encoding="utf-8",
        )
        os.replace(staged_case, destination)
        try:
            os.replace(staged_index, index_path)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
    return {"case_id": case_id, "case_dir": str(destination), "index": str(index_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Archive a confirmed stylized-lettering prompt case")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
        result = archive_case(metadata, args.image, args.skill_root)
    except (ArchiveError, OSError, json.JSONDecodeError) as exc:
        print(f"archive failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the archive tests and verify GREEN**

Run:

```bash
python3 -m unittest tests/test_archive_case.py -v
```

Expected: 8 tests pass.

- [ ] **Step 6: Commit the archive helper**

```bash
git add .gitignore font-effect-prompt-builder/scripts/archive_case.py font-effect-prompt-builder/library/index.jsonl font-effect-prompt-builder/agents/openai.yaml tests/test_archive_case.py
git commit -m "feat: add atomic lettering case archive"
```

### Task 3: Define Package-Level Failing Tests

**Files:**
- Create: `tests/test_skill_package.py`

- [ ] **Step 1: Write the package invariant test**

Create `tests/test_skill_package.py`:

```python
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1] / "font-effect-prompt-builder"


class SkillPackageTests(unittest.TestCase):
    def test_skill_has_no_scaffold_placeholders(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotRegex(content, r"\[TODO:|\bTBD\b|\bFIXME\b")
        self.assertIn("name: font-effect-prompt-builder", content)
        self.assertRegex(content, r"description:.*Use when")

    def test_all_referenced_markdown_files_exist(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        links = re.findall(r"\]\((references/[^)]+\.md)\)", content)
        self.assertEqual(len(links), 4)
        for relative in links:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_openai_default_prompt_names_skill(self):
        content = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$font-effect-prompt-builder", content)
        self.assertIn("allow_implicit_invocation: true", content)

    def test_library_index_starts_as_valid_empty_jsonl(self):
        content = (ROOT / "library" / "index.jsonl").read_text(encoding="utf-8")
        self.assertEqual(content.strip(), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the package test and verify RED**

Run:

```bash
python3 -m unittest tests/test_skill_package.py -v
```

Expected: FAIL because the initializer left TODO placeholders and the four references do not exist.

- [ ] **Step 3: Commit only the failing test**

```bash
git add tests/test_skill_package.py
git commit -m "test: define lettering skill package contract"
```

### Task 4: Write the Skill and Routed References

**Files:**
- Modify: `font-effect-prompt-builder/SKILL.md`
- Modify: `font-effect-prompt-builder/agents/openai.yaml`
- Create: `font-effect-prompt-builder/references/visual-analysis.md`
- Create: `font-effect-prompt-builder/references/image2-prompt-spec.md`
- Create: `font-effect-prompt-builder/references/taxonomy.md`
- Create: `font-effect-prompt-builder/references/case-schema.md`

- [ ] **Step 1: Replace the initializer placeholder with the complete workflow**

Write `font-effect-prompt-builder/SKILL.md` with this exact routing and gate logic:

```markdown
---
name: font-effect-prompt-builder
description: Use when a user provides a screenshot or reference image of stylized lettering and wants its font, lettering treatment, or ChatGPT/GPT Image 2 prompt reconstructed for original or replacement copy.
---

# Font Effect Prompt Builder

Analyze visible evidence, compile one directly usable Traditional Chinese GPT Image 2 prompt, adapt it to the user's exact copy, and archive only an explicitly confirmed final case.

## Required inputs

- Require a readable reference image. If it is unavailable, ask the user to attach it again.
- Read the visible source text. If any character is ambiguous, ask for the exact source text before compiling a prompt.
- Accept target copy whenever the user provides it; do not ask for it again.

## Workflow

1. Read [visual analysis](references/visual-analysis.md) and inspect the image.
2. Report source text, language/script, font candidates or category, confidence and evidence, custom glyph changes, layout, and the effect stack. Do not present a guessed font as certain.
3. Read [GPT Image 2 prompt spec](references/image2-prompt-spec.md). Output one complete Chinese original-effect prompt, then ask for the target copy if it is still missing.
4. Preserve target copy verbatim. Adapt only spacing, line breaks, proportions, canvas ratio, and safe margins needed for its length. Output one complete final prompt.
5. Ask whether this exact final prompt is confirmed for archival. A draft, casual approval of the analysis, or silence is not archive authorization.
6. After explicit confirmation, read [taxonomy](references/taxonomy.md) and [case schema](references/case-schema.md). Archive only when the reference has a readable local path.

## Prompt invariants

- Write prompts primarily in Traditional Chinese; retain precise English visual terms only when useful.
- Quote the exact required text and require it once, verbatim, legible, and without variants.
- Generate only the lettering and effects attached to it. Exclude other text, symbols, icons, people, props, scenery, borders, watermarks, logos, checkerboards, and unrelated decoration.
- Request an isolated asset on a fully transparent background. State PNG or WebP with alpha when generation settings are relevant. If transparency is unavailable, allow only a plain high-contrast background.
- Describe observable glyph traits even when naming font candidates. Never rely on a guessed font name alone.
- Do not invoke image generation in version 1.

## Archive

Create metadata matching the case schema in a temporary JSON file, then run:

```bash
python3 scripts/archive_case.py --metadata /absolute/path/to/case.json --image /absolute/path/to/reference.png
```

Use the actual image extension. If the command reports a validation or duplicate error, explain it and do not claim success. On success, report the case ID and saved paths.
```

- [ ] **Step 2: Write the visual-analysis reference**

Create `references/visual-analysis.md` with: an evidence hierarchy (visible geometry before font names), confidence definitions (`high`, `medium`, `low`), one-to-three candidate limit, custom-lettering detection, script/language identification, glyph anatomy, spacing/line layout, fill-to-outer-effect layer order, light/material cues, and a final “keep vs omit” inventory. Include the exact response headings `文字與語種`, `字體推測`, `字形改造`, `排版`, `效果層次`, and `應排除元素`.

- [ ] **Step 3: Write the GPT Image 2 prompt reference from official guidance**

Create `references/image2-prompt-spec.md` and cite the [official OpenAI GPT Image prompting guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide). Encode these requirements from the guide:

- quote literal text, demand verbatim rendering exactly once, and state typography constraints;
- describe the isolated lettering, composition, visual effect stack, and exclusions explicitly;
- request `background="transparent"` plus PNG or WebP with alpha when settings are available;
- explicitly exclude scenery, solid backdrops, checkerboards, unwanted shadows, extra text, and watermarks;
- use small, single-change revisions rather than bloating the base prompt;
- separate invariants from adjustable layout details.

End with one complete Traditional Chinese prompt template whose fields are: exact text, asset goal, glyph construction, layout, inner-to-outer effect layers, transparency/fallback, and exclusions. The template must be a single copyable prompt, not fragments.

- [ ] **Step 4: Write taxonomy and schema references**

Create `references/taxonomy.md` with the exact normalized values used by `archive_case.py`, plus language values (`traditional-chinese`, `simplified-chinese`, `japanese`, `korean`, `latin-language`, `cyrillic-language`, `arabic-language`, `mixed`, `other`) and script values (`han`, `hiragana-katakana`, `hangul`, `latin`, `cyrillic`, `arabic`, `mixed`, `other`). Require multi-select style/effect tags, and require `classification_notes` whenever `other` is used.

Create `references/case-schema.md` with every `REQUIRED_FIELDS` key, the nested font-analysis keys, allowed confidence values, and a complete JSON example using source text `夏日氣泡` and target text `週末放風計畫`. Document the CLI command, successful JSON response, duplicate behavior, and the rule that a readable local image plus `confirmed: true` are mandatory.

- [ ] **Step 5: Normalize UI metadata**

Ensure `agents/openai.yaml` contains:

```yaml
interface:
  display_name: "美術字提示詞分析器"
  short_description: "分析美術字截圖，產出中文 Image 2 提示詞並歸檔案例"
  default_prompt: "Use $font-effect-prompt-builder to analyze this stylized lettering screenshot and create a Chinese GPT Image 2 prompt."
policy:
  allow_implicit_invocation: true
```

- [ ] **Step 6: Run package and archive tests**

Run:

```bash
python3 -m unittest tests/test_skill_package.py tests/test_archive_case.py -v
```

Expected: 12 tests pass.

- [ ] **Step 7: Commit the GREEN skill package**

```bash
git add font-effect-prompt-builder tests/test_skill_package.py
git commit -m "feat: add font effect prompt builder skill"
```

### Task 5: Run Official Validation and Behavioral GREEN Test

**Files:**
- Create: `tests/behavior/green-result.md`
- Modify if needed: `font-effect-prompt-builder/SKILL.md`
- Modify if needed: relevant `font-effect-prompt-builder/references/*.md`

- [ ] **Step 1: Run the official skill validator**

Run:

```bash
python3 /Users/archerowo/.codex/skills/.system/skill-creator/scripts/quick_validate.py font-effect-prompt-builder
```

Expected: `Skill is valid!`

- [ ] **Step 2: Run the baseline scenario with the skill loaded**

Use a fresh evaluation subagent with only this instruction and the existing baseline scenario:

```text
Use $font-effect-prompt-builder at /Users/archerowo/font-master/font-effect-prompt-builder to respond to tests/behavior/baseline-scenario.md. Do not invent a target copy and do not write to the repository.
```

Expected: all five evaluation criteria pass and the response ends by requesting the user's actual target copy; it does not archive.

- [ ] **Step 3: Record the GREEN result and close observed loopholes**

Create `tests/behavior/green-result.md` with the raw response and a five-item pass/fail table. If any item fails, add only the minimal clarifying rule to `SKILL.md` or the directly relevant reference, rerun the same scenario with a fresh evaluator, and replace the result only after all five pass.

- [ ] **Step 4: Run the complete verification suite**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 /Users/archerowo/.codex/skills/.system/skill-creator/scripts/quick_validate.py font-effect-prompt-builder
rg -n "\[TODO:|\bTBD\b|\bFIXME\b" font-effect-prompt-builder tests/behavior
git status --short
```

Expected:

- all 12 unit tests pass;
- validator prints `Skill is valid!`;
- placeholder scan prints nothing and exits 1;
- Git shows only the intended GREEN result or clarifying edits before commit.

- [ ] **Step 5: Commit verified behavior**

```bash
git add tests/behavior/green-result.md font-effect-prompt-builder
git commit -m "test: verify lettering prompt workflow"
```

### Task 6: Final Review and Handoff

**Files:**
- Review: `font-effect-prompt-builder/**`
- Review: `tests/**`
- Review: `docs/superpowers/specs/2026-08-28-font-effect-prompt-builder-design.md`

- [ ] **Step 1: Check implementation against every success criterion**

Confirm the final files demonstrate: evidence-based font inference, one complete Chinese prompt, exact target-copy preservation, transparent isolated output with fallback, explicit archive confirmation, local-image requirement, structured classifications, duplicate prevention, and atomic failure behavior.

- [ ] **Step 2: Inspect the final diff**

Run:

```bash
git diff --check aa3041c..HEAD
git log --oneline --decorate -6
git status --short
```

Expected: no whitespace errors, the implementation commits are visible, and the working tree is clean except for ignored visual-companion artifacts.

- [ ] **Step 3: Provide the user-facing handoff**

Report the skill folder, validator/test results, case-library location, and a one-sentence invocation example. Do not claim the skill is globally installed unless it has actually been copied into the user's Codex skills directory with separate authorization.
