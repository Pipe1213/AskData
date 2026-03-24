from typing import Any


class QueryPipelineError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        stage: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.retryable = retryable
        self.details = details or {}

    def to_error_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": {
                "stage": self.stage,
                "retryable": self.retryable,
                **self.details,
            },
        }
