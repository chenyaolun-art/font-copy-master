"""Create an atomic archive entry for an analyzed lettering reference."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path


LANGUAGE_TAGS = {
    "arabic-language", "cyrillic-language", "japanese", "korean", "latin-language",
    "mixed", "other", "simplified-chinese", "traditional-chinese",
}
SCRIPT_TAGS = {
    "arabic", "cyrillic", "han", "hangul", "hiragana-katakana", "latin", "mixed",
    "other",
}
STYLE_TAGS = {
    "cute", "editorial", "elegant", "energetic", "fantasy", "futuristic", "handwritten",
    "horror", "industrial", "luxury", "other", "playful", "retro", "street", "traditional",
}
EFFECT_TAGS = {
    "bevel", "brush", "chrome", "distressed", "embroidery", "extrusion-3d", "flame",
    "flat", "glass", "glossy", "glow", "gold", "gradient", "ice", "ink", "inline",
    "liquid", "metallic", "neon", "other", "outline", "paper", "plastic", "shadow",
}
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
REQUIRED_FIELDS = {
    "confirmed", "source_text", "target_text", "language", "script", "font_analysis",
    "visual_analysis", "original_prompt", "final_prompt", "style_tags", "effect_tags",
    "classification_notes",
}
PENDING_MARKER = ".pending-index"
LOCK_FILENAME = ".archive.lock"
_TRANSACTION_LOCK = threading.RLock()


class ArchiveError(Exception):
    """Raised when supplied archive data does not meet the case schema."""


def _require_nonempty_text(metadata, field):
    value = metadata.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ArchiveError("{} must be nonempty".format(field))
    return value.strip()


def _validate_tags(metadata, field, allowed, label):
    values = metadata.get(field)
    if not isinstance(values, list) or not values or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise ArchiveError("{} must be a nonempty list".format(field))
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ArchiveError("unknown {}: {}".format(label, ", ".join(unknown)))
    return sorted(set(values))


def _validate_metadata(metadata):
    if not isinstance(metadata, dict):
        raise ArchiveError("metadata must be an object")
    missing = sorted(REQUIRED_FIELDS - set(metadata))
    if missing:
        raise ArchiveError("missing required field: {}".format(", ".join(missing)))
    if metadata["confirmed"] is not True:
        raise ArchiveError("confirmation must be explicitly true")

    result = dict(metadata)
    for field in (
        "source_text", "target_text", "visual_analysis", "original_prompt", "final_prompt",
    ):
        result[field] = _require_nonempty_text(metadata, field)

    for field, allowed in (("language", LANGUAGE_TAGS), ("script", SCRIPT_TAGS)):
        value = metadata[field]
        if not isinstance(value, str) or value not in allowed:
            raise ArchiveError("unknown {}: {}".format(field, value))
        result[field] = value

    font_analysis = metadata["font_analysis"]
    if not isinstance(font_analysis, dict):
        raise ArchiveError("font_analysis must be an object")
    candidates = font_analysis.get("candidates", [])
    category = font_analysis.get("category", "")
    evidence = font_analysis.get("evidence", "")
    custom_modifications = font_analysis.get("custom_modifications", "")
    if not isinstance(candidates, list) or len(candidates) > 3 or any(
        not isinstance(candidate, str) or not candidate.strip() for candidate in candidates
    ):
        raise ArchiveError("font_analysis candidates must contain at most three text values")
    if not all(isinstance(value, str) for value in (category, evidence, custom_modifications)):
        raise ArchiveError("font_analysis category, evidence, and custom_modifications must be text")
    if not candidates and (not isinstance(category, str) or not category.strip()):
        raise ArchiveError("font_analysis requires candidates or category")
    confidence = font_analysis.get("confidence")
    if not isinstance(confidence, str) or confidence not in {"low", "medium", "high"}:
        raise ArchiveError("font_analysis confidence must be low, medium, or high")
    result["font_analysis"] = dict(font_analysis)
    result["font_analysis"]["candidates"] = [candidate.strip() for candidate in candidates]
    result["font_analysis"]["category"] = category.strip()
    result["font_analysis"]["evidence"] = evidence.strip()
    result["font_analysis"]["custom_modifications"] = custom_modifications.strip()

    result["style_tags"] = _validate_tags(metadata, "style_tags", STYLE_TAGS, "style tag")
    result["effect_tags"] = _validate_tags(metadata, "effect_tags", EFFECT_TAGS, "effect tag")
    notes = metadata["classification_notes"]
    if not isinstance(notes, str):
        raise ArchiveError("classification_notes must be text")
    if (
        "other" in {result["language"], result["script"]}
        or "other" in result["style_tags"]
        or "other" in result["effect_tags"]
    ) and not notes.strip():
        raise ArchiveError("classification_notes is required with other")
    result["classification_notes"] = notes.strip()
    return result


def _stage_image(path, staged_image):
    image_path = Path(path)
    if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ArchiveError("reference image must use a supported extension")
    try:
        if not image_path.is_file():
            raise OSError("not a file")
        with image_path.open("rb") as image_file, staged_image.open("xb") as archive_file:
            digest = hashlib.sha256()
            size = 0
            while True:
                chunk = image_file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                archive_file.write(chunk)
                size += len(chunk)
    except OSError as error:
        raise ArchiveError("reference image is not readable: {}".format(error)) from error
    if not size:
        raise ArchiveError("reference image must be nonempty")
    return digest.hexdigest()


def _read_index(index_path):
    raw = index_path.read_text(encoding="utf-8")
    records = []
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ArchiveError("invalid index JSONL at line {}".format(number)) from error
        if not isinstance(record, dict):
            raise ArchiveError("invalid index JSONL at line {}".format(number))
        records.append(record)
    return records


@contextmanager
def _transaction_lock(library):
    """Serialize archive writes across threads and local processes."""
    with _TRANSACTION_LOCK:
        with (library / LOCK_FILENAME).open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_pending_marker(case_directory):
    marker = case_directory / PENDING_MARKER
    with marker.open("w", encoding="utf-8") as marker_file:
        marker_file.write("index replacement pending\n")
        marker_file.flush()
        os.fsync(marker_file.fileno())


def _reconcile_marked_cases(cases_directory, records):
    """Finish or remove only case directories bearing the durable marker."""
    if not cases_directory.is_dir():
        return
    indexed_case_ids = {
        record.get("case_id") for record in records if isinstance(record.get("case_id"), str)
    }
    for candidate in cases_directory.iterdir():
        if not candidate.is_dir():
            continue
        marker = candidate / PENDING_MARKER
        if not marker.is_file():
            continue
        if candidate.name in indexed_case_ids:
            marker.unlink()
        else:
            shutil.rmtree(candidate)


def _case_markdown(metadata, case_id, archive_day, sha256, image_name):
    analysis = metadata["font_analysis"]
    candidates = ", ".join(analysis.get("candidates", [])) or "—"
    return "\n".join(
        (
            "# Lettering case {}".format(case_id),
            "",
            "- Date: {}".format(archive_day.isoformat()),
            "- Reference: {}".format(image_name),
            "- SHA-256: {}".format(sha256),
            "- Language: {}".format(metadata["language"]),
            "- Script: {}".format(metadata["script"]),
            "- Style tags: {}".format(", ".join(metadata["style_tags"])),
            "- Effect tags: {}".format(", ".join(metadata["effect_tags"])),
            "",
            "## Copy",
            "",
            "- Source: {}".format(metadata["source_text"]),
            "- Target: {}".format(metadata["target_text"]),
            "",
            "## Font analysis",
            "",
            "- Candidates: {}".format(candidates),
            "- Category: {}".format(analysis.get("category", "—") or "—"),
            "- Confidence: {}".format(analysis["confidence"]),
            "- Evidence: {}".format(analysis.get("evidence", "") or "—"),
            "- Custom modifications: {}".format(
                analysis.get("custom_modifications", "") or "—"
            ),
            "",
            "## Visual analysis",
            "",
            metadata["visual_analysis"],
            "",
            "## Original prompt",
            "",
            metadata["original_prompt"],
            "",
            "## Final prompt",
            "",
            metadata["final_prompt"],
            "",
            "## Classification notes",
            "",
            metadata["classification_notes"] or "—",
            "",
        )
    )


def archive_case(metadata, image_path, skill_root, today=None):
    """Validate and atomically archive one lettering case, returning its paths."""
    metadata = _validate_metadata(metadata)
    archive_day = today or date.today()
    if not isinstance(archive_day, date):
        raise ArchiveError("today must be a date")

    library = Path(skill_root) / "library"
    index_path = library / "index.jsonl"
    cases_directory = library / "cases"
    image_path = Path(image_path)
    image_name = "reference{}".format(image_path.suffix.lower())

    with _transaction_lock(library):
        records = _read_index(index_path)
        _reconcile_marked_cases(cases_directory, records)
        had_cases_directory = cases_directory.exists()
        with tempfile.TemporaryDirectory(dir=str(library), prefix=".archive-") as staging_parent:
            staging_parent = Path(staging_parent)
            staged_case = staging_parent / "case"
            staged_case.mkdir()
            sha256 = _stage_image(image_path, staged_case / image_name)
            case_id = "{}-{}".format(archive_day.strftime("%Y%m%d"), sha256[:12])
            if any(record.get("sha256") == sha256 for record in records):
                raise ArchiveError("duplicate reference image")

            destination = cases_directory / case_id
            if destination.exists():
                raise ArchiveError("case destination already exists")
            record = {
                "case_id": case_id,
                "created_at": archive_day.isoformat(),
                "reference": "cases/{}/{}".format(case_id, image_name),
                "sha256": sha256,
                "source_text": metadata["source_text"],
                "target_text": metadata["target_text"],
                "language": metadata["language"],
                "script": metadata["script"],
                "font_confidence": metadata["font_analysis"]["confidence"],
                "style_tags": metadata["style_tags"],
                "effect_tags": metadata["effect_tags"],
            }
            (staged_case / "case.md").write_text(
                _case_markdown(metadata, case_id, archive_day, sha256, image_name),
                encoding="utf-8",
            )
            _write_pending_marker(staged_case)
            staged_index = staging_parent / "index.jsonl"
            staged_index.write_text(
                "".join(
                    json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                    for item in records + [record]
                ),
                encoding="utf-8",
            )

            cases_directory.mkdir(exist_ok=True)
            case_replaced = False
            index_replaced = False
            try:
                os.replace(str(staged_case), str(destination))
                case_replaced = True
                os.replace(str(staged_index), str(index_path))
                index_replaced = True
            except BaseException:
                if case_replaced and not index_replaced:
                    shutil.rmtree(destination, ignore_errors=True)
                if not had_cases_directory:
                    try:
                        cases_directory.rmdir()
                    except OSError:
                        pass
                raise
            (destination / PENDING_MARKER).unlink()
            return {
                "case_id": case_id,
                "case_dir": str(destination.resolve()),
                "index_path": str(index_path.resolve()),
            }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Archive a lettering analysis case.")
    parser.add_argument("--metadata", required=True, help="Path to metadata JSON.")
    parser.add_argument("--image", required=True, help="Path to the reference image.")
    parser.add_argument(
        "--skill-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Skill package root (defaults to this script's package).",
    )
    arguments = parser.parse_args(argv)
    try:
        with Path(arguments.metadata).open(encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
        result = archive_case(metadata, arguments.image, arguments.skill_root)
    except (ArchiveError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print("archive failed: {}".format(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
