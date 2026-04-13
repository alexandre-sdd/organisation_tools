import re
import unicodedata


def tokenize(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if len(tok) >= 4]


def normalize_key(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
    return normalized


def tokens_without_stopwords(text: str, stopwords: set[str]) -> set[str]:
    return {tok for tok in normalize_key(text).split() if tok and tok not in stopwords}


def match_entity(
    a: str,
    b: str,
    stopwords: set[str],
    min_token_overlap: int = 1,
) -> bool:
    na = normalize_key(a)
    nb = normalize_key(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    tokens_a = tokens_without_stopwords(a, stopwords)
    tokens_b = tokens_without_stopwords(b, stopwords)
    overlap = len(tokens_a.intersection(tokens_b))
    required = max(1, min_token_overlap)
    return overlap >= required


def is_nyc(location: str) -> bool:
    loc = normalize_key(location)
    return "new york" in loc or "nyc" in loc or loc.endswith(" ny")


def compact_role_title(title: str) -> str:
    """Make a role title shorter/quote-safe without inventing facts."""
    if not title:
        return ""
    text = " ".join(title.split()).strip()
    for sep in [" | ", " — ", " – ", " - ", ","]:
        if sep in text:
            text = text.split(sep, 1)[0].strip()
    if len(text) > 60:
        text = text[:57].rstrip() + "..."
    return text
