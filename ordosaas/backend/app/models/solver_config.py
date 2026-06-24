"""SolverConfig ORM model."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String
from app.models._types import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SolverConfig(BaseModel):
    __tablename__ = "solver_configs"
    __table_args__ = (
        CheckConstraint("wr BETWEEN 1 AND 50", name="ck_cfg_wr"),
        CheckConstraint("strategy IN ('auto','cpsat','lns','atcs')", name="ck_cfg_strategy"),
        CheckConstraint("cpsat_timeout BETWEEN 5 AND 300", name="ck_cfg_cpsat_timeout"),
        CheckConstraint("max_jobs_per_window BETWEEN 5 AND 200", name="ck_cfg_max_jpw"),
        CheckConstraint("min_jobs_per_window BETWEEN 2 AND 20", name="ck_cfg_min_jpw"),
        CheckConstraint("max_recursion_depth BETWEEN 1 AND 8", name="ck_cfg_depth"),
        CheckConstraint("max_iterations BETWEEN 1 AND 20", name="ck_cfg_iterations"),
        CheckConstraint("junction_radius BETWEEN 2 AND 30", name="ck_cfg_junction"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problem_instances.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    wr: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    strategy: Mapped[str] = mapped_column(String(10), default="auto", nullable=False)
    cpsat_timeout: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    max_jobs_per_window: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    min_jobs_per_window: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_recursion_depth: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    max_iterations: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    epsilon: Mapped[float] = mapped_column(Numeric(6, 4), default=0.01, nullable=False)
    junction_radius: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    k1: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    k2: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
