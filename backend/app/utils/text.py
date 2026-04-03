import re

TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "last",
    "me",
    "of",
    "on",
    "show",
    "that",
    "the",
    "this",
    "to",
    "what",
    "which",
    "with",
}


def tokenize_text(value: str) -> list[str]:
    tokens = TOKEN_PATTERN.findall(value.lower())
    return [_normalize_token(token) for token in tokens if _normalize_token(token)]


def significant_tokens(value: str) -> set[str]:
    return {token for token in tokenize_text(value) if token not in STOPWORDS}


def _normalize_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 3:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
        return token[:-1]
    return token
