"""ProblemInstance ORM model."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from app.models._types import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedModel


class ProblemInstance(TimestampedModel):
    __tablename__ = "problem_instances"
    __table_args__ = (
        CheckConstraint("status IN ('draft','solving','solved','error')", name="ck_instance_status"),
        CheckConstraint("import_source IN ('csv','manual','demo')", name="ck_instance_import_source"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    nb_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nb_machines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nb_operations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nb_setups: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    import_source: Mapped[str] = mapped_column(String(20), default="csv", nullable=False)
    raw_jobs_csv: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_operations_csv: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_setups_csv: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant", back_populates="problem_instances")
    jobs = relationship("Job", back_populates="instance", cascade="all, delete-orphan")
    resolutions = relationship("Resolution", back_populates="instance", cascade="all, delete-orphan")
