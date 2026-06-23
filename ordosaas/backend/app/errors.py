"""Standardized application exceptions returning {error, message, detail}."""
from fastapi import HTTPException, status


class AppError(HTTPException):
    """Base error carrying a machine-readable code plus optional detail."""

    def __init__(self, status_code: int, code: str, message: str, detail=None):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.extra = detail or {}


def not_found(message="Ressource introuvable", detail=None):
    return AppError(status.HTTP_404_NOT_FOUND, "not_found", message, detail)


def conflict(message="Conflit", detail=None):
    return AppError(status.HTTP_409_CONFLICT, "conflict", message, detail)


def bad_request(message="Requête invalide", detail=None):
    return AppError(status.HTTP_400_BAD_REQUEST, "bad_request", message, detail)


def unauthorized(message="Non authentifié", detail=None):
    return AppError(status.HTTP_401_UNAUTHORIZED, "unauthorized", message, detail)


def forbidden(message="Accès refusé", detail=None):
    return AppError(status.HTTP_403_FORBIDDEN, "forbidden", message, detail)
