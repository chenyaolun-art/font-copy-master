# Font Effect Prompt Builder Skill Design

## Goal

Create a Codex skill that analyzes stylized lettering in a user-provided screenshot, reconstructs the likely typography and visual treatment, and produces a Chinese prompt tailored to ChatGPT Image 2. After the user supplies the actual copy and confirms the final prompt, the skill archives the reference image, analysis, prompts, and lightweight language/style classification as a reusable case.

The first version produces prompts and maintains the case library. It does not invoke image generation.

## Confirmed Product Decisions

- Prompts are written primarily in Traditional Chinese. Unambiguous English typography or visual terms may remain in English when translation would reduce precision.
- Generated images must contain only the requested text and its attached visual treatment.
- Transparent background is the default. A plain high-contrast background is the fallback when transparency is unreliable.
- Drafts are not archived. A case is archived only after the user explicitly confirms that the final prompt is complete.
- Font identification must express uncertainty. When exact identification is unreliable, the skill provides one to three likely candidates or a font category, a confidence level, and any likely custom lettering modifications.
- The case library uses structured metadata plus human-readable case documents.

## Architecture

The skill has four responsibilities with explicit handoffs:

1. **Visual analyzer** — reads the screenshot and source text; identifies likely font candidates, glyph construction, composition, material, outlines, shadows, dimensionality, lighting, and background.
2. **Prompt compiler** — converts the visual analysis into one complete Chinese ChatGPT Image 2 prompt that recreates the original lettering and excludes unrelated content.
3. **Copy adapter** — receives the user's intended copy, preserves the visual system, and changes only text-dependent layout constraints such as spacing, line count, aspect ratio, and safe margins.
4. **Case archiver** — after explicit final approval, stores the reference image, analysis, original and final prompts, classifications, and image fingerprint, then updates the structured index.

Data flow:

```text
screenshot + source text
  -> visual analysis
  -> original-effect prompt
  -> user-provided copy
  -> final prompt
  -> explicit user confirmation
  -> case library
```

## Interaction and Output Contract

### Reference Analysis

The user supplies a screenshot. If the lettering is not readable, the skill asks only for the exact source text and does not guess it. The response includes a compact analysis with:

- source text and language/script;
- one to three font candidates or a font category;
- confidence and evidence;
- likely custom glyph modifications;
- composition and layout;
- fill/material, outline, shadow, depth, glow, and other attached effects;
- scene elements that should be omitted from the generated image.

### Original-Effect Prompt

The skill outputs one complete, directly copyable Chinese prompt for ChatGPT Image 2. It must specify:

- the exact source text, rendered once and without spelling variants;
- glyph shape and typography characteristics;
- composition and layout;
- the visual effect stack from inner fill to outer effects;
- transparent background by default;
- a plain high-contrast background only as a fallback;
- no extra text, symbols, icons, people, props, scenes, borders, watermarks, or unrelated decoration.

The user does not need to assemble separate prompt fragments.

### Final Prompt

The skill asks for the intended copy and returns a complete final prompt. When source and target copy lengths differ substantially, the skill may adjust spacing, line breaks, proportions, canvas ratio, and safe margins. It must not delete, rewrite, translate, abbreviate, or decorate the user's copy without permission.

### Confirmation Gate

The skill asks whether the final prompt should be treated as complete. Only an explicit confirmation authorizes case archival. Iteration continues without writing to the case library until that confirmation.

## Skill Package Structure

```text
font-effect-prompt-builder/
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
|-- references/
|   |-- visual-analysis.md
|   |-- image2-prompt-spec.md
|   |-- taxonomy.md
|   `-- case-schema.md
|-- scripts/
|   `-- archive_case.py
`-- library/
    |-- index.jsonl
    `-- cases/<case-id>/
        |-- case.md
        `-- reference.<original-extension>
