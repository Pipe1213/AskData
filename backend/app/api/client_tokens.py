from fastapi import Header, HTTPException, status

CLIENT_TOKEN_HEADER = "X-AskData-Client-Token"


def get_optional_client_token(
    client_token: str | None = Header(default=None, alias=CLIENT_TOKEN_HEADER),
) -> str | None:
    normalized = client_token.strip() if client_token else ""
    return normalized or None


def require_client_token(
    client_token: str | None = Header(default=None, alias=CLIENT_TOKEN_HEADER),
) -> str:
    normalized = client_token.strip() if client_token else ""
    if normalized:
        return normalized

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{CLIENT_TOKEN_HEADER} header is required.",
    )

