"""SolutionComparison ORM model."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String
from app.models._types import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SolutionComparison(BaseModel):
    __tablename__ = "solution_comparisons"
    __table_args__ = (
        CheckConstraint("winner IN ('A','B') OR winner IS NULL", name="ck_comparison_winner"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    resolution_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolutions.id"), nullable=False
    )
    resolution_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolutions.id"), nullable=False
    )
    delta_weighted_tardiness: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    delta_jobs_late: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delta_machine_utilization: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    winner: Mapped[str | None] = mapped_column(String(1), nullable=True)
