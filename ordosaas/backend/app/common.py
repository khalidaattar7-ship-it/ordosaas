"""Shared response schemas used across modules."""
import uuid

from pydantic import BaseModel


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str


def paginate_meta(page: int, per_page: int, total: int) -> PaginationMeta:
    total_pages = (total + per_page - 1) // per_page if per_page else 0
    return PaginationMeta(
        page=page, per_page=per_page, total=total, total_pages=total_pages
    )
