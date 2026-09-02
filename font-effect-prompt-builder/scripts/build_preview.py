"""Build a self-contained local gallery for archived lettering cases."""

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import tempfile
from pathlib import Path


TARGET_TEXT_TOKEN = "__FONT_EFFECT_TARGET_TEXT__"
LINE_COUNT_TOKEN = "__FONT_EFFECT_LINE_COUNT__"


class PreviewError(Exception):
    """Raised when the lettering archive cannot be rendered safely."""


def _section_map(raw):
    sections = {}
    current = None
    for line in raw.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def _section_body(sections, name):
    return "\n".join(sections.get(name, [])).strip()


def _bullet_map(sections, name):
    result = {}
    current_key = None
    for line in sections.get(name, []):
        if line.startswith("- ") and ": " in line:
            current_key, value = line[2:].split(": ", 1)
            result[current_key] = value
        elif current_key and line.strip():
            result[current_key] += "\n" + line.strip()
    return result


def parse_case_markdown(raw):
    """Extract fields used by the gallery from an archived case document."""
    sections = _section_map(raw)
    copy = _bullet_map(sections, "Copy")
    analysis = _bullet_map(sections, "Font analysis")
    return {
        "source_text": copy.get("Source", ""),
        "target_text": copy.get("Target", ""),
        "category": analysis.get("Category", ""),
        "confidence": analysis.get("Confidence", ""),
        "evidence": analysis.get("Evidence", ""),
        "custom_modifications": analysis.get("Custom modifications", ""),
        "visual_analysis": _section_body(sections, "Visual analysis"),
        "original_prompt": _section_body(sections, "Original prompt"),
        "final_prompt": _section_body(sections, "Final prompt"),
        "classification_notes": _section_body(sections, "Classification notes"),
    }


def make_prompt_template(prompt, target_text="", source_text=""):
    """Replace archived copy with tokens and append a high-priority layout override."""
    prompt = (prompt or "").strip()
    if not prompt:
        return ""
    templated = prompt
    for candidate in (target_text, source_text):
        if not candidate:
            continue
        quoted = "「{}」".format(candidate)
        if quoted in templated:
            templated = templated.replace(
                quoted,
                "「{}」".format(TARGET_TEXT_TOKEN),
                1,
            )
            break
    if TARGET_TEXT_TOKEN not in templated:
        templated, count = re.subn(
            r"「.*?」",
            "「{}」".format(TARGET_TEXT_TOKEN),
            templated,
            count=1,
            flags=re.DOTALL,
        )
        if count == 0:
            templated = (
                "製作一張孤立的美術字資產，唯一目標是渲染精確文字"
                "「{}」。\n\n{}".format(TARGET_TEXT_TOKEN, templated)
            )
    override = (
        "本次文案排版覆盖上述针对旧文案的行数、字距、行距、字号与单字比例描述："
        "严格依照输入中的 {} 行换行排版；各行默认保持统一字号、字重和字形比例，"
        "不制造单字大小差异，仅可调整字距、行距与整体缩放以适配画布。"
        "若原提示词与本次文案排版冲突，以本段为准；其余字形、材质、色彩、描边、"
        "阴影、平滑降噪和透明背景要求全部保留。"
    ).format(LINE_COUNT_TOKEN)
    return "{}\n\n{}".format(templated.rstrip(), override)


def _read_index(index_path):
    if not index_path.is_file():
        raise PreviewError("index.jsonl is missing: {}".format(index_path))
    try:
        raw = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise PreviewError("index.jsonl is not readable: {}".format(error)) from error
    records = []
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise PreviewError("invalid index JSON at line {}".format(number)) from error
        if not isinstance(record, dict):
            raise PreviewError("invalid index record at line {}".format(number))
        records.append(record)
    return records


def _image_data_url(image_path):
    mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    try:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    except OSError as error:
        raise PreviewError("reference image is not readable: {}".format(error)) from error
    return "data:{};base64,{}".format(mime, encoded)


