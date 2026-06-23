"""Machine ORM model."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedModel


class Machine(TimestampedModel):
    __tablename__ = "machines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_machine_tenant_external"),
        CheckConstraint("status IN ('active','maintenance','inactive')", name="ck_machine_status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    tenant = relationship("Tenant", back_populates="machines")
