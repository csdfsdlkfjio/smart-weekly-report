"""业务异常：由 main.py 统一映射为 JSON 响应。"""

from __future__ import annotations


class AppError(Exception):
    """所有可预期业务异常的基类。"""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthenticated"


class PermissionDenied(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class StateTransitionError(AppError):
    status_code = 400
    code = "invalid_transition"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"