def load_cases(library):
    """Load indexed cases, returning usable case data and non-fatal warnings."""
    library = Path(library).resolve()
    records = _read_index(library / "index.jsonl")
    cases = []
    warnings = []
    for record in records:
        case_id = record.get("case_id")
        reference = record.get("reference")
        if not isinstance(case_id, str) or not case_id:
            warnings.append("unknown case: missing case_id")
            continue
        if not isinstance(reference, str) or not reference:
            warnings.append("{}: missing reference path".format(case_id))
            continue
        case_directory = library / "cases" / case_id
        case_path = case_directory / "case.md"
        image_path = library / reference
        if not case_path.is_file() or not image_path.is_file():
            warnings.append("{}: missing case.md or reference image".format(case_id))
            continue
        try:
            parsed = parse_case_markdown(case_path.read_text(encoding="utf-8"))
            image_url = _image_data_url(image_path)
        except (OSError, UnicodeError, PreviewError) as error:
            warnings.append("{}: {}".format(case_id, error))
            continue
        case = dict(record)
        case.update(parsed)
        case["case_id"] = case_id
        case["image_url"] = image_url
        case["style_tags"] = list(record.get("style_tags") or [])
        case["effect_tags"] = list(record.get("effect_tags") or [])
        case["prompt_template"] = make_prompt_template(
            parsed.get("final_prompt") or parsed.get("original_prompt"),
            target_text=parsed.get("target_text", ""),
            source_text=parsed.get("source_text", ""),
        )
        cases.append(case)
    return cases, warnings


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>字效索引 · Font Effect Library</title>
  <style>
    :root {
      --ink-950: #09111b;
      --ink-900: #0f1a28;
      --ink-850: #142132;
      --ink-800: #1a293d;
      --ink-700: #2a3b50;
      --paper: #f4f0e7;
      --paper-muted: #c7c7c2;
      --ice: #b9d9dc;
      --ice-strong: #d9f1ef;
      --gold: #d7c39a;
      --lavender: #c8c2df;
      --danger: #efb6a3;
      --line: rgba(237, 241, 239, 0.13);
      --display: "Iowan Old Style", "Baskerville", "Songti SC", "STSong", serif;
      --body: "Avenir Next", "PingFang TC", "PingFang SC", sans-serif;
      --mono: "SFMono-Regular", "Cascadia Mono", "Liberation Mono", monospace;
    }

    * {
      box-sizing: border-box;
    }

    html {
      min-height: 100%;
      background: var(--ink-950);
    }

    body {
      min-height: 100vh;
      margin: 0;
      overflow-x: hidden;
      color: var(--paper);
      background:
        radial-gradient(circle at 10% -20%, rgba(185, 217, 220, 0.13), transparent 38rem),
        radial-gradient(circle at 92% 14%, rgba(215, 195, 154, 0.09), transparent 32rem),
        var(--ink-950);
      font-family: var(--body);
      line-height: 1.65;
    }

    button,
    input,
    select,
    textarea {
      font: inherit;
    }

    button,
    select {
      cursor: pointer;
    }

    button:focus-visible,
    input:focus-visible,
    select:focus-visible,
    textarea:focus-visible,
    .case-card:focus-visible {
      outline: 2px solid var(--ice);
      outline-offset: 3px;
    }

    .shell {
      width: min(1500px, calc(100% - 40px));
      margin: 0 auto;
      padding: 34px 0 72px;
    }

    .masthead {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 28px;
      align-items: end;
      padding: 18px 0 30px;
      border-bottom: 1px solid var(--line);
    }

    .eyebrow {
      margin: 0 0 8px;
      color: var(--ice);
      font: 600 11px/1.2 var(--mono);
      letter-spacing: 0.2em;
      text-transform: uppercase;
    }

    h1 {
      margin: 0;
      font: 500 clamp(44px, 7vw, 92px)/0.92 var(--display);
      letter-spacing: -0.045em;
      text-wrap: balance;
    }

    .masthead-copy {
      max-width: 680px;
      margin: 16px 0 0;
      color: var(--paper-muted);
      font-size: 15px;
      text-wrap: pretty;
    }

    .library-count {
      display: grid;
      justify-items: end;
      gap: 2px;
      color: var(--paper-muted);
      font: 500 12px/1.2 var(--mono);
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    .library-count strong {
      color: var(--paper);
      font: 500 54px/1 var(--display);
      letter-spacing: -0.04em;
    }

    .controls {
      position: sticky;
      top: 0;
      z-index: 10;
      margin: 0 -20px;
      padding: 18px 20px 15px;
      border-bottom: 1px solid var(--line);
      background: rgba(9, 17, 27, 0.92);
      backdrop-filter: blur(18px) saturate(120%);
    }

    .control-row {
      display: grid;
      grid-template-columns: minmax(240px, 1fr) auto auto;
      gap: 12px;
    }

    .search-wrap {
      position: relative;
    }

    .search-wrap label {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }

    #search-input,
    #sort-select,
    .ghost-button {
      min-height: 46px;
      border: 1px solid var(--line);
      border-radius: 4px;
      color: var(--paper);
      background: var(--ink-850);
    }

    #search-input {
      width: 100%;
      padding: 0 16px;
      font-size: 15px;
    }

    #search-input::placeholder {
      color: #89919c;
    }

    #sort-select {
      padding: 0 38px 0 14px;
    }

    .ghost-button {
      padding: 0 16px;
    }

    .ghost-button:hover {
      border-color: rgba(185, 217, 220, 0.48);
      background: var(--ink-800);
    }

    .filter-groups {
      display: flex;
      flex-wrap: wrap;
      gap: 9px 22px;
      margin-top: 13px;
    }

    .filter-group {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 7px;
    }

    .filter-label {
      margin-right: 2px;
      color: #8f9aa7;
      font: 600 10px/1 var(--mono);
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }

    .filter-chip {
      min-height: 30px;
      padding: 4px 10px;
      border: 1px solid transparent;
      border-radius: 999px;
      color: #aeb7c1;
      background: transparent;
      font-size: 12px;
    }

    .filter-chip:hover {
      color: var(--paper);
      background: rgba(255, 255, 255, 0.045);
    }

    .filter-chip[aria-pressed="true"] {
      border-color: rgba(185, 217, 220, 0.48);
      color: var(--ice-strong);
      background: rgba(185, 217, 220, 0.1);
    }

    .results-line {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 20px;
      margin: 28px 0 13px;
      color: #99a4af;
      font-size: 13px;
    }

    .results-line strong {
      color: var(--paper);
      font-weight: 600;
    }

    .case-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 18px;
    }

    .case-card {
      grid-column: span 6;
      display: grid;
      grid-template-rows: auto 1fr;
      min-width: 0;
      padding: 0;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: inherit;
      text-align: left;
      background: var(--ink-900);
      box-shadow: 0 18px 50px rgba(0, 0, 0, 0.16);
      transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
    }

    .case-card:nth-child(4n + 1),
    .case-card:nth-child(4n + 4) {
      grid-column: span 7;
    }

    .case-card:nth-child(4n + 2),
    .case-card:nth-child(4n + 3) {
      grid-column: span 5;
    }

    .case-card:hover {
      transform: translateY(-3px);
      border-color: rgba(185, 217, 220, 0.34);
      background: #132133;
    }

    .preview-stage {
      position: relative;
      display: grid;
      place-items: center;
      min-height: 250px;
      padding: 22px;
      overflow: hidden;
      background:
        linear-gradient(135deg, rgba(185, 217, 220, 0.035), transparent 55%),
        #0b1421;
    }

    .preview-stage::after {
      position: absolute;
      inset: auto 16px 14px auto;
      content: attr(data-index);
      color: rgba(244, 240, 231, 0.35);
      font: 500 10px/1 var(--mono);
      letter-spacing: 0.16em;
    }

    .preview-stage img {
      display: block;
      width: 100%;
      max-height: 290px;
      object-fit: contain;
      filter: saturate(0.98) contrast(1.01);
    }

    .card-copy {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 20px;
      align-items: start;
      padding: 18px 18px 19px;
      border-top: 1px solid var(--line);
    }

    .card-copy h2 {
      margin: 0;
      overflow: hidden;
      color: var(--paper);
      font: 500 clamp(22px, 3vw, 34px)/1.25 var(--display);
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .category {
      margin: 5px 0 0;
      color: #aab3bd;
      font-size: 12px;
      line-height: 1.45;
    }

    .tag-list {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 5px;
      max-width: 220px;
    }

    .tag {
      padding: 3px 7px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: #9eabb7;
      font: 500 10px/1.4 var(--mono);
      white-space: nowrap;
    }

    .empty-state {
      grid-column: 1 / -1;
      display: grid;
      place-items: center;
      min-height: 360px;
      padding: 40px;
      border: 1px dashed rgba(244, 240, 231, 0.2);
      color: #9aa5b1;
      text-align: center;
    }

    .empty-state strong {
      display: block;
      margin-bottom: 8px;
      color: var(--paper);
      font: 500 30px/1.2 var(--display);
    }

    dialog {
      width: min(1180px, calc(100% - 32px));
      max-height: calc(100vh - 32px);
      margin: auto;
      padding: 0;
      overflow: hidden;
      border: 1px solid rgba(244, 240, 231, 0.2);
      border-radius: 8px;
      color: var(--paper);
      background: var(--ink-900);
      box-shadow: 0 30px 100px rgba(0, 0, 0, 0.5);
    }

    dialog::backdrop {
      background: rgba(3, 8, 14, 0.82);
      backdrop-filter: blur(7px);
    }

    .dialog-layout {
      display: grid;
      grid-template-columns: minmax(0, 0.95fr) minmax(360px, 1.05fr);
      max-height: calc(100vh - 34px);
    }

    .dialog-visual {
      position: sticky;
      top: 0;
      display: grid;
      place-items: center;
      min-height: 520px;
      padding: 34px;
      background:
        radial-gradient(circle at 50% 50%, rgba(185, 217, 220, 0.08), transparent 60%),
        #0a1420;
    }

    .dialog-visual img {
      display: block;
      width: 100%;
      max-height: 72vh;
      object-fit: contain;
    }

    .dialog-content {
      position: relative;
      overflow-y: auto;
      scrollbar-gutter: stable;
      padding: 34px 34px 44px;
      border-left: 1px solid var(--line);
    }

    .close-button {
      position: sticky;
      top: 0;
      float: right;
      width: 44px;
      height: 44px;
      margin: -8px -8px 0 12px;
      border: 1px solid var(--line);
      border-radius: 50%;
      color: var(--paper);
      background: var(--ink-850);
      font-size: 20px;
      line-height: 1;
      z-index: 2;
    }

    .detail-id {
      margin: 0 0 12px;
      color: var(--ice);
      font: 500 10px/1.4 var(--mono);
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }

    .detail-title {
      margin: 0;
      font: 500 clamp(36px, 5vw, 62px)/1.08 var(--display);
      letter-spacing: -0.035em;
      white-space: pre-line;
    }

    .detail-target {
      margin: 7px 0 20px;
      color: var(--paper-muted);
      white-space: pre-line;
    }

    .detail-tags {
      justify-content: flex-start;
      max-width: none;
      margin-bottom: 30px;
    }

    .detail-section {
      padding: 22px 0;
      border-top: 1px solid var(--line);
    }

    .detail-section h3 {
      margin: 0 0 9px;
      color: var(--gold);
      font: 600 10px/1.4 var(--mono);
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }

    .detail-section p {
      margin: 0;
      color: #c3c9cd;
      font-size: 14px;
      white-space: pre-line;
      text-wrap: pretty;
    }

    .target-builder {
      margin: 2px 0 22px;
      padding: 18px;
      border: 1px solid rgba(185, 217, 220, 0.22);
      border-radius: 4px;
      background: rgba(185, 217, 220, 0.045);
    }

    .target-builder label {
      display: block;
      margin-bottom: 4px;
      color: var(--paper);
      font: 500 21px/1.25 var(--display);
    }

    .builder-help {
      margin: 0 0 12px !important;
      color: #9ea9b4 !important;
      font-size: 12px !important;
    }

    #target-copy-input {
      display: block;
      width: 100%;
      min-height: 108px;
      padding: 13px 14px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 4px;
      color: var(--paper);
      background: #09131f;
      font-size: 16px;
      line-height: 1.7;
    }

    #target-copy-input::placeholder {
      color: #737e8b;
    }

    .builder-actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
      margin-top: 12px;
    }

    .builder-shortcut {
      color: #7f8b98;
      font: 10px/1.4 var(--mono);
    }

    .generate-button {
      min-height: 44px;
      padding: 9px 16px;
      border: 1px solid rgba(215, 195, 154, 0.48);
      border-radius: 4px;
      color: #15110a;
      background: var(--gold);
      font-weight: 650;
    }

    .generate-button:hover {
      background: #ead7ae;
    }

    .target-status {
      min-height: 20px;
      margin: 8px 0 0 !important;
      color: var(--ice) !important;
      font-size: 12px !important;
    }

    .prompt-tabs {
      display: flex;
      gap: 8px;
      margin: 2px 0 12px;
    }

    .tab-button,
    .copy-button {
      min-height: 40px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 4px;
      color: var(--paper);
      background: var(--ink-850);
      font-size: 12px;
    }

    .tab-button[aria-selected="true"] {
      border-color: rgba(185, 217, 220, 0.52);
      color: var(--ice-strong);
      background: rgba(185, 217, 220, 0.1);
    }

    .copy-button {
      margin-left: auto;
      border-color: rgba(215, 195, 154, 0.36);
      color: #f4e8cd;
    }

    .prompt-box {
      max-height: none;
      margin: 0;
      padding: 16px;
      overflow: visible;
      border: 1px solid var(--line);
      border-radius: 4px;
      color: #d5d9dc;
      background: #09131f;
      font: 12px/1.75 var(--mono);
      white-space: pre-wrap;
      word-break: break-word;
    }

    .copy-status {
      min-height: 20px;
      margin: 8px 0 0;
      color: var(--ice);
      font-size: 12px;
    }

    .warning-strip {
      display: none;
      margin-top: 16px;
      padding: 10px 12px;
      border: 1px solid rgba(239, 182, 163, 0.24);
      color: var(--danger);
      background: rgba(239, 182, 163, 0.05);
      font-size: 12px;
    }

    .warning-strip.visible {
      display: block;
    }

    @media (max-width: 900px) {
      .case-card,
      .case-card:nth-child(n) {
        grid-column: span 12;
      }

      .dialog-layout {
        grid-template-columns: 1fr;
        overflow-y: auto;
      }

      .dialog-visual {
        position: relative;
        min-height: 290px;
      }

      .dialog-content {
        overflow: visible;
        border-top: 1px solid var(--line);
        border-left: 0;
      }
    }

    @media (max-width: 640px) {
      .shell {
        width: calc(100% - 24px);
        padding-top: 18px;
      }

      .masthead {
        grid-template-columns: 1fr;
      }

      .library-count {
        justify-items: start;
      }

      .control-row {
        grid-template-columns: 1fr 1fr;
      }

      .search-wrap {
        grid-column: 1 / -1;
      }

      .controls {
        margin: 0 -12px;
        padding-inline: 12px;
      }

      .preview-stage {
        min-height: 200px;
      }

      .card-copy {
        grid-template-columns: 1fr;
      }

      .tag-list {
        justify-content: flex-start;
        max-width: none;
      }

      .dialog-content {
        padding: 24px 20px 36px;
      }

      .dialog-visual {
        padding: 20px;
      }

      .prompt-tabs {
        flex-wrap: wrap;
      }

      .copy-button {
        width: 100%;
        margin-left: 0;
      }

      .builder-actions {
        align-items: stretch;
        flex-direction: column;
      }

      .generate-button {
        width: 100%;
      }
    }

    @media (max-width: 520px) {
      .control-row {
        grid-template-columns: minmax(0, 1fr);
      }

      .search-wrap {
        grid-column: auto;
      }

      #sort-select,
      .ghost-button {
        width: 100%;
        min-width: 0;
      }

      .filter-group {
        width: 100%;
        min-width: 0;
      }

      .results-line {
        align-items: flex-start;
        flex-direction: column;
        gap: 4px;
      }

      .case-grid {
        grid-template-columns: minmax(0, 1fr);
      }

      .case-card,
      .case-card:nth-child(n) {
        grid-column: 1 / -1;
      }

      .preview-stage {
        padding: 14px;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *,
      *::before,
      *::after {
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="masthead">
      <div>
        <p class="eyebrow">Font Effect Library / Local Archive</p>
        <h1>字效索引</h1>
        <p class="masthead-copy">把所有参考图、风格标签和生图提示词放在同一张联系表里。先看图，再筛选，最后复制。</p>
      </div>
      <div class="library-count" aria-label="归档案例数量">
        <strong id="total-count">0</strong>
        archived cases
      </div>
    </header>

    <section class="controls" aria-label="筛选工具">
      <div class="control-row">
        <div class="search-wrap">
          <label for="search-input">搜索字体案例</label>
          <input id="search-input" type="search" placeholder="搜索文案、分类或标签…" autocomplete="off">
        </div>
        <select id="sort-select" aria-label="排序方式">
          <option value="newest">最新归档</option>
          <option value="oldest">最早归档</option>
          <option value="title">按文案</option>
        </select>
        <button id="clear-button" class="ghost-button" type="button">清除筛选</button>
      </div>
      <div id="filter-groups" class="filter-groups"></div>
      <div id="warning-strip" class="warning-strip" role="status"></div>
    </section>

    <div class="results-line">
      <span>当前显示 <strong id="visible-count">0</strong> 款字效</span>
      <span>点击卡片查看完整提示词</span>
    </div>

    <section id="case-grid" class="case-grid" aria-live="polite"></section>
  </main>

  <dialog id="detail-dialog" aria-labelledby="detail-title">
    <div class="dialog-layout">
      <div class="dialog-visual">
        <img id="detail-image" alt="">
      </div>
      <div class="dialog-content">
        <button id="close-dialog" class="close-button" type="button" aria-label="关闭详情">×</button>
        <p id="detail-id" class="detail-id"></p>
        <h2 id="detail-title" class="detail-title"></h2>
        <p id="detail-target" class="detail-target"></p>
        <div id="detail-tags" class="tag-list detail-tags"></div>

        <section class="detail-section">
          <h3>字体结构</h3>
          <p id="detail-category"></p>
        </section>
        <section class="detail-section">
          <h3>可见特征</h3>
          <p id="detail-evidence"></p>
        </section>
        <section class="detail-section">
          <h3>效果与排版</h3>
          <p id="detail-visual"></p>
        </section>
        <section class="detail-section">
          <h3>GPT Image 2 Prompt</h3>
          <div class="target-builder">
            <label for="target-copy-input">换成你的目标文案</label>
            <p class="builder-help">输入时直接换行，生成结果会保留当前字体的字形、材质与平滑降噪规则。</p>
            <textarea id="target-copy-input" placeholder="在这里输入要生成的文字…" spellcheck="false"></textarea>
            <div class="builder-actions">
              <span class="builder-shortcut">⌘ / Ctrl + Enter 快速生成</span>
              <button id="generate-prompt" class="generate-button" type="button">生成生图提示词</button>
            </div>
            <p id="target-status" class="target-status" role="status"></p>
          </div>
          <div class="prompt-tabs" role="tablist" aria-label="提示词版本">
            <button id="original-tab" class="tab-button" type="button" role="tab" aria-selected="false">原始提示词</button>
            <button id="final-tab" class="tab-button" type="button" role="tab" aria-selected="true">终版提示词</button>
            <button id="generated-tab" class="tab-button" type="button" role="tab" aria-selected="false" hidden>你的提示词</button>
            <button id="copy-prompt" class="copy-button" type="button">复制终版提示词</button>
          </div>
          <pre id="prompt-box" class="prompt-box" tabindex="0"></pre>
          <p id="copy-status" class="copy-status" role="status"></p>
        </section>
      </div>
    </div>
  </dialog>

  <script>
    const CASES = __CASE_DATA__;
    const BUILD_WARNINGS = __BUILD_WARNINGS__;
    const state = {
      query: "",
      sort: "newest",
      selected: { language: new Set(), style: new Set(), effect: new Set() },
      activeCase: null,
      promptKind: "final",
      targetText: "",
      generatedPrompt: ""
    };

    const labels = {
      language: "语种",
      style: "风格",
      effect: "效果"
    };

    const searchInput = document.getElementById("search-input");
    const sortSelect = document.getElementById("sort-select");
    const clearButton = document.getElementById("clear-button");
    const filterGroups = document.getElementById("filter-groups");
    const caseGrid = document.getElementById("case-grid");
    const visibleCount = document.getElementById("visible-count");
    const totalCount = document.getElementById("total-count");
    const warningStrip = document.getElementById("warning-strip");
    const dialog = document.getElementById("detail-dialog");
    const originalTab = document.getElementById("original-tab");
    const finalTab = document.getElementById("final-tab");
    const generatedTab = document.getElementById("generated-tab");
    const copyButton = document.getElementById("copy-prompt");
    const promptBox = document.getElementById("prompt-box");
    const copyStatus = document.getElementById("copy-status");
    const targetCopyInput = document.getElementById("target-copy-input");
    const generateButton = document.getElementById("generate-prompt");
    const targetStatus = document.getElementById("target-status");
    const TARGET_TEXT_TOKEN = "__FONT_EFFECT_TARGET_TEXT__";
    const LINE_COUNT_TOKEN = "__FONT_EFFECT_LINE_COUNT__";

    function unique(values) {
      return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hant"));
    }

    function allTags(caseItem) {
      return [...(caseItem.style_tags || []), ...(caseItem.effect_tags || [])];
    }

    function filterValues() {
      return {
        language: unique(CASES.map((item) => item.language)),
        style: unique(CASES.flatMap((item) => item.style_tags || [])),
        effect: unique(CASES.flatMap((item) => item.effect_tags || []))
      };
    }

    function makeTag(text) {
      const span = document.createElement("span");
      span.className = "tag";
      span.textContent = text;
      return span;
    }

    function renderFilters() {
      filterGroups.replaceChildren();
      const values = filterValues();
      Object.keys(values).forEach((groupName) => {
        if (!values[groupName].length) return;
        const group = document.createElement("div");
        group.className = "filter-group";
        const label = document.createElement("span");
        label.className = "filter-label";
        label.textContent = labels[groupName];
        group.append(label);
        values[groupName].forEach((value) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "filter-chip";
          button.textContent = value;
          button.setAttribute("aria-pressed", "false");
          button.addEventListener("click", () => {
            const selected = state.selected[groupName];
            if (selected.has(value)) selected.delete(value);
            else selected.add(value);
            button.setAttribute("aria-pressed", String(selected.has(value)));
            renderCases();
          });
          group.append(button);
        });
        filterGroups.append(group);
      });
    }

    function matchesSet(values, selected) {
      if (!selected.size) return true;
      return values.some((value) => selected.has(value));
    }

    function filteredCases() {
      const query = state.query.trim().toLocaleLowerCase("zh-Hant");
      const result = CASES.filter((item) => {
        const haystack = [
          item.case_id,
          item.source_text,
          item.target_text,
          item.category,
          item.evidence,
          item.language,
          ...allTags(item)
        ].join(" ").toLocaleLowerCase("zh-Hant");
        return (!query || haystack.includes(query))
          && matchesSet([item.language], state.selected.language)
          && matchesSet(item.style_tags || [], state.selected.style)
          && matchesSet(item.effect_tags || [], state.selected.effect);
      });
      return result.sort((a, b) => {
        if (state.sort === "oldest") {
          return String(a.created_at).localeCompare(String(b.created_at));
        }
        if (state.sort === "title") {
          return String(a.source_text).localeCompare(String(b.source_text), "zh-Hant");
        }
        return String(b.created_at).localeCompare(String(a.created_at))
          || String(b.case_id).localeCompare(String(a.case_id));
      });
    }

    function caseCard(item, index) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "case-card";
      button.setAttribute("aria-label", "查看字效：" + (item.source_text || item.case_id));

      const stage = document.createElement("div");
      stage.className = "preview-stage";
      stage.dataset.index = String(index + 1).padStart(2, "0");
      const image = document.createElement("img");
      image.src = item.image_url;
      image.alt = (item.source_text || "字体案例") + "参考图";
      stage.append(image);

      const copy = document.createElement("div");
      copy.className = "card-copy";
      const headingWrap = document.createElement("div");
      const heading = document.createElement("h2");
      heading.textContent = item.source_text || "未命名字效";
      const category = document.createElement("p");
      category.className = "category";
      category.textContent = item.category || "未记录字体分类";
      headingWrap.append(heading, category);

      const tags = document.createElement("div");
      tags.className = "tag-list";
      allTags(item).slice(0, 4).forEach((tag) => tags.append(makeTag(tag)));
      copy.append(headingWrap, tags);
      button.append(stage, copy);
      button.addEventListener("click", () => openDetail(item));
      return button;
    }

    function renderCases() {
      const items = filteredCases();
      visibleCount.textContent = String(items.length);
      caseGrid.replaceChildren();
      if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        const hasAnyCase = CASES.length > 0;
        empty.innerHTML = hasAnyCase
          ? "<div><strong>没有匹配的字效</strong><span>换个关键词或清除筛选。</span></div>"
          : "<div><strong>还没有归档字体</strong><span>完成一次字效归档后重新生成页面。</span></div>";
        caseGrid.append(empty);
        return;
      }
      items.forEach((item, index) => caseGrid.append(caseCard(item, index)));
    }

    function setText(id, value, fallback) {
      document.getElementById(id).textContent = value || fallback;
    }

    function buildTargetPrompt(item, targetText) {
      const normalized = String(targetText || "").replace(/\r\n?/g, "\n").trim();
      if (!normalized) return "";
      const lineCount = normalized.split("\n").length;
      const template = item.prompt_template || item.final_prompt || item.original_prompt || "";
      return template
        .split(TARGET_TEXT_TOKEN).join(normalized)
        .split(LINE_COUNT_TOKEN).join(String(lineCount));
    }

    function renderPrompt() {
      if (!state.activeCase) return;
      const values = {
        original: state.activeCase.original_prompt,
        final: state.activeCase.final_prompt,
        generated: state.generatedPrompt
      };
      const value = values[state.promptKind];
      originalTab.setAttribute("aria-selected", String(state.promptKind === "original"));
      finalTab.setAttribute("aria-selected", String(state.promptKind === "final"));
      generatedTab.hidden = !state.generatedPrompt;
      generatedTab.setAttribute("aria-selected", String(state.promptKind === "generated"));
      promptBox.textContent = value || "此案例没有记录该版本提示词。";
      const copyLabels = {
        original: "复制原始提示词",
        final: "复制终版提示词",
        generated: "复制你的提示词"
      };
      copyButton.textContent = copyLabels[state.promptKind];
      copyStatus.textContent = "";
    }

    function generateTargetPrompt() {
      const targetText = targetCopyInput.value.replace(/\r\n?/g, "\n").trim();
      if (!targetText) {
        targetStatus.textContent = "请先输入目标文案。";
        targetCopyInput.focus();
        return;
      }
      state.targetText = targetText;
      state.generatedPrompt = buildTargetPrompt(state.activeCase, targetText);
      state.promptKind = "generated";
      targetStatus.textContent = "已按当前字效生成，可在下方检查并复制。";
      renderPrompt();
    }

    function openDetail(item) {
      state.activeCase = item;
      state.generatedPrompt = state.targetText ? buildTargetPrompt(item, state.targetText) : "";
      state.promptKind = state.generatedPrompt ? "generated" : "final";
      targetCopyInput.value = state.targetText;
      targetStatus.textContent = state.generatedPrompt
        ? "已沿用上一次输入，并切换为当前字效。"
        : "";
      setText("detail-id", item.case_id, "未记录案例编号");
      setText("detail-title", item.source_text, "未命名字效");
      setText(
        "detail-target",
        item.target_text && item.target_text !== item.source_text ? "目标文案 · " + item.target_text : "",
        ""
      );
      setText("detail-category", item.category, "未记录字体分类。");
      setText("detail-evidence", item.evidence, "未记录可见特征。");
      setText("detail-visual", item.visual_analysis, "未记录视觉分析。");
      const image = document.getElementById("detail-image");
      image.src = item.image_url;
      image.alt = (item.source_text || "字体案例") + "参考大图";
      const tags = document.getElementById("detail-tags");
      tags.replaceChildren();
      [item.language, ...allTags(item)].filter(Boolean).forEach((tag) => tags.append(makeTag(tag)));
      renderPrompt();
      dialog.showModal();
      document.getElementById("close-dialog").focus();
    }

    async function copyPrompt() {
      if (!state.activeCase) return;
      const value = promptBox.textContent;
      if (!value) {
        copyStatus.textContent = "当前没有可复制的提示词。";
        return;
      }
      try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error("clipboard unavailable");
        await navigator.clipboard.writeText(value);
        copyStatus.textContent = "已复制，可以直接粘贴到 GPT Image 2。";
      } catch (error) {
        const helper = document.createElement("textarea");
        helper.value = value;
        helper.setAttribute("readonly", "");
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.append(helper);
        helper.select();
        const copied = document.execCommand("copy");
        helper.remove();
        copyStatus.textContent = copied ? "已复制。" : "复制受限，提示词已选中，请手动复制。";
        if (!copied) {
          const selection = window.getSelection();
          const range = document.createRange();
          range.selectNodeContents(promptBox);
          selection.removeAllRanges();
          selection.addRange(range);
        }
      }
    }

    searchInput.addEventListener("input", (event) => {
      state.query = event.target.value;
      renderCases();
    });

    sortSelect.addEventListener("change", (event) => {
      state.sort = event.target.value;
      renderCases();
    });

    clearButton.addEventListener("click", () => {
      state.query = "";
      searchInput.value = "";
      state.sort = "newest";
      sortSelect.value = "newest";
      Object.values(state.selected).forEach((set) => set.clear());
      document.querySelectorAll(".filter-chip").forEach((chip) => chip.setAttribute("aria-pressed", "false"));
      renderCases();
      searchInput.focus();
    });

    originalTab.addEventListener("click", () => {
      state.promptKind = "original";
      renderPrompt();
    });

    finalTab.addEventListener("click", () => {
      state.promptKind = "final";
      renderPrompt();
    });

    generatedTab.addEventListener("click", () => {
      if (!state.generatedPrompt) return;
      state.promptKind = "generated";
      renderPrompt();
    });

    targetCopyInput.addEventListener("input", () => {
      if (!state.generatedPrompt) return;
      state.generatedPrompt = "";
      if (state.promptKind === "generated") state.promptKind = "final";
      targetStatus.textContent = "文案已修改，请重新生成。";
      renderPrompt();
    });

    targetCopyInput.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        generateTargetPrompt();
      }
    });

    generateButton.addEventListener("click", generateTargetPrompt);
    copyButton.addEventListener("click", copyPrompt);
    document.getElementById("close-dialog").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });

    totalCount.textContent = String(CASES.length);
    if (BUILD_WARNINGS.length) {
      warningStrip.textContent = "生成时跳过 " + BUILD_WARNINGS.length + " 个案例：" + BUILD_WARNINGS.join("；");
      warningStrip.classList.add("visible");
    }
    renderFilters();
    renderCases();
  </script>
