"""Pydantic schemas for the machines module."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class MachineResponse(BaseModel):
    id: uuid.UUID
    external_id: str
    name: str
    description: str | None = None
    status: str

    model_config = {"from_attributes": True}


class MachineListResponse(BaseModel):
    data: list[MachineResponse]


class CreateMachineRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class PatchMachineRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    status: Literal["active", "maintenance", "inactive"] | None = None
