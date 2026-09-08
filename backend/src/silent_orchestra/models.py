from datetime import datetime, timezone
from typing import Annotated, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ponytail: SQLAlchemy copies the mapped_column out of an Annotated alias per
# use, so these replace the repeated column declarations. Mapped[T] already
# means NOT NULL and Mapped[T | None] means NULL - no explicit nullable needed.
Pk = Annotated[str, mapped_column(String(36), primary_key=True)]
UserFk = Annotated[str, mapped_column(ForeignKey("users.id", ondelete="CASCADE"))]
PatternFk = Annotated[str, mapped_column(ForeignKey("gesture_patterns.id", ondelete="CASCADE"))]
Timestamp = Annotated[datetime, mapped_column(DateTime(timezone=True), default=utcnow)]


class User(Base):
    __tablename__ = "users"

    id: Mapped[Pk]
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[Timestamp]

    contexts: Mapped[list["Context"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Context(Base):
    __tablename__ = "contexts"
    __table_args__ = (
        CheckConstraint("activity IN ('presentation','music')", name="ck_context_activity"),
        Index("ix_contexts_user_activity", "user_id", "activity"),
    )

    id: Mapped[Pk]
    user_id: Mapped[UserFk]
    active_app: Mapped[str] = mapped_column(String(100))
    activity: Mapped[str] = mapped_column(String(32))
    space: Mapped[str] = mapped_column(String(100), default="unspecified")
    device: Mapped[str] = mapped_column(String(100), default="laptop")
    captured_at: Mapped[Timestamp]

    user: Mapped[User] = relationship(back_populates="contexts")
    observations: Mapped[list["GestureObservation"]] = relationship(
        back_populates="context", cascade="all, delete-orphan"
    )


class GestureObservation(Base):
    __tablename__ = "gesture_observations"
    __table_args__ = (
        CheckConstraint("duration_ms >= 0", name="ck_observation_duration"),
        CheckConstraint("frame_stored = 0", name="ck_raw_frame_never_stored"),
        Index("ix_observations_user_gesture", "user_id", "gesture_key"),
        Index("ix_observations_detected_at", "detected_at"),
    )

    id: Mapped[Pk]
    user_id: Mapped[UserFk]
    context_id: Mapped[str] = mapped_column(ForeignKey("contexts.id", ondelete="CASCADE"))
    gesture_key: Mapped[str] = mapped_column(String(120))
    gesture_embedding: Mapped[list[float]] = mapped_column(JSON)
    motion_type: Mapped[str] = mapped_column(String(50))
    direction: Mapped[str] = mapped_column(String(30), default="none")
    duration_ms: Mapped[int]
    frame_stored: Mapped[bool] = mapped_column(default=False)
    detected_at: Mapped[Timestamp]

    context: Mapped[Context] = relationship(back_populates="observations")
    # Without the cascade the ORM nulls out actions.observation_id on delete,
    # which the NOT NULL column rejects and a demo reset then fails on.
    action: Mapped["Action | None"] = relationship(
        back_populates="observation", uselist=False, cascade="all, delete-orphan"
    )


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (
        CheckConstraint("executed_by IN ('USER','AGENT')", name="ck_action_executor"),
        Index("ix_actions_user_type", "user_id", "action_type"),
    )

    id: Mapped[Pk]
    user_id: Mapped[UserFk]
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("gesture_observations.id", ondelete="CASCADE"), unique=True
    )
    action_type: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(100))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    executed_by: Mapped[str] = mapped_column(String(16), default="USER")
    executed_at: Mapped[Timestamp]

    observation: Mapped[GestureObservation] = relationship(back_populates="action")


class GesturePattern(Base):
    __tablename__ = "gesture_patterns"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_pattern_confidence"),
        CheckConstraint("observation_count >= 0", name="ck_pattern_count"),
        CheckConstraint("status IN ('CANDIDATE','ACTIVE','REJECTED')", name="ck_pattern_status"),
        CheckConstraint("context_scope IN ('presentation','music')", name="ck_pattern_context"),
        UniqueConstraint(
            "user_id", "gesture_key", "context_scope", "intent", name="uq_personal_gesture_memory"
        ),
        Index("ix_patterns_memory_lookup", "user_id", "context_scope", "status"),
    )

    id: Mapped[Pk]
    user_id: Mapped[UserFk]
    gesture_key: Mapped[str] = mapped_column(String(120))
    gesture_embedding: Mapped[list[float]] = mapped_column(JSON)
    motion_type: Mapped[str] = mapped_column(String(50))
    direction: Mapped[str] = mapped_column(String(30))
    intent: Mapped[str] = mapped_column(String(64))
    context_scope: Mapped[str] = mapped_column(String(32))
    target: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(default=0.0)
    observation_count: Mapped[int] = mapped_column(default=0)
    positive_feedback_count: Mapped[int] = mapped_column(default=0)
    negative_feedback_count: Mapped[int] = mapped_column(default=0)
    auto_execute: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(16), default="CANDIDATE")
    created_at: Mapped[Timestamp]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    suggestions: Mapped[list["AgentSuggestion"]] = relationship(
        back_populates="pattern", cascade="all, delete-orphan"
    )
    executions: Mapped[list["Execution"]] = relationship(
        back_populates="pattern", cascade="all, delete-orphan"
    )


class AgentSuggestion(Base):
    __tablename__ = "agent_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','ACCEPTED','REJECTED','MODIFIED')", name="ck_suggestion_status"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_suggestion_confidence"),
        Index("ix_suggestions_user_status", "user_id", "status"),
    )

    id: Mapped[Pk]
    user_id: Mapped[UserFk]
    gesture_pattern_id: Mapped[PatternFk]
    suggested_intent: Mapped[str] = mapped_column(String(64))
    modified_intent: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float]
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    created_at: Mapped[Timestamp]
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pattern: Mapped[GesturePattern] = relationship(back_populates="suggestions")


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_execution_confidence"),
        CheckConstraint("execution_mode IN ('DRY_RUN','OS')", name="ck_execution_mode"),
        CheckConstraint("status IN ('SIMULATED','SUCCEEDED','FAILED')", name="ck_execution_status"),
        Index("ix_executions_user_time", "user_id", "executed_at"),
    )

    id: Mapped[Pk]
    user_id: Mapped[UserFk]
    gesture_pattern_id: Mapped[PatternFk]
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("gesture_observations.id", ondelete="CASCADE")
    )
    intent: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(100))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float]
    execution_mode: Mapped[str] = mapped_column(String(16), default="DRY_RUN")
    status: Mapped[str] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[Timestamp]

    pattern: Mapped[GesturePattern] = relationship(back_populates="executions")
    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "feedback_type IN ('CORRECT','WRONG_ACTION','ACCIDENTAL_GESTURE','IGNORE')",
            name="ck_feedback_type",
        ),
        Index("ix_feedback_pattern_time", "gesture_pattern_id", "created_at"),
    )

    id: Mapped[Pk]
    user_id: Mapped[UserFk]
    gesture_pattern_id: Mapped[PatternFk]
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.id", ondelete="CASCADE"), unique=True
    )
    feedback_type: Mapped[str] = mapped_column(String(32))
    corrected_intent: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[Timestamp]

    execution: Mapped[Execution] = relationship(back_populates="feedback")
