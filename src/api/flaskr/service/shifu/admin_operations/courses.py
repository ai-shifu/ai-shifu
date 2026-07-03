"""Compatibility shim for flaskr.service.shifu.admin_operations.courses.

The implementation was split into the sibling courses_* modules; this module
re-exports every previous public and private symbol so existing imports and
monkeypatch targets keep working.
Shim retained for one release cycle per backend-overhaul-master.md B5.
"""

# ruff: noqa: F401, E402

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Sequence, Set
from flask import Flask, current_app
from sqlalchemy import and_, case, false, literal, not_, or_
from sqlalchemy.orm import defer
from flaskr.common.cache_provider import cache as redis
from flaskr.common.config import get_redis_key_prefix
from flaskr.common.umami_client import get_course_visit_count_30d
from flaskr.i18n import _
from flaskr.dao import db
from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
)
from flaskr.service.billing.primitives import credit_decimal_to_number
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.learn.learn_dtos import ElementType
from flaskr.service.learn.listen_element_payloads import _deserialize_payload
from flaskr.service.learn.const import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.common.models import (
    raise_error,
    raise_error_with_args,
    raise_param_error,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.profile.models import Variable
from flaskr.util import generate_id
from flaskr.service.shifu.admin_dtos import (
    AdminOperationCourseListDTO,
    AdminOperationCourseChapterDetailDTO,
    AdminOperationCourseDetailBasicInfoDTO,
    AdminOperationCourseDetailChapterDTO,
    AdminOperationCourseDetailDTO,
    AdminOperationCourseCreditUsageDetailItemDTO,
    AdminOperationCourseCreditUsageDetailListDTO,
    AdminOperationCourseCreditUsageItemDTO,
    AdminOperationCourseCreditUsageListDTO,
    AdminOperationCourseFollowUpCurrentRecordDTO,
    AdminOperationCourseFollowUpDetailBasicInfoDTO,
    AdminOperationCourseFollowUpDetailDTO,
    AdminOperationCourseFollowUpItemDTO,
    AdminOperationCourseFollowUpListDTO,
    AdminOperationCourseFollowUpSummaryDTO,
    AdminOperationCourseFollowUpTimelineItemDTO,
    AdminOperationCourseDetailMetricsDTO,
    AdminOperationCoursePromptDTO,
    AdminOperationCourseRatingItemDTO,
    AdminOperationCourseRatingListDTO,
    AdminOperationCourseRatingSummaryDTO,
    AdminOperationCourseOverviewDTO,
    AdminOperationCourseUserDTO,
    AdminOperationCourseSummaryDTO,
)
from flaskr.service.shifu.course_activity import load_course_activity_map
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    SHIFU_NAME_MAX_LENGTH,
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.demo_courses import (
    is_builtin_demo_course,
    load_builtin_demo_titles,
    load_demo_shifu_bids,
)
from flaskr.service.shifu.shifu_draft_funcs import (
    check_text_with_risk_control,
    get_latest_shifu_draft,
)
from flaskr.service.shifu.shifu_history_manager import (
    HistoryItem,
    save_outline_tree_history,
    save_shifu_history,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
    UserToken,
)
from flaskr.service.user.repository import (
    ensure_user_for_identifier,
    load_user_aggregate_by_identifier,
    set_user_state,
    upsert_credential,
)
from flaskr.service.user.utils import (
    ensure_demo_course_permissions,
    load_existing_demo_shifu_ids,
    mark_creator_role_if_needed,
    run_creator_granted_post_auth,
)
from markdown_flow import MarkdownFlow

from flaskr.service.shifu.admin_operations import (
    courses_shared as _split_courses_shared,
)
from flaskr.service.shifu.admin_operations import (
    courses_credit_usage as _split_courses_credit_usage,
)
from flaskr.service.shifu.admin_operations import (
    courses_listing as _split_courses_listing,
)
from flaskr.service.shifu.admin_operations import (
    courses_transfer_copy as _split_courses_transfer_copy,
)
from flaskr.service.shifu.admin_operations import (
    courses_detail as _split_courses_detail,
)
from flaskr.service.shifu.admin_operations import (
    courses_follow_ups as _split_courses_follow_ups,
)
from flaskr.service.shifu.admin_operations import courses_users as _split_courses_users
from flaskr.service.shifu.admin_operations import (
    courses_ratings as _split_courses_ratings,
)

from flaskr.service.shifu.admin_operations.courses_shared import (
    COURSE_CREDIT_USAGE_LIST_MAX_PAGE_SIZE,
    COURSE_CREDIT_USAGE_MODE_ASK,
    COURSE_CREDIT_USAGE_MODE_LEARN,
    COURSE_CREDIT_USAGE_MODE_LISTEN,
    COURSE_CREDIT_USAGE_MODE_MIXED,
    COURSE_CREDIT_USAGE_SCENE_DEBUG,
    COURSE_CREDIT_USAGE_SCENE_LEARNING,
    COURSE_CREDIT_USAGE_SCENE_PREVIEW,
    COURSE_CREDIT_USAGE_VIEW_GROUPED,
    COURSE_CREDIT_USAGE_VIEW_RAW,
    COURSE_FOLLOW_UP_LIST_MAX_PAGE_SIZE,
    COURSE_QUICK_FILTER_CREATED_LAST_7D,
    COURSE_QUICK_FILTER_DRAFT,
    COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D,
    COURSE_QUICK_FILTER_PAID_ORDER_30D,
    COURSE_QUICK_FILTER_PUBLISHED,
    COURSE_QUICK_FILTER_VALUES,
    COURSE_RATING_LIST_MAX_PAGE_SIZE,
    COURSE_STATUS_PUBLISHED,
    COURSE_STATUS_UNPUBLISHED,
    COURSE_USER_LEARNING_STATUS_COMPLETED,
    COURSE_USER_LEARNING_STATUS_LEARNING,
    COURSE_USER_LEARNING_STATUS_NOT_STARTED,
    COURSE_USER_LIST_MAX_PAGE_SIZE,
    COURSE_USER_ROLE_CREATOR,
    COURSE_USER_ROLE_NORMAL,
    COURSE_USER_ROLE_OPERATOR,
    COURSE_USER_ROLE_STUDENT,
    OPERATOR_ORDER_LIST_MAX_PAGE_SIZE,
    OPERATOR_TARGET_CONTACT_MAX_LENGTH,
    OPERATOR_TARGET_EMAIL_PATTERN,
    OPERATOR_TARGET_PHONE_PATTERN,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCES,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_ALL,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_MANUAL,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TOPUP,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TRIAL_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_FILTER_TYPES,
    OPERATOR_USER_CREDIT_GRANT_SOURCES,
    OPERATOR_USER_CREDIT_GRANT_SOURCE_COMPENSATION,
    OPERATOR_USER_CREDIT_GRANT_SOURCE_REWARD,
    OPERATOR_USER_CREDIT_GRANT_TYPES,
    OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL,
    OPERATOR_USER_CREDIT_GRANT_TYPE_REFERRAL_REWARD,
    OPERATOR_USER_CREDIT_TYPE_ALL,
    OPERATOR_USER_CREDIT_TYPE_CONSUME,
    OPERATOR_USER_CREDIT_TYPE_GRANT,
    OPERATOR_USER_CREDIT_TYPE_OTHER,
    OPERATOR_USER_CREDIT_VALIDITY_1D,
    OPERATOR_USER_CREDIT_VALIDITY_1M,
    OPERATOR_USER_CREDIT_VALIDITY_1Y,
    OPERATOR_USER_CREDIT_VALIDITY_3M,
    OPERATOR_USER_CREDIT_VALIDITY_7D,
    OPERATOR_USER_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_VALIDITY_PRESETS,
    OPERATOR_USER_LIST_MAX_PAGE_SIZE,
    OPERATOR_USER_PRELOADED_AUTH_CREDENTIAL_PROVIDERS,
    OPERATOR_USER_QUICK_FILTER_CREATED_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_CREATOR,
    OPERATOR_USER_QUICK_FILTER_GUEST,
    OPERATOR_USER_QUICK_FILTER_LEARNER,
    OPERATOR_USER_QUICK_FILTER_LEARNING_ACTIVE_30D,
    OPERATOR_USER_QUICK_FILTER_PAID,
    OPERATOR_USER_QUICK_FILTER_PAID_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_REGISTERED,
    OPERATOR_USER_QUICK_FILTER_REGISTERED_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_VALUES,
    OPERATOR_USER_REGISTRATION_CREDENTIAL_PROVIDERS,
    OPERATOR_USER_REGISTRATION_SOURCE_EMAIL,
    OPERATOR_USER_REGISTRATION_SOURCE_GOOGLE,
    OPERATOR_USER_REGISTRATION_SOURCE_IMPORTED,
    OPERATOR_USER_REGISTRATION_SOURCE_PHONE,
    OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN,
    OPERATOR_USER_REGISTRATION_SOURCE_WECHAT,
    OPERATOR_USER_ROLE_CREATOR,
    OPERATOR_USER_ROLE_LEARNER,
    OPERATOR_USER_ROLE_OPERATOR,
    OPERATOR_USER_ROLE_REGULAR,
    OPERATOR_USER_STATUS_PAID,
    OPERATOR_USER_STATUS_REGISTERED,
    OPERATOR_USER_STATUS_TRIAL,
    OPERATOR_USER_STATUS_UNKNOWN,
    OPERATOR_USER_STATUS_UNREGISTERED,
    OPERATOR_USER_SUPPORTED_LOGIN_METHOD_PROVIDERS,
    OPERATOR_USER_SUPPORTED_REGISTRATION_SOURCE_PROVIDERS,
    PROMPT_SOURCE_CHAPTER,
    PROMPT_SOURCE_COURSE,
    PROMPT_SOURCE_LESSON,
    USER_STATE_TO_OPERATOR_STATUS,
    _build_course_order_amount_expr,
    _build_course_outline_context_map,
    _coerce_operator_datetime,
    _find_matching_creator_bids,
    _format_average_score,
    _format_decimal,
    _get_legacy_admin_symbol,
    _is_operator_visible_course,
    _load_course_user_contact_map,
    _load_latest_course_versions,
    _load_latest_outline_items,
    _load_operator_course_detail_source,
    _load_operator_course_outline_items,
    _load_operator_user_last_login_map,
    _load_user_map,
    _merge_courses,
    _normalize_identifier,
    _normalize_metadata_json,
    _resolve_course_user_learning_status,
    _resolve_course_user_role,
    _resolve_operator_credit_grant_type,
    _resolve_visible_leaf_outline_bids,
)
from flaskr.service.shifu.admin_operations.courses_credit_usage import (
    _apply_course_credit_usage_filters,
    _build_course_credit_usage_ask_filter,
    _build_course_credit_usage_covered_completed_user_subquery,
    _build_course_credit_usage_generation_name_expr,
    _build_course_credit_usage_group_key,
    _build_course_credit_usage_learn_filter,
    _build_course_credit_usage_model_display,
    _build_course_credit_usage_scene_filter,
    _build_credit_usage_user_keyword_filter,
    _build_latest_bill_usage_record_subquery,
    _build_operator_course_credit_metrics,
    _build_operator_course_credit_usage_base_query,
    _build_operator_course_credit_usage_detail_item,
    _build_operator_course_credit_usage_item,
    _build_operator_course_credit_usage_ledger_totals_subquery,
    _load_bill_usage_record_map,
    _load_course_credit_usage_output_summary_map,
    _resolve_course_credit_usage_mode,
    _resolve_course_credit_usage_mode_filter,
    _resolve_course_credit_usage_output_summary,
    _resolve_course_credit_usage_scene,
    _resolve_course_credit_usage_scene_filter,
    _resolve_course_credit_usage_view,
    get_operator_course_credit_usage_details,
    get_operator_course_credit_usages,
)
from flaskr.service.shifu.admin_operations.courses_listing import (
    OperatorCourseListCandidate,
    OperatorCourseListSeed,
    _attach_course_prompt_flags,
    _build_course_summary,
    _build_latest_billing_order_subquery,
    _build_latest_operator_course_rows_query,
    _build_latest_operator_course_rows_subquery,
    _build_latest_outline_activity_subquery,
    _build_latest_shifus_query,
    _build_operator_course_candidate_query,
    _build_operator_course_latest_activity_subquery,
    _build_operator_course_list_candidate,
    _build_operator_course_list_seed,
    _build_operator_course_overview,
    _build_operator_course_overview_legacy,
    _build_operator_course_query_filter,
    _build_operator_visible_course_filter,
    _can_use_operator_course_sql_optimization,
    _find_operator_course_bids_by_name,
    _list_operator_courses_legacy,
    _load_course_activity_map,
    _load_latest_shifu_seeds,
    _load_latest_shifus,
    _load_recent_learning_active_course_bids,
    _load_recent_paid_order_course_bids,
    _resolve_course_quick_filter,
    _resolve_course_status,
    _resolve_created_last_7d_window,
    get_operator_course_overview,
    list_operator_courses,
)
from flaskr.service.shifu.admin_operations.courses_transfer_copy import (
    _build_course_copy_title,
    _build_outline_history_tree,
    _clear_shifu_creator_cache,
    _clear_shifu_permission_cache,
    _copy_course_variable_definitions,
    _load_latest_active_draft_outlines,
    _load_latest_course_for_transfer,
    _prepare_operator_target_creator,
    _resolve_course_copy_title,
    _run_course_copy_draft_risk_check,
    _run_course_copy_outline_risk_check,
    _update_course_creator_bid,
    _validate_operator_target_contact,
    copy_operator_course,
    transfer_operator_course_creator,
)
from flaskr.service.shifu.admin_operations.courses_detail import (
    _build_chapter_tree,
    _load_outline_learning_stats,
    _resolve_content_status,
    _resolve_learning_permission,
    _resolve_outline_prompt_source,
    _resolve_prompt_with_fallback,
    get_operator_course_chapter_detail,
    get_operator_course_detail,
    get_operator_course_prompt,
)
from flaskr.service.shifu.admin_operations.courses_follow_ups import (
    _build_course_follow_up_base_subquery,
    _build_follow_up_source_status_map,
    _build_follow_up_user_keyword_filter,
    _load_follow_up_groups_for_progress_record,
    _load_follow_up_groups_for_progress_records,
    _resolve_follow_up_answer_block,
    _resolve_follow_up_answer_content,
    _resolve_follow_up_matching_outline_bids,
    _resolve_follow_up_source,
    _resolve_follow_up_source_from_blocks,
    _resolve_follow_up_source_from_element,
    get_operator_course_follow_up_detail,
    get_operator_course_follow_ups,
)
from flaskr.service.shifu.admin_operations.courses_users import (
    _load_course_related_user_bids,
    _load_course_user_joined_at_map,
    _load_course_user_last_learning_map,
    _load_course_user_learned_lesson_count_map,
    _load_course_user_paid_amount_map,
    get_operator_course_users,
)
from flaskr.service.shifu.admin_operations.courses_ratings import (
    _resolve_course_rating_mode,
    _resolve_course_rating_sort_by,
    get_operator_course_ratings,
)

_COURSES_SPLIT_SUBMODULES = (
    _split_courses_shared,
    _split_courses_credit_usage,
    _split_courses_listing,
    _split_courses_transfer_copy,
    _split_courses_detail,
    _split_courses_follow_ups,
    _split_courses_users,
    _split_courses_ratings,
)


class _CoursesCompatibilityModule(type(sys)):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for submodule in _COURSES_SPLIT_SUBMODULES:
            if hasattr(submodule, name):
                setattr(submodule, name, value)


sys.modules[__name__].__class__ = _CoursesCompatibilityModule