</body>
</html>
"""


def build_gallery(library, output_path=None):
    """Build preview.html atomically and return its absolute path and case count."""
    library = Path(library).resolve()
    cases, warnings = load_cases(library)
    output = Path(output_path).resolve() if output_path else library / "preview.html"
    payload = json.dumps(cases, ensure_ascii=False).replace("</", "<\\/")
    warning_payload = json.dumps(warnings, ensure_ascii=False).replace("</", "<\\/")
    html = (
        HTML_TEMPLATE.replace("__CASE_DATA__", payload)
        .replace("__BUILD_WARNINGS__", warning_payload)
    )
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(output.parent),
            prefix=".preview-",
            suffix=".html",
            delete=False,
        ) as temporary:
            temporary.write(html)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(str(temporary_path), str(output))
    except OSError as error:
        try:
            temporary_path.unlink()
        except (NameError, OSError):
            pass
        raise PreviewError("preview output is not writable: {}".format(error)) from error
    return {
        "preview_path": str(output.resolve()),
        "case_count": len(cases),
        "warnings": warnings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the local lettering preview gallery.")
    parser.add_argument("--library", required=True, help="Absolute path to the archive library.")
    parser.add_argument("--output", help="Optional absolute output HTML path.")
    arguments = parser.parse_args(argv)
    try:
        result = build_gallery(arguments.library, arguments.output)
    except (PreviewError, OSError, UnicodeError) as error:
        print("preview build failed: {}".format(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
