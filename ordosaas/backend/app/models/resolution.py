"""Resolution ORM model."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedModel


class Resolution(TimestampedModel):
    __tablename__ = "resolutions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','partial','failed','cancelled')",
            name="ck_resolution_status",
        ),
        CheckConstraint("method_used IN ('cpsat','lns','atcs') OR method_used IS NULL", name="ck_resolution_method"),
        CheckConstraint("progress_pct BETWEEN 0 AND 100", name="ck_resolution_progress"),
        CheckConstraint("current_phase BETWEEN 0 AND 4", name="ck_resolution_phase"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problem_instances.id", ondelete="CASCADE"), nullable=False
    )
    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("solver_configs.id"), nullable=False
    )
    triggered_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    method_used: Mapped[str | None] = mapped_column(String(10), nullable=True)
    total_weighted_tardiness: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    nb_jobs_late: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nb_jobs_on_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_tardiness: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    machine_utilization_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    total_setup_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    atcs_weighted_tardiness: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    improvement_vs_atcs_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_phase: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    instance = relationship("ProblemInstance", back_populates="resolutions")
