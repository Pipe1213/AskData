from typing import Any

from app.core.masking import mask_secrets, mask_value


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
        # Set by the query pipeline: LLM usage spent before the failure (a QueryUsage).
        self.usage: Any = None

    def to_error_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": mask_secrets(self.message),
            "details": mask_value(
                {
                    "stage": self.stage,
                    "retryable": self.retryable,
                    **self.details,
                }
            ),
        }
