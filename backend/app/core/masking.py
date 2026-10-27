import logging
import re
from collections.abc import Iterable
from typing import Any

MASK = "***"

# postgresql://user:secret@host -> postgresql://user:***@host
_URL_CREDENTIALS = re.compile(r"(?P<prefix>[A-Za-z][A-Za-z0-9+.-]*://[^:/@\s]*:)[^@\s]*@")
# password=secret, PGPASSWORD=secret, password='se cret'
_KEY_VALUE = re.compile(r"(?i)(?P<key>\b\w*(?:password|passwd|pwd)\s*=\s*)('[^']*'|\"[^\"]*\"|[^\s&;,]+)")
# "password": "secret"
_JSON_FIELD = re.compile(r"(?i)(?P<key>[\"']\w*password[\"']\s*:\s*)([\"'])[^\"']*\2")


def mask_secrets(text: str, secrets: Iterable[str | None] = ()) -> str:
    """Hide passwords in connection URLs, key=value pairs, JSON fields and any known secret."""
    masked = _URL_CREDENTIALS.sub(lambda match: f"{match.group('prefix')}{MASK}@", text)
    masked = _KEY_VALUE.sub(lambda match: f"{match.group('key')}{MASK}", masked)
    masked = _JSON_FIELD.sub(lambda match: f"{match.group('key')}\"{MASK}\"", masked)
    for secret in secrets:
        # Very short values would mask unrelated text; the patterns above still cover them.
        if secret and len(secret) >= 4:
            masked = masked.replace(secret, MASK)
    return masked


def mask_value(value: Any, secrets: Iterable[str | None] = ()) -> Any:
    """mask_secrets applied to every string inside nested dicts, lists and tuples."""
    secrets = list(secrets)
    if isinstance(value, str):
        return mask_secrets(value, secrets)
    if isinstance(value, dict):
        return {key: mask_value(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(mask_value(item, secrets) for item in value)
    return value


class MaskSecretsFilter(logging.Filter):
    """Log filter that masks secrets in the message and in formatted tracebacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = mask_secrets(message)
        if masked != message:
            record.msg = masked
            record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = mask_secrets(logging.Formatter().formatException(record.exc_info))
        return True
