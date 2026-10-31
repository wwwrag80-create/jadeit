"""أخطاء النظام برسائل عربية واضحة تصل كما هي إلى الواجهة."""
from __future__ import annotations


class AppError(Exception):
    status = 400

    def __init__(self, message: str, code: str = "invalid", details=None, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details
        if status is not None:
            self.status = status

    def to_dict(self):
        out = {"code": self.code, "message": self.message}
        if self.details is not None:
            out["details"] = self.details
        return out


class ValidationError(AppError):
    status = 422

    def __init__(self, message: str, details=None, code: str = "validation"):
        super().__init__(message, code=code, details=details)


class NotFound(AppError):
    status = 404

    def __init__(self, message: str = "العنصر المطلوب غير موجود"):
        super().__init__(message, code="not_found")


class Forbidden(AppError):
    status = 403

    def __init__(self, message: str = "لا تملك صلاحية تنفيذ هذه العملية"):
        super().__init__(message, code="forbidden")


class Unauthorized(AppError):
    status = 401

    def __init__(self, message: str = "يجب تسجيل الدخول"):
        super().__init__(message, code="unauthorized")


class Conflict(AppError):
    status = 409

    def __init__(self, message: str, details=None, code: str = "conflict"):
        super().__init__(message, code=code, details=details)
