"""Tenant ORM model."""
from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedModel


class Tenant(TimestampedModel):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("default_wr BETWEEN 1 AND 50", name="ck_tenant_default_wr"),
        CheckConstraint("default_timeout BETWEEN 5 AND 300", name="ck_tenant_default_timeout"),
        CheckConstraint("default_strategy IN ('auto','cpsat','lns','atcs')", name="ck_tenant_default_strategy"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    default_wr: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    default_timeout: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    default_strategy: Mapped[str] = mapped_column(String(10), default="auto", nullable=False)
    max_jobs_per_instance: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    max_machines_per_instance: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    max_instances_stored: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Africa/Casablanca", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    machines = relationship("Machine", back_populates="tenant", cascade="all, delete-orphan")
    problem_instances = relationship("ProblemInstance", back_populates="tenant", cascade="all, delete-orphan")
