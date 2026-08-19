"""Document tag storage.

Persists tags per document in a JSON file so they survive restarts.
"""

import json
import threading
from pathlib import Path


class TagStore:
    def __init__(self, path: str):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._tags: dict[str, list[str]] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._tags = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                self._tags = {}

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._tags, indent=2))
        tmp.replace(self._path)

    def get_tags(self, doc_id: str) -> list[str]:
        with self._lock:
            return list(self._tags.get(doc_id, []))

    def set_tags(self, doc_id: str, tags: list[str]):
        with self._lock:
            self._tags[doc_id] = list(dict.fromkeys(tags))
            self._save()

    def add_tag(self, doc_id: str, tag: str):
        with self._lock:
            current = self._tags.get(doc_id, [])
            if tag not in current:
                current.append(tag)
                self._tags[doc_id] = current
                self._save()

    def remove_tag(self, doc_id: str, tag: str):
        with self._lock:
            current = self._tags.get(doc_id, [])
            if tag in current:
                current.remove(tag)
                self._tags[doc_id] = current
                self._save()

    def list_all_tags(self) -> list[str]:
        with self._lock:
            all_tags = set()
            for tags in self._tags.values():
                all_tags.update(tags)
            return sorted(all_tags)

    def find_by_tag(self, tag: str) -> list[str]:
        with self._lock:
            return [doc_id for doc_id, tags in self._tags.items() if tag in tags]

    def remove_document(self, doc_id: str):
        with self._lock:
            self._tags.pop(doc_id, None)
            self._save()

    def all_tags(self) -> dict[str, list[str]]:
        with self._lock:
            return dict(self._tags)
