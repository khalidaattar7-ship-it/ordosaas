"""Job ORM model."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Job(BaseModel):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("instance_id", "external_id", name="uq_job_instance_external"),
        CheckConstraint("deadline > 0", name="ck_job_deadline"),
        CheckConstraint("weight > 0", name="ck_job_weight"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problem_instances.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    deadline: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(10, 4), default=1.0, nullable=False)

    instance = relationship("ProblemInstance", back_populates="jobs")
    operations = relationship("Operation", back_populates="job", cascade="all, delete-orphan")
