import hashlib
from pathlib import Path


SUPPORTED_EXTENSIONS = {".txt", ".md"}


def parse_file(file_path: str) -> str:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Supported types: {SUPPORTED_EXTENSIONS}")

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if path.stat().st_size == 0:
        raise ValueError(f"File is empty: {file_path}")

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"Corrupted file (not valid UTF-8 text): {file_path}") from e


def compute_md5(file_path: str) -> str:
    return hashlib.md5(Path(file_path).read_bytes()).hexdigest()


def get_file_metadata(file_path: str) -> dict:
    path = Path(file_path)
    return {
        "filename": path.name,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "md5_hash": compute_md5(file_path),
    }
