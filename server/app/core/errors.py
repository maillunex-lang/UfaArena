from fastapi import HTTPException


class GameError(HTTPException):
    """Domain error with a stable machine-readable code for the client."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(status_code=status, detail={"code": code, "message": message})