```

`SKILL.md` contains routing, the core workflow, invariants, and links to the relevant references. Detailed analysis criteria, prompt construction rules, classification vocabulary, and archive schema live in the corresponding reference documents and are loaded only when needed.

## Case Data Model

Each archived case contains:

- case ID and creation date;
- reference image path, file type, and SHA-256 fingerprint;
- source text and final copy;
- language and writing system;
- font candidates/category, confidence, and custom modifications;
- visual analysis;
- original-effect prompt;
- confirmed final prompt;
- normalized style and effect tags.

The human-readable `case.md` is the authoritative case record. `library/index.jsonl` contains the compact fields needed for discovery and duplicate detection. The archive tool derives the index entry from validated case input so the two representations do not drift.

### Initial Classification Axes

- **Language/script:** Traditional Chinese, Simplified Chinese, Japanese, Korean, Latin, Cyrillic, Arabic, mixed script, or other.
- **Style:** cute, elegant, luxury, retro, traditional, energetic, playful, futuristic, industrial, fantasy, horror, street, handwritten, editorial, or other.
- **Effects:** flat, gradient, outline, inline, shadow, extrusion/3D, bevel, metallic, chrome, gold, neon, glow, glass, plastic, paper, ink, brush, distressed, flame, ice, liquid, embroidery, or other.

Tags remain deliberately small and multi-select. When no existing tag fits, the case uses `other` plus a concise free-text note rather than expanding the controlled vocabulary for one example.

## Archival Behavior

`archive_case.py` accepts validated case metadata and a readable local image path. It:

1. validates required fields and explicit final-confirmation status;
2. computes the image SHA-256 fingerprint and checks the index for duplicates;
3. creates a safe, deterministic case ID;
4. stages the case document and image in a temporary directory;
5. stages a replacement index containing the new record;
6. moves the complete case into the library and atomically replaces the index;
7. rolls back the new case folder if the index replacement fails;
8. reports the archived case ID and paths.

The tool never overwrites an existing case. Validation or duplicate failures make no library changes. If the conversation image has no readable local source, the skill may still produce prompts but must defer archival and ask the user to reattach or provide the image file.

## Error Handling

- **Missing or unreadable image:** stop visual analysis and request a readable attachment.
- **Unreadable source text:** analyze the visible style, but request the exact source text before compiling prompts.
- **Uncertain font identity:** label the lettering as potentially custom, provide candidates or category plus confidence, and describe observable glyph traits in the prompt.
- **Very different target-copy length:** preserve the copy exactly and adapt only layout-dependent constraints.
- **Unavailable local reference image:** do not archive; retain the completed prompt in the response and explain what is needed to archive later.
- **Missing archive fields or duplicate image:** fail before writing and report the reason.
- **Interrupted archive:** staging, atomic index replacement, and rollback prevent half-created or unindexed cases.

## Validation Strategy

### Behavioral RED/GREEN Test

Before creating the skill, run a realistic stylized-lettering request without loading the skill and record omissions or unsafe assumptions. After implementation, run the same request with the skill and verify that it:

- distinguishes exact font identification from visual inference;
- produces a single complete Chinese Image 2 prompt;
- preserves the requested text exactly and excludes extra content;
- asks for target copy before producing the final prompt;
- waits for explicit confirmation before archival;
- creates complete, searchable case metadata when archival is authorized.

### Archive Tool Tests

Automated tests use temporary directories and cover:

- successful archive creation;
- required-field validation;
- confirmation-gate enforcement;
- SHA-256 duplicate detection;
- safe case IDs and preservation of the original image extension;
- correct JSONL index updates;
- no half-created case or index entry after failure.

### Package Validation

Run the official skill quick validator and check that:

- frontmatter and naming are valid;
- the description is specific enough for correct discovery;
- all linked references exist;
- no scaffold placeholders remain;
- the archive script and tests pass without warnings.

## Out of Scope for Version 1

- Calling ChatGPT Image 2 or any other image-generation tool.
- Comparing generated images with the reference and automatically refining prompts.
- Font-file search, licensing lookup, or downloading fonts.
- Vector tracing, OCR correction beyond asking the user for exact text, or editing the user's image.
- Embedding/vector database retrieval or external storage services.

## Success Criteria

The skill is complete when a user can provide a stylized-lettering screenshot, receive an evidence-based visual analysis and directly usable Chinese ChatGPT Image 2 prompt, replace the source copy with their intended copy without losing the visual system, and explicitly approve a complete archived case that can later be found by language, style, and effect tags.
