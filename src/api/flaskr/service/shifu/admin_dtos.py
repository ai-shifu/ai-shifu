"""Compatibility shim for flaskr.service.shifu.admin_dtos.

The DTOs were split into admin_dtos_courses and admin_dtos_users; this module
re-exports every previous symbol so existing imports keep working.
Shim retained for one release cycle per backend-overhaul-master.md B5.
"""

# ruff: noqa: F401

from __future__ import annotations

from datetime import datetime

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.billing.dtos import BillingPlanDTO

from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseChapterDetailDTO,
    AdminOperationCourseCreditUsageDetailItemDTO,
    AdminOperationCourseCreditUsageDetailListDTO,
    AdminOperationCourseCreditUsageItemDTO,
    AdminOperationCourseCreditUsageListDTO,
    AdminOperationCourseDetailBasicInfoDTO,
    AdminOperationCourseDetailChapterDTO,
    AdminOperationCourseDetailDTO,
    AdminOperationCourseDetailMetricsDTO,
    AdminOperationCourseFollowUpCurrentRecordDTO,
    AdminOperationCourseFollowUpDetailBasicInfoDTO,
    AdminOperationCourseFollowUpDetailDTO,
    AdminOperationCourseFollowUpItemDTO,
    AdminOperationCourseFollowUpListDTO,
    AdminOperationCourseFollowUpSummaryDTO,
    AdminOperationCourseFollowUpTimelineItemDTO,
    AdminOperationCourseListDTO,
    AdminOperationCourseOverviewDTO,
    AdminOperationCoursePromptDTO,
    AdminOperationCourseRatingItemDTO,
    AdminOperationCourseRatingListDTO,
    AdminOperationCourseRatingSummaryDTO,
    AdminOperationCourseSummaryDTO,
    AdminOperationCourseUserDTO,
)
from flaskr.service.shifu.admin_dtos_users import (
    AdminOperationUserCourseSummaryDTO,
    AdminOperationUserCreditGrantRequestDTO,
    AdminOperationUserCreditGrantResultDTO,
    AdminOperationUserCreditLedgerItemDTO,
    AdminOperationUserCreditLedgerPageDTO,
    AdminOperationUserCreditSummaryDTO,
    AdminOperationUserCreditUsageDetailDTO,
    AdminOperationUserCreditUsageDetailItemDTO,
    AdminOperationUserGrantBootstrapDTO,
    AdminOperationUserListDTO,
    AdminOperationUserOverviewDTO,
    AdminOperationUserPackageGrantRequestDTO,
    AdminOperationUserPackageGrantResultDTO,
    AdminOperationUserReferralRewardSummaryDTO,
    AdminOperationUserSummaryDTO,
)
