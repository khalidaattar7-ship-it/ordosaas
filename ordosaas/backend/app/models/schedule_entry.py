"""ScheduleEntry ORM model."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric
from app.models._types import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ScheduleEntry(BaseModel):
    __tablename__ = "schedule_entries"
    __table_args__ = (
        CheckConstraint("start_time >= 0", name="ck_entry_start"),
        CheckConstraint("end_time > start_time", name="ck_entry_end"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    resolution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("operations.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id"), nullable=False
    )
    window_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("time_windows.id"), nullable=True
    )
    start_time: Mapped[int] = mapped_column(Integer, nullable=False)
    end_time: Mapped[int] = mapped_column(Integer, nullable=False)
    setup_from_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True
    )
    setup_start_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    setup_end_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    setup_duration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    job_completion_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_tardiness: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
