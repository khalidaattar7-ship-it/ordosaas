"""SetupTime ORM model."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SetupTime(BaseModel):
    __tablename__ = "setup_times"
    __table_args__ = (
        UniqueConstraint("instance_id", "from_job_id", "to_job_id", "machine_id", name="uq_setup_unique"),
        CheckConstraint("duration >= 0", name="ck_setup_duration"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problem_instances.id", ondelete="CASCADE"), nullable=False
    )
    from_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    to_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id"), nullable=False
    )
    duration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
