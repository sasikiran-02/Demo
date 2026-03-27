from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class AppError(Exception):
    stage: str
    code: str
    message: str
    status_code: int
    details: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "stage": self.stage,
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "stage": "request",
                    "code": "invalid_request",
                    "message": "Request validation failed.",
                    "details": {"errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "stage": "internal",
                    "code": "internal_error",
                    "message": "Unexpected internal error.",
                    "details": None,
                }
            },
        )
