import logging

from app.core.masking import MaskSecretsFilter


def setup_logging(log_level: str) -> None:
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        logging.basicConfig(
            level=log_level.upper(),
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
    root_logger.setLevel(log_level.upper())

    for logger in (root_logger, *(logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access"))):
        for handler in logger.handlers:
            if not any(isinstance(existing, MaskSecretsFilter) for existing in handler.filters):
                handler.addFilter(MaskSecretsFilter())
