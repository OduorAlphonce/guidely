"""Unit tests for the document parser (issue #31).

Covers txt/md parsing, unsupported types, empty and missing files, and
corrupted (non-UTF-8) input, plus md5 and metadata helpers.

Run from the repo root:
    python backend/tests/test_parser.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["OPENROUTER_API_KEY"] = ""

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.parser import (
    SUPPORTED_EXTENSIONS,
    compute_md5,
    get_file_metadata,
    parse_file,
)

PASS = 0
FAIL = 0
FAILURES = []

SAMPLE_TEXT = "# Onboarding\n\nWelcome to the team.\n"


def check(description, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {description}")
    else:
        FAIL += 1
        FAILURES.append(description)
        print(f"  [FAIL] {description}")


def test_txt_parsing():
    print("\nTest 1: .txt parsing")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_parser_txt_"))
    try:
        p = tmpdir / "notes.txt"
        p.write_text(SAMPLE_TEXT, encoding="utf-8")

        content = parse_file(str(p))
        check("returns the raw text", content == SAMPLE_TEXT)
        check("content is a non-empty string", isinstance(content, str) and len(content) > 0)

        # Extension matching is case-insensitive.
        upper = tmpdir / "notes.TXT"
        upper.write_text("upper case", encoding="utf-8")
        check("parses uppercase .TXT", parse_file(str(upper)) == "upper case")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_md_parsing():
    print("\nTest 2: .md parsing")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_parser_md_"))
    try:
        p = tmpdir / "readme.md"
        p.write_text("# Title\n\nSome *markdown* body.", encoding="utf-8")

        content = parse_file(str(p))
        check("returns the markdown text verbatim", content == "# Title\n\nSome *markdown* body.")
        check("md is a supported extension", ".md" in SUPPORTED_EXTENSIONS)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_unsupported_type():
    print("\nTest 3: unsupported file types raise ValueError")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_parser_unsupported_"))
    try:
        for name in ("doc.pdf", "sheet.csv", "file.json", "img.png"):
            p = tmpdir / name
            p.write_text("ignored", encoding="utf-8")
            try:
                parse_file(str(p))
                check(f"{name} is rejected", False)
            except ValueError as e:
                check(f"{name} is rejected with a clear message", "Unsupported" in str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_missing_file():
    print("\nTest 4: missing files raise FileNotFoundError")
    try:
        parse_file("/nonexistent/guidely/no-file.txt")
        check("missing file raises FileNotFoundError", False)
    except FileNotFoundError as e:
        check("missing file raises FileNotFoundError", "File not found" in str(e))
    except Exception:
        check("missing file raises FileNotFoundError", False)


def test_empty_file():
    print("\nTest 5: empty files raise ValueError")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_parser_empty_"))
    try:
        p = tmpdir / "empty.txt"
        p.touch()
        try:
            parse_file(str(p))
            check("empty file is rejected", False)
        except ValueError as e:
            check("empty file is rejected with a clear message", "empty" in str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_corrupted_file():
    print("\nTest 6: non-UTF-8 (corrupted) files raise ValueError")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_parser_corrupt_"))
    try:
        p = tmpdir / "corrupt.txt"
        p.write_bytes(b"\xff\xfe\x00\x80\x99")
        try:
            parse_file(str(p))
            check("corrupted file is rejected", False)
        except ValueError as e:
            check("corrupted file is rejected with a clear message", "UTF-8" in str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_md5_and_metadata():
    print("\nTest 7: compute_md5 and get_file_metadata")
    tmpdir = Path(tempfile.mkdtemp(prefix="guidely_parser_meta_"))
    try:
        p = tmpdir / "meta.txt"
        p.write_text("metadata content", encoding="utf-8")
        from hashlib import md5

        expected = md5(b"metadata content").hexdigest()
        check("md5 matches hashlib md5 of the bytes", compute_md5(str(p)) == expected)

        meta = get_file_metadata(str(p))
        check("metadata has filename", meta["filename"] == "meta.txt")
        check("metadata has the absolute path", meta["path"] == str(p.resolve()))
        check("metadata has size_bytes", meta["size_bytes"] == len("metadata content"))
        check("metadata has md5_hash", meta["md5_hash"] == expected)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    print("=" * 64)
    print("Guidely parser — unit tests (issue #31)")
    print("=" * 64)

    test_txt_parsing()
    test_md_parsing()
    test_unsupported_type()
    test_missing_file()
    test_empty_file()
    test_corrupted_file()
    test_md5_and_metadata()

    print("\n" + "=" * 64)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("Failed checks:")
        for f in FAILURES:
            print(f"  - {f}")
    print("=" * 64)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
