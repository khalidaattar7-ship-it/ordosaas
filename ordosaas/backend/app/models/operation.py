"""Operation ORM model."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from app.models._types import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Operation(BaseModel):
    __tablename__ = "operations"
    __table_args__ = (
        UniqueConstraint("job_id", "position", name="uq_operation_job_position"),
        UniqueConstraint("job_id", "machine_id", name="uq_operation_job_machine"),
        CheckConstraint("position >= 1", name="ck_operation_position"),
        CheckConstraint("duration > 0", name="ck_operation_duration"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)

    job = relationship("Job", back_populates="operations")
