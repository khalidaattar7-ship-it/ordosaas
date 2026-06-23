"""Shared FastAPI dependencies (auth, tenant scoping)."""
from fastapi import Depends

from app.database import get_db

__all__ = ["get_db"]
