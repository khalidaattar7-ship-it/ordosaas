"""TimeWindow ORM model."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String
from app.models._types import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class TimeWindow(BaseModel):
    __tablename__ = "time_windows"
    __table_args__ = (
        CheckConstraint("window_index >= 1", name="ck_window_index"),
        CheckConstraint("t_start >= 0", name="ck_window_tstart"),
        CheckConstraint("t_end > t_start", name="ck_window_tend"),
        CheckConstraint("nb_jobs > 0", name="ck_window_nb_jobs"),
        CheckConstraint(
            "status IN ('pending','running','optimal','feasible','atcs_fallback','error')",
            name="ck_window_status",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    resolution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False
    )
    window_index: Mapped[int] = mapped_column(Integer, nullable=False)
    t_start: Mapped[int] = mapped_column(Integer, nullable=False)
    t_end: Mapped[int] = mapped_column(Integer, nullable=False)
    nb_jobs: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    method_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recursion_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    local_weighted_tardiness: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
