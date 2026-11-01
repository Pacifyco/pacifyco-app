"""One error format for every API response:

    {"error": {"code": "not_found", "message": "Not found", "details": null}}

`code` is stable and meant for the web app to branch on; `message` is safe to show a user.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("pacifyco.api")


class AppError(Exception):
    """Raise from routers and services for expected failures (business rules, permissions)."""

    def __init__(self, status_code: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def _code_for_status(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).name.lower()
    except ValueError:
        return "error"


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    response = error_response(exc.status_code, _code_for_status(exc.status_code), str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Leave out the submitted values ("input") so they never come back in responses or logs.
    details = [
        {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]} for error in exc.errors()
    ]
    return error_response(422, "validation_error", "Some fields need fixing", details)


async def _unhandled_error(_: Request, exc: Exception) -> JSONResponse:
    # Sentry records the exception; the client only gets a generic message.
    logger.exception("Unhandled error", exc_info=exc)
    return error_response(500, "internal_error", "Something went wrong on our side. Please try again.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
