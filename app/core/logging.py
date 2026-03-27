from __future__ import annotations

import logging
import re
from typing import Any


class SensitiveDataFilter(logging.Filter):
    _patterns = [
        re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]+)", re.IGNORECASE),
        re.compile(r'("access_token"\s*:\s*")[^"]+(")', re.IGNORECASE),
        re.compile(r'("client_secret"\s*:\s*")[^"]+(")', re.IGNORECASE),
        re.compile(r'("authorization"\s*:\s*")[^"]+(")', re.IGNORECASE),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self._patterns:
            message = pattern.sub(r"\1[REDACTED]\2", message)

        record.msg = message
        record.args = ()
        return True


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not any(isinstance(existing_filter, SensitiveDataFilter) for existing_filter in handler.filters):
            handler.addFilter(SensitiveDataFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
