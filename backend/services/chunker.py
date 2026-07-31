import re
import tiktoken


ENCODING = tiktoken.get_encoding("cl100k_base")
DEFAULT_MAX_TOKENS = 800
DEFAULT_OVERLAP_TOKENS = 100
DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " "]


def count_tokens(text: str) -> int:
    return len(ENCODING.encode(text))


def chunk_text(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    separators: list[str] | None = None,
) -> list[dict]:
    if separators is None:
        separators = DEFAULT_SEPARATORS

    if not text.strip():
        return []

    chunks = []
    raw_chunks = _split_text(text, max_tokens, separators)

    for i, raw in enumerate(raw_chunks):
        tokens = count_tokens(raw)
        if i > 0 and overlap_tokens > 0:
            prev_text = raw_chunks[i - 1]
            overlap_words = prev_text.split()[-overlap_tokens:] if len(prev_text.split()) > overlap_tokens else prev_text.split()
            raw = " ".join(overlap_words) + "\n" + raw if overlap_words else raw
            tokens = count_tokens(raw)

        chunks.append({
            "index": i,
            "text": raw.strip(),
            "token_count": tokens,
        })

    return chunks


def _split_text(text: str, max_tokens: int, separators: list[str]) -> list[str]:
    splits = _split_once(text, separators[0]) if separators else [text]
    result = []

    for split in splits:
        if count_tokens(split) <= max_tokens:
            result.append(split)
        elif len(separators) > 1:
            result.extend(_split_text(split, max_tokens, separators[1:]))
        else:
            result.extend(_split_by_tokens(split, max_tokens))

    return result


def _split_once(text: str, separator: str) -> list[str]:
    if separator == " ":
        return [text]
    return [s.strip() for s in re.split(re.escape(separator), text) if s.strip()]


def _split_by_tokens(text: str, max_tokens: int) -> list[str]:
    words = text.split()
    chunks = []
    current = []
    current_tokens = 0

    for word in words:
        word_tokens = count_tokens(word + " ")
        if current_tokens + word_tokens > max_tokens and current:
            chunks.append(" ".join(current))
            current = []
            current_tokens = 0
        current.append(word)
        current_tokens += word_tokens

    if current:
        chunks.append(" ".join(current))

    return chunks if chunks else [text]
