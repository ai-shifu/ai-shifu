"""Expose stable cross-service learning read APIs."""

from flaskr.service.learn.course_visits import count_recent_course_visitors

__all__ = ["count_recent_course_visitors"]
