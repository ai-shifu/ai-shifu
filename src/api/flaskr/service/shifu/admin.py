"""Compatibility shim for flaskr.service.shifu.admin.

The implementation was split into the sibling admin_* modules; this module
re-exports every previous public and private symbol so existing imports and
monkeypatch targets keep working.
Shim retained for one release cycle per backend-overhaul-master.md B5.
"""

# ruff: noqa: F401, E402

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from json import JSONDecodeError
from typing import Any, Dict, Iterable, Optional, Sequence, Set
from flask import current_app
from sqlalchemy import and_, case, literal, not_, or_
from sqlalchemy.orm import defer
from flaskr.common.umami_client import get_course_visit_count_30d
from flaskr.i18n import _
from flaskr.dao import db
from flaskr.util.datetime import now_utc
from flaskr.service.billing.bucket_categories import (
    resolve_wallet_bucket_runtime_category,
    wallet_bucket_requires_active_subscription,
)
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_LABELS,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.billing.primitives import (
    credit_decimal_to_number,
    quantize_credit_amount as _quantize_credit_amount,
    safe_int as _safe_int,
)
from flaskr.service.billing.queries import load_primary_active_subscription
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.learn.const import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.common.models import (
    raise_error,
    raise_error_with_args,
    raise_param_error,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin_dtos import (
    AdminOperationCourseCreditUsageDetailItemDTO,
    AdminOperationCourseCreditUsageItemDTO,
    AdminOperationCourseSummaryDTO,
    AdminOperationUserCreditLedgerItemDTO,
    AdminOperationUserCreditSummaryDTO,
    AdminOperationUserCourseSummaryDTO,
    AdminOperationUserSummaryDTO,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    SHIFU_NAME_MAX_LENGTH,
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.course_activity import load_course_activity_map
from flaskr.service.shifu.demo_courses import (
    is_builtin_demo_course,
    load_builtin_demo_titles,
    load_demo_shifu_bids,
)
from flaskr.service.shifu.shifu_draft_funcs import (
    check_text_with_risk_control,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
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
from flaskr.service.user.utils import (
    run_creator_granted_post_auth,
)
from markdown_flow import MarkdownFlow

from flaskr.service.shifu import admin_shared as _split_admin_shared
from flaskr.service.shifu import admin_user_credits as _split_admin_user_credits
from flaskr.service.shifu import admin_user_profiles as _split_admin_user_profiles
from flaskr.service.shifu import admin_course_summaries as _split_admin_course_summaries
from flaskr.service.shifu import admin_user_courses as _split_admin_user_courses

from flaskr.service.shifu.admin_shared import (
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
    _coerce_operator_datetime,
    _format_decimal,
    _normalize_identifier,
    _normalize_metadata_json,
    _resolve_operator_credit_grant_type,
)
from flaskr.service.shifu.admin_user_credits import (
    _allocate_usage_detail_credits,
    _apply_course_credit_usage_filters,
    _build_course_credit_usage_ask_filter,
    _build_course_credit_usage_covered_completed_user_subquery,
    _build_course_credit_usage_generation_name_expr,
    _build_course_credit_usage_group_key,
    _build_course_credit_usage_learn_filter,
    _build_course_credit_usage_model_display,
    _build_course_credit_usage_scene_filter,
    _build_operator_course_credit_metrics,
    _build_operator_course_credit_usage_base_query,
    _build_operator_course_credit_usage_detail_item,
    _build_operator_course_credit_usage_item,
    _build_operator_course_credit_usage_ledger_totals_subquery,
    _build_operator_user_credit_ledger_item,
    _build_operator_user_credit_merged_metadata,
    _build_operator_user_credit_summary,
    _collect_operator_user_credit_order_source_bids,
    _is_operator_user_credit_consume_row,
    _is_operator_user_credit_grant_row,
    _is_operator_user_credit_other_row,
    _load_active_subscription_end_map,
    _load_active_subscription_product_display_name_i18n_key,
    _load_billing_order_map,
    _load_course_credit_usage_output_summary_map,
    _load_generated_block_content_map,
    _load_listen_segment_content_map,
    _load_operator_user_credit_summary_map,
    _load_operator_user_credit_usage_context_map,
    _load_operator_user_credit_usage_main_row,
    _load_operator_user_credit_usage_owner_ledger_rows,
    _load_operator_user_credit_usage_segment_rows,
    _operator_credit_int,
    _resolve_course_credit_usage_mode,
    _resolve_course_credit_usage_mode_filter,
    _resolve_course_credit_usage_output_summary,
    _resolve_course_credit_usage_scene,
    _resolve_course_credit_usage_scene_filter,
    _resolve_course_credit_usage_view,
    _resolve_operator_credit_display_entry_type,
    _resolve_operator_credit_display_source_type,
    _resolve_operator_credit_note_code,
    _resolve_operator_credit_usage_scene,
    _resolve_operator_user_credit_grant_filter_key,
    _resolve_operator_user_credit_grant_source_filter,
    _resolve_operator_user_credit_type_filter,
    _resolve_operator_user_credit_usage_context,
    _resolve_operator_user_credit_usage_scene,
    _resolve_usage_detail_item_content,
)
from flaskr.service.shifu.admin_user_profiles import (
    _assert_operator_user_grant_target_supported,
    _build_course_order_amount_expr,
    _build_learner_user_bid_subquery,
    _build_operator_user_roles,
    _build_operator_user_summary,
    _build_recent_learning_active_user_bid_subquery,
    _build_recent_paid_user_bid_subquery,
    _build_registered_user_timestamp_subquery,
    _find_matching_creator_bids,
    _find_matching_user_bids_by_identifier,
    _load_course_user_contact_map,
    _load_learner_user_bids,
    _load_operator_user_auth_credentials,
    _load_operator_user_contact_map,
    _load_operator_user_last_learning_map,
    _load_operator_user_last_login_map,
    _load_operator_user_or_raise,
    _load_operator_user_registration_source_map,
    _load_operator_user_total_paid_amount_map,
    _load_user_map,
    _normalize_login_method,
    _normalize_registration_source,
    _resolve_course_user_learning_status,
    _resolve_course_user_role,
    _resolve_operator_user_quick_filter,
    _resolve_operator_user_role,
    _resolve_operator_user_status,
    _resolve_recent_days_window,
)
from flaskr.service.shifu.admin_course_summaries import (
    OperatorCourseListCandidate,
    OperatorCourseListSeed,
    _attach_course_prompt_flags,
    _build_course_copy_title,
    _build_course_summary,
    _build_latest_operator_course_rows_query,
    _build_latest_operator_course_rows_subquery,
    _build_latest_outline_activity_subquery,
    _build_latest_shifus_query,
    _build_operator_course_candidate_query,
    _build_operator_course_latest_activity_subquery,
    _build_operator_course_list_candidate,
    _build_operator_course_list_seed,
    _build_operator_visible_course_filter,
    _build_outline_history_tree,
    _format_average_score,
    _is_operator_visible_course,
    _load_course_activity_map,
    _load_latest_active_draft_outlines,
    _load_latest_course_for_transfer,
    _load_latest_course_versions,
    _load_latest_courses_by_shifu_bids,
    _load_latest_shifu_seeds,
    _load_latest_shifus,
    _merge_courses,
    _resolve_course_copy_title,
    _resolve_course_quick_filter,
    _resolve_course_rating_mode,
    _resolve_course_rating_sort_by,
    _resolve_course_status,
    _resolve_created_last_7d_window,
)
from flaskr.service.shifu.admin_user_courses import (
    _build_operator_user_course_summary,
    _is_completed_leaf_progress_statuses,
    _load_learning_progress_counts_by_user_and_course,
    _load_operator_user_course_count_maps,
    _load_operator_user_course_maps,
    _load_visible_published_leaf_outline_bids_by_shifu,
)

# Public compatibility exports for split admin operation modules. Keep these
# aliases until the remaining legacy helpers are moved out of this module.
build_learner_user_bid_subquery = _build_learner_user_bid_subquery
build_operator_user_summary = _build_operator_user_summary
build_recent_learning_active_user_bid_subquery = (
    _build_recent_learning_active_user_bid_subquery
)
build_recent_paid_user_bid_subquery = _build_recent_paid_user_bid_subquery
build_registered_user_timestamp_subquery = _build_registered_user_timestamp_subquery
find_matching_user_bids_by_identifier = _find_matching_user_bids_by_identifier
load_learner_user_bids = _load_learner_user_bids
load_operator_user_auth_credentials = _load_operator_user_auth_credentials
load_operator_user_contact_map = _load_operator_user_contact_map
load_operator_user_course_count_maps = _load_operator_user_course_count_maps
load_operator_user_course_maps = _load_operator_user_course_maps
load_operator_user_credit_summary_map = _load_operator_user_credit_summary_map
load_operator_user_last_learning_map = _load_operator_user_last_learning_map
load_operator_user_last_login_map = _load_operator_user_last_login_map
load_operator_user_or_raise = _load_operator_user_or_raise
load_operator_user_registration_source_map = _load_operator_user_registration_source_map
load_operator_user_total_paid_amount_map = _load_operator_user_total_paid_amount_map
resolve_operator_user_quick_filter = _resolve_operator_user_quick_filter
resolve_recent_days_window = _resolve_recent_days_window


from flaskr.service.shifu.admin_operations import courses as _operator_courses  # noqa: E402

# Backward-compatible exports for existing imports from shifu.admin.
_OPERATOR_COURSE_COMPAT_EXPORTS = (
    "_resolve_operator_credit_grant_type",
    "_format_decimal",
    "_coerce_operator_datetime",
    "_format_average_score",
    "_resolve_course_rating_mode",
    "_resolve_course_rating_sort_by",
    "_resolve_course_credit_usage_mode",
    "_resolve_course_credit_usage_mode_filter",
    "_resolve_course_credit_usage_scene",
    "_resolve_course_credit_usage_scene_filter",
    "_build_course_credit_usage_scene_filter",
    "_resolve_course_credit_usage_view",
    "_build_course_credit_usage_model_display",
    "_build_course_credit_usage_group_key",
    "_build_operator_course_credit_usage_item",
    "_build_course_credit_usage_generation_name_expr",
    "_build_course_credit_usage_ask_filter",
    "_build_course_credit_usage_learn_filter",
    "_build_operator_course_credit_usage_ledger_totals_subquery",
    "_build_operator_course_credit_usage_base_query",
    "_resolve_course_credit_usage_output_summary",
    "_load_course_credit_usage_output_summary_map",
    "_build_operator_course_credit_usage_detail_item",
    "_apply_course_credit_usage_filters",
    "_build_course_credit_usage_covered_completed_user_subquery",
    "_build_operator_course_credit_metrics",
    "_normalize_metadata_json",
    "_normalize_identifier",
    "_load_course_user_contact_map",
    "_load_user_map",
    "_resolve_course_user_role",
    "_resolve_course_user_learning_status",
    "_build_course_order_amount_expr",
    "_find_matching_creator_bids",
    "_load_operator_user_last_login_map",
    "_build_operator_course_list_seed",
    "_build_operator_course_list_candidate",
    "_build_operator_visible_course_filter",
    "_build_latest_operator_course_rows_query",
    "_build_latest_operator_course_rows_subquery",
    "_build_operator_course_candidate_query",
    "_build_latest_outline_activity_subquery",
    "_build_operator_course_latest_activity_subquery",
    "_build_latest_shifus_query",
    "_load_latest_shifus",
    "_load_latest_shifu_seeds",
    "_attach_course_prompt_flags",
    "_build_course_summary",
    "_is_operator_visible_course",
    "_resolve_course_status",
    "_resolve_course_quick_filter",
    "_resolve_created_last_7d_window",
    "_load_course_activity_map",
    "_load_latest_course_for_transfer",
    "_load_latest_active_draft_outlines",
    "_build_course_copy_title",
    "_resolve_course_copy_title",
    "_build_outline_history_tree",
    "_copy_course_variable_definitions",
    "_run_course_copy_draft_risk_check",
    "_run_course_copy_outline_risk_check",
    "_validate_operator_target_contact",
    "_prepare_operator_target_creator",
    "_load_recent_learning_active_course_bids",
    "_load_recent_paid_order_course_bids",
    "_clear_shifu_permission_cache",
    "_clear_shifu_creator_cache",
    "_update_course_creator_bid",
    "transfer_operator_course_creator",
    "copy_operator_course",
    "_merge_courses",
    "_load_latest_course_versions",
    "_load_operator_course_detail_source",
    "_load_latest_outline_items",
    "_resolve_learning_permission",
    "_resolve_content_status",
    "_resolve_outline_prompt_source",
    "_resolve_prompt_with_fallback",
    "_build_chapter_tree",
    "_load_outline_learning_stats",
    "_load_operator_course_outline_items",
    "_resolve_visible_leaf_outline_bids",
    "_build_course_outline_context_map",
    "_build_course_follow_up_base_subquery",
    "_build_follow_up_user_keyword_filter",
    "_build_credit_usage_user_keyword_filter",
    "_resolve_follow_up_matching_outline_bids",
    "_resolve_follow_up_answer_block",
    "_resolve_follow_up_answer_content",
    "_load_follow_up_groups_for_progress_record",
    "_resolve_follow_up_source_from_element",
    "_resolve_follow_up_source_from_blocks",
    "_resolve_follow_up_source",
    "_load_course_related_user_bids",
    "_load_course_user_paid_amount_map",
    "_load_course_user_last_learning_map",
    "_load_course_user_joined_at_map",
    "_load_course_user_learned_lesson_count_map",
    "get_operator_course_detail",
    "get_operator_course_prompt",
    "get_operator_course_users",
    "get_operator_course_credit_usages",
    "get_operator_course_credit_usage_details",
    "get_operator_course_follow_ups",
    "get_operator_course_ratings",
    "get_operator_course_follow_up_detail",
    "get_operator_course_chapter_detail",
    "_load_bill_usage_record_map",
    "_build_latest_bill_usage_record_subquery",
    "_build_latest_billing_order_subquery",
    "_find_operator_course_bids_by_name",
    "_build_operator_course_query_filter",
    "_build_operator_course_overview",
    "get_operator_course_overview",
    "_can_use_operator_course_sql_optimization",
    "_build_operator_course_overview_legacy",
    "_list_operator_courses_legacy",
    "list_operator_courses",
    "load_existing_demo_shifu_ids",
)

_copy_course_variable_definitions = _operator_courses._copy_course_variable_definitions
_run_course_copy_draft_risk_check = _operator_courses._run_course_copy_draft_risk_check
_run_course_copy_outline_risk_check = (
    _operator_courses._run_course_copy_outline_risk_check
)
_validate_operator_target_contact = _operator_courses._validate_operator_target_contact
_prepare_operator_target_creator = _operator_courses._prepare_operator_target_creator
_load_recent_learning_active_course_bids = (
    _operator_courses._load_recent_learning_active_course_bids
)
_load_recent_paid_order_course_bids = (
    _operator_courses._load_recent_paid_order_course_bids
)
_clear_shifu_permission_cache = _operator_courses._clear_shifu_permission_cache
_clear_shifu_creator_cache = _operator_courses._clear_shifu_creator_cache
_update_course_creator_bid = _operator_courses._update_course_creator_bid
transfer_operator_course_creator = _operator_courses.transfer_operator_course_creator
copy_operator_course = _operator_courses.copy_operator_course
_load_operator_course_detail_source = (
    _operator_courses._load_operator_course_detail_source
)
_load_latest_outline_items = _operator_courses._load_latest_outline_items
_resolve_learning_permission = _operator_courses._resolve_learning_permission
_resolve_content_status = _operator_courses._resolve_content_status
_resolve_outline_prompt_source = _operator_courses._resolve_outline_prompt_source
_resolve_prompt_with_fallback = _operator_courses._resolve_prompt_with_fallback
_build_chapter_tree = _operator_courses._build_chapter_tree
_load_outline_learning_stats = _operator_courses._load_outline_learning_stats
_load_operator_course_outline_items = (
    _operator_courses._load_operator_course_outline_items
)
_resolve_visible_leaf_outline_bids = (
    _operator_courses._resolve_visible_leaf_outline_bids
)
_build_course_outline_context_map = _operator_courses._build_course_outline_context_map
_build_course_follow_up_base_subquery = (
    _operator_courses._build_course_follow_up_base_subquery
)
_build_follow_up_user_keyword_filter = (
    _operator_courses._build_follow_up_user_keyword_filter
)
_build_credit_usage_user_keyword_filter = (
    _operator_courses._build_credit_usage_user_keyword_filter
)
_resolve_follow_up_matching_outline_bids = (
    _operator_courses._resolve_follow_up_matching_outline_bids
)
_resolve_follow_up_answer_block = _operator_courses._resolve_follow_up_answer_block
_resolve_follow_up_answer_content = _operator_courses._resolve_follow_up_answer_content
_load_follow_up_groups_for_progress_record = (
    _operator_courses._load_follow_up_groups_for_progress_record
)
_resolve_follow_up_source_from_element = (
    _operator_courses._resolve_follow_up_source_from_element
)
_resolve_follow_up_source_from_blocks = (
    _operator_courses._resolve_follow_up_source_from_blocks
)
_resolve_follow_up_source = _operator_courses._resolve_follow_up_source
_load_course_related_user_bids = _operator_courses._load_course_related_user_bids
_load_course_user_paid_amount_map = _operator_courses._load_course_user_paid_amount_map
_load_course_user_last_learning_map = (
    _operator_courses._load_course_user_last_learning_map
)
_load_course_user_joined_at_map = _operator_courses._load_course_user_joined_at_map
_load_course_user_learned_lesson_count_map = (
    _operator_courses._load_course_user_learned_lesson_count_map
)
get_operator_course_detail = _operator_courses.get_operator_course_detail
get_operator_course_prompt = _operator_courses.get_operator_course_prompt
get_operator_course_users = _operator_courses.get_operator_course_users
get_operator_course_credit_usages = _operator_courses.get_operator_course_credit_usages
get_operator_course_credit_usage_details = (
    _operator_courses.get_operator_course_credit_usage_details
)
get_operator_course_follow_ups = _operator_courses.get_operator_course_follow_ups
get_operator_course_ratings = _operator_courses.get_operator_course_ratings
get_operator_course_follow_up_detail = (
    _operator_courses.get_operator_course_follow_up_detail
)
get_operator_course_chapter_detail = (
    _operator_courses.get_operator_course_chapter_detail
)
_load_bill_usage_record_map = _operator_courses._load_bill_usage_record_map
_build_latest_bill_usage_record_subquery = (
    _operator_courses._build_latest_bill_usage_record_subquery
)
_build_latest_billing_order_subquery = (
    _operator_courses._build_latest_billing_order_subquery
)
_find_operator_course_bids_by_name = (
    _operator_courses._find_operator_course_bids_by_name
)
_build_operator_course_query_filter = (
    _operator_courses._build_operator_course_query_filter
)
_build_operator_course_overview = _operator_courses._build_operator_course_overview
get_operator_course_overview = _operator_courses.get_operator_course_overview
_can_use_operator_course_sql_optimization = (
    _operator_courses._can_use_operator_course_sql_optimization
)
_build_operator_course_overview_legacy = (
    _operator_courses._build_operator_course_overview_legacy
)
_list_operator_courses_legacy = _operator_courses._list_operator_courses_legacy
list_operator_courses = _operator_courses.list_operator_courses
load_existing_demo_shifu_ids = _operator_courses.load_existing_demo_shifu_ids

_OPERATOR_COURSE_FORWARDABLE_NAMES = _OPERATOR_COURSE_COMPAT_EXPORTS + (
    "check_text_with_risk_control",
    "datetime",
    "get_course_visit_count_30d",
    "run_creator_granted_post_auth",
)

_ADMIN_SPLIT_SUBMODULES = (
    _split_admin_shared,
    _split_admin_user_credits,
    _split_admin_user_profiles,
    _split_admin_course_summaries,
    _split_admin_user_courses,
)


class _AdminCompatibilityModule(type(sys)):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for submodule in _ADMIN_SPLIT_SUBMODULES:
            if hasattr(submodule, name):
                setattr(submodule, name, value)
        if name in _OPERATOR_COURSE_FORWARDABLE_NAMES and hasattr(
            _operator_courses, name
        ):
            setattr(_operator_courses, name, value)


sys.modules[__name__].__class__ = _AdminCompatibilityModule


__all__ = (
    "get_course_visit_count_30d",
    "UNIT_TYPE_VALUE_GUEST",
    "UNIT_TYPE_VALUE_NORMAL",
    "UNIT_TYPE_VALUE_TRIAL",
    "check_text_with_risk_control",
    "load_existing_demo_shifu_ids",
    "run_creator_granted_post_auth",
    "_resolve_operator_credit_grant_type",
    "_format_average_score",
    "_resolve_course_rating_mode",
    "_resolve_course_rating_sort_by",
    "_resolve_course_credit_usage_view",
    "_build_course_credit_usage_model_display",
    "_build_course_credit_usage_group_key",
    "_build_operator_course_credit_usage_item",
    "_load_course_credit_usage_output_summary_map",
    "_build_operator_course_credit_usage_detail_item",
    "_apply_course_credit_usage_filters",
    "_build_operator_course_credit_metrics",
    "_load_course_user_contact_map",
    "_load_user_map",
    "_resolve_course_user_role",
    "_resolve_course_user_learning_status",
    "_find_matching_creator_bids",
    "_build_operator_course_list_candidate",
    "_build_operator_course_candidate_query",
    "_load_latest_shifu_seeds",
    "_build_course_summary",
    "_resolve_course_quick_filter",
    "_resolve_created_last_7d_window",
    "_load_course_activity_map",
    "_load_latest_course_for_transfer",
    "_load_latest_active_draft_outlines",
    "_resolve_course_copy_title",
    "_build_outline_history_tree",
    "_copy_course_variable_definitions",
    "_run_course_copy_draft_risk_check",
    "_run_course_copy_outline_risk_check",
    "_validate_operator_target_contact",
    "_prepare_operator_target_creator",
    "_load_recent_learning_active_course_bids",
    "_load_recent_paid_order_course_bids",
    "_clear_shifu_permission_cache",
    "_clear_shifu_creator_cache",
    "_update_course_creator_bid",
    "transfer_operator_course_creator",
    "copy_operator_course",
    "_load_latest_course_versions",
    "_load_operator_course_detail_source",
    "_resolve_learning_permission",
    "_resolve_content_status",
    "_resolve_outline_prompt_source",
    "_resolve_prompt_with_fallback",
    "_build_chapter_tree",
    "_load_outline_learning_stats",
    "_load_operator_course_outline_items",
    "_resolve_visible_leaf_outline_bids",
    "_build_course_follow_up_base_subquery",
    "_build_follow_up_user_keyword_filter",
    "_resolve_follow_up_matching_outline_bids",
    "_resolve_follow_up_answer_block",
    "_resolve_follow_up_answer_content",
    "_load_follow_up_groups_for_progress_record",
    "_resolve_follow_up_source_from_element",
    "_resolve_follow_up_source_from_blocks",
    "_resolve_follow_up_source",
    "_load_course_related_user_bids",
    "_load_course_user_paid_amount_map",
    "_load_course_user_last_learning_map",
    "_load_course_user_joined_at_map",
    "_load_course_user_learned_lesson_count_map",
    "get_operator_course_detail",
    "get_operator_course_prompt",
    "get_operator_course_users",
    "get_operator_course_credit_usages",
    "get_operator_course_credit_usage_details",
    "get_operator_course_follow_ups",
    "get_operator_course_ratings",
    "get_operator_course_follow_up_detail",
    "get_operator_course_chapter_detail",
    "_load_bill_usage_record_map",
    "_build_latest_billing_order_subquery",
    "_find_operator_course_bids_by_name",
    "_build_operator_course_query_filter",
    "_build_operator_course_overview",
    "get_operator_course_overview",
    "_can_use_operator_course_sql_optimization",
    "_build_operator_course_overview_legacy",
    "_list_operator_courses_legacy",
    "list_operator_courses",
)
