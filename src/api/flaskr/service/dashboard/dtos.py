"""DTOs for teacher-facing analytics dashboard."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from flaskr.common.swagger import register_schema_to_swagger


@register_schema_to_swagger
class DashboardEmptyDTO(BaseModel):
    """Placeholder DTO for initial module wiring."""

    ok: bool = Field(default=True, description="Always true", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {"ok": bool(self.ok)}


@register_schema_to_swagger
class DashboardOutlineDTO(BaseModel):
    """Published outline item exposed to the dashboard."""

    outline_item_bid: str = Field(
        ..., description="Outline item business identifier", required=False
    )
    title: str = Field(..., description="Outline title", required=False)
    type: int = Field(..., description="Outline type", required=False)
    hidden: bool = Field(default=False, description="Hidden flag", required=False)
    parent_bid: str = Field(
        default="", description="Parent outline bid", required=False
    )
    position: str = Field(default="", description="Outline position", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {
            "outline_item_bid": self.outline_item_bid,
            "title": self.title,
            "type": self.type,
            "hidden": bool(self.hidden),
            "parent_bid": self.parent_bid,
            "position": self.position,
        }


@register_schema_to_swagger
class DashboardSeriesPointDTO(BaseModel):
    """A single chart series point (label + numeric value)."""

    label: str = Field(..., description="Point label", required=False)
    value: int = Field(..., description="Point value", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {"label": self.label, "value": int(self.value)}


@register_schema_to_swagger
class DashboardTopOutlineDTO(BaseModel):
    """Top outline by follow-up questions."""

    outline_item_bid: str = Field(
        ..., description="Outline item business identifier", required=False
    )
    title: str = Field(..., description="Outline title", required=False)
    ask_count: int = Field(..., description="Follow-up ask count", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {
            "outline_item_bid": self.outline_item_bid,
            "title": self.title,
            "ask_count": int(self.ask_count),
        }


@register_schema_to_swagger
class DashboardTopLearnerDTO(BaseModel):
    """Top learner by follow-up questions."""

    user_bid: str = Field(..., description="User business identifier", required=False)
    nickname: str = Field(..., description="User nickname", required=False)
    mobile: str = Field(..., description="User mobile", required=False)
    ask_count: int = Field(..., description="Follow-up ask count", required=False)

    def __json__(self) -> Dict[str, Any]:
        return {
            "user_bid": self.user_bid,
            "nickname": self.nickname,
            "mobile": self.mobile,
            "ask_count": int(self.ask_count),
        }


@register_schema_to_swagger
class DashboardOverviewKpiDTO(BaseModel):
    """Overview KPI payload."""

    learner_count: int = Field(..., description="Learner count", required=False)
    completion_count: int = Field(
        ..., description="Completed learner count", required=False
    )
    completion_rate: float = Field(
        ..., description="Completion rate (0..1)", required=False
    )
    required_outline_total: int = Field(
        ..., description="Required outline items total", required=False
    )
    follow_up_ask_total: int = Field(
        ..., description="Follow-up asks total (within range)", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "learner_count": int(self.learner_count),
            "completion_count": int(self.completion_count),
            "completion_rate": float(self.completion_rate),
            "required_outline_total": int(self.required_outline_total),
            "follow_up_ask_total": int(self.follow_up_ask_total),
        }


@register_schema_to_swagger
class DashboardOverviewDTO(BaseModel):
    """Dashboard overview response payload."""

    kpis: DashboardOverviewKpiDTO = Field(
        ..., description="KPI summary", required=False
    )
    progress_distribution: List[DashboardSeriesPointDTO] = Field(
        default_factory=list,
        description="Progress distribution buckets",
        required=False,
    )
    follow_up_trend: List[DashboardSeriesPointDTO] = Field(
        default_factory=list,
        description="Follow-up asks trend",
        required=False,
    )
    top_outlines_by_follow_ups: List[DashboardTopOutlineDTO] = Field(
        default_factory=list,
        description="Top outlines by follow-up asks",
        required=False,
    )
    top_learners_by_follow_ups: List[DashboardTopLearnerDTO] = Field(
        default_factory=list,
        description="Top learners by follow-up asks",
        required=False,
    )
    start_date: str = Field(
        default="", description="Start date (YYYY-MM-DD)", required=False
    )
    end_date: str = Field(
        default="", description="End date (YYYY-MM-DD)", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "kpis": self.kpis.__json__(),
            "progress_distribution": [
                item.__json__() for item in self.progress_distribution
            ],
            "follow_up_trend": [item.__json__() for item in self.follow_up_trend],
            "top_outlines_by_follow_ups": [
                item.__json__() for item in self.top_outlines_by_follow_ups
            ],
            "top_learners_by_follow_ups": [
                item.__json__() for item in self.top_learners_by_follow_ups
            ],
            "start_date": self.start_date,
            "end_date": self.end_date,
        }


@register_schema_to_swagger
class DashboardLearnerSummaryDTO(BaseModel):
    """Learner summary row for teacher dashboard."""

    user_bid: str = Field(..., description="User business identifier", required=False)
    nickname: str = Field(..., description="User nickname", required=False)
    mobile: str = Field(..., description="User mobile", required=False)
    required_outline_total: int = Field(
        ..., description="Required outline items total", required=False
    )
    completed_outline_count: int = Field(
        ..., description="Completed outline items count", required=False
    )
    progress_percent: float = Field(
        ..., description="Progress percent (0..1)", required=False
    )
    last_active_at: str = Field(
        default="", description="Last active timestamp (ISO)", required=False
    )
    follow_up_ask_count: int = Field(
        default=0, description="Follow-up asks total", required=False
    )

    def __json__(self) -> Dict[str, Any]:
        return {
            "user_bid": self.user_bid,
            "nickname": self.nickname,
            "mobile": self.mobile,
            "required_outline_total": int(self.required_outline_total),
            "completed_outline_count": int(self.completed_outline_count),
            "progress_percent": float(self.progress_percent),
            "last_active_at": self.last_active_at,
            "follow_up_ask_count": int(self.follow_up_ask_count),
        }
