import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FoodEntry(Base):
    __tablename__ = "food_entries"
    __table_args__ = (
        UniqueConstraint(
            "source", "external_id", name="uq_food_entries_source_external_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(255))
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    local_date: Mapped[date] = mapped_column(Date, index=True)
    timezone: Mapped[str] = mapped_column(String(64))
    meal: Mapped[str] = mapped_column(String(32))
    food_name: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    nutrients: Mapped[list["NutrientValue"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", lazy="selectin"
    )


class NutrientValue(Base):
    __tablename__ = "nutrient_values"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("food_entries.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    unit: Mapped[str] = mapped_column(String(16))

    entry: Mapped[FoodEntry] = relationship(back_populates="nutrients")


class DailyGoal(Base):
    __tablename__ = "daily_goals"
    __table_args__ = (
        UniqueConstraint(
            "source", "local_date", name="uq_daily_goals_source_local_date"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32))
    local_date: Mapped[date] = mapped_column(Date, index=True)
    timezone: Mapped[str] = mapped_column(String(64))
    activity_energy_kcal: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    consume_activity_energy: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    values: Mapped[list["DailyGoalValue"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan", lazy="selectin"
    )


class DailyGoalValue(Base):
    __tablename__ = "daily_goal_values"

    daily_goal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("daily_goals.id", ondelete="CASCADE"), primary_key=True
    )
    variant: Mapped[str] = mapped_column(String(16), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    unit: Mapped[str] = mapped_column(String(16))

    goal: Mapped[DailyGoal] = relationship(back_populates="values")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    range_start: Mapped[date] = mapped_column(Date)
    range_end: Mapped[date] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    items_seen: Mapped[int] = mapped_column(Integer, default=0)
    items_upserted: Mapped[int] = mapped_column(Integer, default=0)
    items_deleted: Mapped[int] = mapped_column(Integer, default=0)
    goals_seen: Mapped[int] = mapped_column(Integer, default=0)
    goals_upserted: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
