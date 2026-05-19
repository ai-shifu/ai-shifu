'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { CircleHelp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { formatAdminCredits } from '@/app/admin/lib/numberFormat';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import { formatOperatorNaiveDateTime } from '../dateTime';
import type {
  AdminOperationUserCourseItem,
  AdminOperationUserCreditFilters,
  AdminOperationUserCreditSummary,
  AdminOperationUserCreditsResponse,
  AdminOperationUserDetailResponse,
} from '../../operation-user-types';
import useOperatorGuard from '../../useOperatorGuard';
import UserDetailSummarySection from './UserDetailSummarySection';
import UserDetailTabsSection from './UserDetailTabsSection';
import {
  createUserCreditFilters,
  FILTER_ALL_OPTION,
  sanitizeCreditFiltersByType,
} from './creditFilterUtils';

type ErrorState = { message: string; code?: number };
type DetailTab = 'credits' | 'learning' | 'created';

const CREDITS_PAGE_SIZE = 10;
const EMPTY_VALUE = '--';
const DETAIL_TAB_HASHES: Record<DetailTab, string> = {
  credits: '#credits',
  learning: '#learning-courses',
  created: '#created-courses',
};
const resolveDetailTabFromHash = (hash: string): DetailTab | null => {
  const hashEntry = Object.entries(DETAIL_TAB_HASHES).find(
    ([, targetHash]) => targetHash === hash,
  ) as [DetailTab, string] | undefined;

  return hashEntry?.[0] ?? null;
};
const resolveCourseCount = (
  count: number,
  courses?: AdminOperationUserCourseItem[],
) => (count > 0 ? count : (courses || []).length);
const DEFAULT_CREDIT_SUMMARY: AdminOperationUserCreditSummary = {
  available_credits: '',
  subscription_credits: '',
  topup_credits: '',
  credits_expire_at: '',
  has_active_subscription: false,
};
const createEmptyCreditsResponse = (): AdminOperationUserCreditsResponse => ({
  summary: DEFAULT_CREDIT_SUMMARY,
  items: [],
  page: 1,
  page_count: 0,
  page_size: CREDITS_PAGE_SIZE,
  total: 0,
});
const EMPTY_DETAIL: AdminOperationUserDetailResponse = {
  user_bid: '',
  mobile: '',
  email: '',
  nickname: '',
  user_status: 'unknown',
  user_role: 'unknown',
  user_roles: [],
  login_methods: [],
  language: '',
  learning_courses: [],
  learning_course_count: 0,
  created_courses: [],
  created_course_count: 0,
  registration_source: 'unknown',
  total_paid_amount: '0',
  available_credits: '',
  subscription_credits: '',
  topup_credits: '',
  credits_expire_at: '',
  has_active_subscription: false,
  last_login_at: '',
  last_learning_at: '',
  created_at: '',
  updated_at: '',
};

/**
 * t('module.operationsUser.detail.title')
 * t('module.operationsUser.detail.back')
 * t('module.operationsUser.detail.basicInfo')
 * t('module.operationsUser.detail.overview')
 * t('module.operationsUser.detail.creditsOverview')
 * t('module.operationsUser.detail.tabs.credits')
 * t('module.operationsUser.detail.tabs.learningCourses')
 * t('module.operationsUser.detail.tabs.createdCourses')
 * t('module.operationsUser.detail.loadingCredits')
 * t('module.operationsUser.detail.learningCourses')
 * t('module.operationsUser.detail.learningProgress')
 * t('module.operationsUser.detail.createdCourses')
 * t('module.operationsUser.detail.emptyCourses')
 * t('module.operationsUser.detail.emptyCredits')
 * t('module.operationsUser.detail.creditLedger')
 * t('module.operationsUser.detail.creditLedgerFilters.type')
 * t('module.operationsUser.detail.creditLedgerFilters.typeOptions.all')
 * t('module.operationsUser.detail.creditLedgerFilters.typeOptions.consume')
 * t('module.operationsUser.detail.creditLedgerFilters.typeOptions.grant')
 * t('module.operationsUser.detail.creditLedgerFilters.typeOptions.other')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSource')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.all')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.subscription')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.trial_subscription')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.topup')
 * t('module.operationsUser.detail.creditLedgerFilters.grantSourceOptions.manual')
 * t('module.operationsUser.detail.creditLedgerFilters.course')
 * t('module.operationsUser.detail.creditLedgerFilters.coursePlaceholder')
 * t('module.operationsUser.detail.creditLedgerFilters.usageMode')
 * t('module.operationsUser.detail.creditLedgerFilters.usageModeOptions.all')
 * t('module.operationsUser.detail.creditLedgerFilters.usageModeOptions.learn')
 * t('module.operationsUser.detail.creditLedgerFilters.usageModeOptions.listen')
 * t('module.operationsUser.detail.creditLedgerFilters.usageModeOptions.ask')
 * t('module.operationsUser.detail.creditLedgerFilters.time')
 * t('module.operationsUser.detail.creditLedgerFilters.timePlaceholder')
 * t('module.operationsUser.detail.creditLedgerColumns.createdAt')
 * t('module.operationsUser.detail.creditLedgerColumns.entryType')
 * t('module.operationsUser.detail.creditLedgerColumns.sourceType')
 * t('module.operationsUser.detail.creditLedgerColumns.amount')
 * t('module.operationsUser.detail.creditLedgerColumns.balanceAfter')
 * t('module.operationsUser.detail.creditLedgerColumns.expiresAt')
 * t('module.operationsUser.detail.creditLedgerColumns.note')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.adjustment')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.consume')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.debug_consume')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.expire')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.gift_expire')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.gift_grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.hold')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.learning_consume')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.manual_credit')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.manual_debit')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.manual_grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.preview_consume')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.refund')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.refund_return')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.release')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.subscription_expire')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.subscription_grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.topup_expire')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.topup_grant')
 * t('module.operationsUser.detail.creditLedgerTypeLabels.trial_subscription_grant')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.debug')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.gift')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.learning')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.manual')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.preview')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.refund')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.subscription')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.topup')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.trial_subscription')
 * t('module.operationsUser.detail.creditLedgerSourceLabels.usage')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.debug_consume')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.gift_expire')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.gift_grant')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.learning_consume')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.manual_credit')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.manual_debit')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.manual_grant')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.preview_consume')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.refund_return')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.subscription_cycle_transition')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.subscription_expire')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.subscription_grant')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.subscription_purchase')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.subscription_renewal')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.topup_expire')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.topup_grant')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.topup_purchase')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.trial_bootstrap')
 * t('module.operationsUser.detail.creditLedgerNoteLabels.trial_subscription_grant')
 * t('module.operationsUser.detail.creditExpireAtHint')
 * t('module.operationsUser.detail.creditExpireAtHintAriaLabel')
 * t('module.operationsUser.detail.creditsOverviewLabels.availableCredits')
 * t('module.operationsUser.detail.creditsOverviewLabels.subscriptionCredits')
 * t('module.operationsUser.detail.creditsOverviewLabels.topupCredits')
 * t('module.operationsUser.detail.creditsOverviewLabels.creditsExpireAt')
 * t('module.operationsUser.table.subscriptionCredits')
 * t('module.operationsUser.table.topupCredits')
 * t('module.operationsUser.table.creditsExpireAt')
 * t('module.operationsUser.credits.longTerm')
 * t('module.user.defaultUserName')
 */

const formatLearningProgress = (
  course: AdminOperationUserCourseItem,
): string => {
  const totalLessonCount = Number(course.total_lesson_count || 0);
  if (!Number.isFinite(totalLessonCount) || totalLessonCount <= 0) {
    return EMPTY_VALUE;
  }

  const completedLessonCount = Math.max(
    0,
    Math.min(Number(course.completed_lesson_count || 0), totalLessonCount),
  );
  const progressPercent = Math.round(
    (completedLessonCount / totalLessonCount) * 100,
  );
  return `${progressPercent}% (${completedLessonCount}/${totalLessonCount})`;
};

export default function AdminOperationUserDetailPage() {
  const { t, i18n } = useTranslation();
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');
  const { t: tOperationsCourse } = useTranslation('module.operationsCourse');
  const router = useRouter();
  const params = useParams<{ user_bid: string }>();
  const { isReady } = useOperatorGuard();
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const currencySymbol = useEnvStore(
    (state: EnvStoreState) => state.currencySymbol || '',
  );
  const defaultUserName = useMemo(() => t('module.user.defaultUserName'), [t]);
  const detailTabsSectionRef = useRef<HTMLDivElement | null>(null);
  const hasInitializedCreditStateRef = useRef(false);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState<ErrorState | null>(null);
  const [creditsLoading, setCreditsLoading] = useState(true);
  const [creditsError, setCreditsError] = useState<ErrorState | null>(null);
  const [detailRetryNonce, setDetailRetryNonce] = useState(0);
  const [creditsRetryNonce, setCreditsRetryNonce] = useState(0);
  const [creditsPageIndex, setCreditsPageIndex] = useState(1);
  const [creditFiltersDraft, setCreditFiltersDraft] =
    useState<AdminOperationUserCreditFilters>(createUserCreditFilters);
  const [creditFilters, setCreditFilters] =
    useState<AdminOperationUserCreditFilters>(createUserCreditFilters);
  const [activeTab, setActiveTab] = useState<DetailTab>('credits');
  const [detail, setDetail] =
    useState<AdminOperationUserDetailResponse>(EMPTY_DETAIL);
  const [credits, setCredits] = useState<AdminOperationUserCreditsResponse>(
    createEmptyCreditsResponse,
  );

  const userBidState = useMemo(() => {
    const rawUserBid = String(params?.user_bid || '').trim();
    if (!rawUserBid) {
      return {
        userBid: '',
        errorMessage: t('server.common.paramsError'),
      };
    }

    try {
      return {
        userBid: decodeURIComponent(rawUserBid),
        errorMessage: '',
      };
    } catch {
      return {
        userBid: '',
        errorMessage: t('server.common.paramsError'),
      };
    }
  }, [params, t]);
  const userBid = userBidState.userBid;
  const contactType = useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const contactLabel = useMemo(
    () =>
      contactType === 'email'
        ? tOperationsUsers('table.email')
        : tOperationsUsers('table.mobile'),
    [contactType, tOperationsUsers],
  );
  const contactValue = useMemo(
    () =>
      contactType === 'email'
        ? detail.email || detail.mobile
        : detail.mobile || detail.email,
    [contactType, detail.email, detail.mobile],
  );
  const creditSummary = useMemo<AdminOperationUserCreditSummary>(
    () => ({
      available_credits:
        credits.summary.available_credits || detail.available_credits || '',
      subscription_credits:
        credits.summary.subscription_credits ||
        detail.subscription_credits ||
        '',
      topup_credits:
        credits.summary.topup_credits || detail.topup_credits || '',
      credits_expire_at:
        credits.summary.credits_expire_at || detail.credits_expire_at || '',
      has_active_subscription:
        credits.summary.has_active_subscription ||
        detail.has_active_subscription,
    }),
    [
      credits.summary.available_credits,
      credits.summary.credits_expire_at,
      credits.summary.has_active_subscription,
      credits.summary.subscription_credits,
      credits.summary.topup_credits,
      detail.available_credits,
      detail.credits_expire_at,
      detail.has_active_subscription,
      detail.subscription_credits,
      detail.topup_credits,
    ],
  );
  const scrollToDetailTabsSection = useCallback(() => {
    detailTabsSectionRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    });
  }, []);
  const syncDetailTabHash = useCallback((nextTab: DetailTab) => {
    if (typeof window === 'undefined') {
      return;
    }
    const nextHash = DETAIL_TAB_HASHES[nextTab];
    if (window.location.hash === nextHash) {
      return;
    }
    const nextUrl = `${window.location.pathname}${window.location.search}${nextHash}`;
    window.history.replaceState(window.history.state, '', nextUrl);
  }, []);
  const setDetailTab = useCallback(
    (nextTab: DetailTab, options?: { scrollToSection?: boolean }) => {
      setActiveTab(nextTab);
      syncDetailTabHash(nextTab);
      if (options?.scrollToSection) {
        scrollToDetailTabsSection();
      }
    },
    [scrollToDetailTabsSection, syncDetailTabHash],
  );

  useEffect(() => {
    if (!isReady) {
      return;
    }

    if (userBidState.errorMessage) {
      setDetailError({ message: userBidState.errorMessage });
      setDetailLoading(false);
      return;
    }

    let cancelled = false;

    const fetchDetail = async () => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const response = (await api.getAdminOperationUserDetail({
          user_bid: userBid,
        })) as AdminOperationUserDetailResponse;
        if (cancelled) {
          return;
        }
        setDetail(response);
      } catch (requestError) {
        if (cancelled) {
          return;
        }
        const resolvedError = requestError as ErrorWithCode;
        setDetailError({
          message: resolvedError.message || t('common.core.networkError'),
          code: resolvedError.code,
        });
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    };

    void fetchDetail();

    return () => {
      cancelled = true;
    };
  }, [detailRetryNonce, isReady, t, userBid, userBidState.errorMessage]);

  useEffect(() => {
    if (!hasInitializedCreditStateRef.current) {
      hasInitializedCreditStateRef.current = true;
      return;
    }
    setCreditsPageIndex(1);
    setCreditsError(null);
    setCredits(createEmptyCreditsResponse());
    setCreditFiltersDraft(createUserCreditFilters());
    setCreditFilters(createUserCreditFilters());
    setActiveTab('credits');
    syncDetailTabHash('credits');
  }, [syncDetailTabHash, userBid]);

  useEffect(() => {
    if (!isReady || !userBid || userBidState.errorMessage) {
      return;
    }

    let cancelled = false;

    const fetchCredits = async () => {
      setCreditsLoading(true);
      setCreditsError(null);
      try {
        const response = (await api.getAdminOperationUserCredits({
          user_bid: userBid,
          page_index: creditsPageIndex,
          page_size: CREDITS_PAGE_SIZE,
          credit_type:
            creditFilters.creditType === FILTER_ALL_OPTION
              ? ''
              : creditFilters.creditType,
          grant_source:
            creditFilters.creditType === 'grant' &&
            creditFilters.grantSource !== FILTER_ALL_OPTION
              ? creditFilters.grantSource
              : '',
          course_query:
            creditFilters.creditType === 'consume'
              ? creditFilters.courseQuery.trim()
              : '',
          usage_mode:
            creditFilters.creditType === 'consume' &&
            creditFilters.usageMode !== FILTER_ALL_OPTION
              ? creditFilters.usageMode
              : '',
          start_time:
            creditFilters.creditType !== FILTER_ALL_OPTION
              ? creditFilters.startTime
              : '',
          end_time:
            creditFilters.creditType !== FILTER_ALL_OPTION
              ? creditFilters.endTime
              : '',
        })) as AdminOperationUserCreditsResponse;
        if (cancelled) {
          return;
        }
        setCredits(response);
      } catch (requestError) {
        if (cancelled) {
          return;
        }
        const resolvedError = requestError as ErrorWithCode;
        setCreditsError({
          message: resolvedError.message || t('common.core.networkError'),
          code: resolvedError.code,
        });
        setCredits(current => ({
          ...current,
          items: [],
          page: creditsPageIndex,
          page_count: 0,
          total: 0,
        }));
      } finally {
        if (!cancelled) {
          setCreditsLoading(false);
        }
      }
    };

    void fetchCredits();

    return () => {
      cancelled = true;
    };
  }, [
    creditsPageIndex,
    creditFilters,
    creditsRetryNonce,
    isReady,
    t,
    userBid,
    userBidState.errorMessage,
  ]);

  const handleCreditSearch = () => {
    const nextFilters = sanitizeCreditFiltersByType({
      ...creditFiltersDraft,
      courseQuery: creditFiltersDraft.courseQuery.trim(),
    });
    setCreditFiltersDraft(nextFilters);
    setCreditFilters(nextFilters);
    setCreditsPageIndex(1);
  };

  const handleCreditReset = () => {
    const nextFilters = createUserCreditFilters();
    setCreditFiltersDraft(nextFilters);
    setCreditFilters(nextFilters);
    setCreditsPageIndex(1);
  };

  useEffect(() => {
    if (typeof window === 'undefined' || detailLoading) {
      return;
    }

    const hashTab = resolveDetailTabFromHash(window.location.hash);
    if (!hashTab) {
      return;
    }

    setActiveTab(hashTab);
    scrollToDetailTabsSection();
  }, [detailLoading, scrollToDetailTabsSection]);

  const resolveRoleLabel = useCallback(
    (role: string) => tOperationsUsers(`roleLabels.${role || 'unknown'}`),
    [tOperationsUsers],
  );
  const resolveRegistrationSourceLabel = useCallback(
    (source: string) =>
      tOperationsUsers(`registrationSourceLabels.${source || 'unknown'}`),
    [tOperationsUsers],
  );
  const resolveCourseStatusLabel = (status: string) => {
    if (status === 'published') {
      return tOperationsCourse('statusLabels.published');
    }
    if (status === 'unpublished') {
      return tOperationsCourse('statusLabels.unpublished');
    }
    const unknownLabel = tOperationsCourse('statusLabels.unknown');
    return status ? `${unknownLabel} (${status})` : unknownLabel;
  };
  const resolveCreditsExpireAt = useCallback(() => {
    if (creditSummary.credits_expire_at) {
      return formatOperatorNaiveDateTime(creditSummary.credits_expire_at);
    }
    if (Number(creditSummary.available_credits || 0) > 0) {
      return tOperationsUsers('credits.longTerm');
    }
    return EMPTY_VALUE;
  }, [
    creditSummary.available_credits,
    creditSummary.credits_expire_at,
    tOperationsUsers,
  ]);
  const creditExpireAtLabel = useMemo(
    () => (
      <>
        <span>
          {tOperationsUsers('detail.creditsOverviewLabels.creditsExpireAt')}
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type='button'
              aria-label={tOperationsUsers(
                'detail.creditExpireAtHintAriaLabel',
              )}
              className='inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground'
            >
              <CircleHelp className='h-3.5 w-3.5' />
            </button>
          </TooltipTrigger>
          <TooltipContent
            side='top'
            className='max-w-[220px] text-center'
          >
            {tOperationsUsers('detail.creditExpireAtHint')}
          </TooltipContent>
        </Tooltip>
      </>
    ),
    [tOperationsUsers],
  );
  const basicInfoItems = useMemo(
    () => [
      {
        key: 'contact',
        label: contactLabel,
        value: contactValue,
      },
      {
        key: 'nickname',
        label: tOperationsUsers('table.nickname'),
        value: detail.nickname || defaultUserName,
      },
      {
        key: 'role',
        label: tOperationsUsers('table.role'),
        value: resolveRoleLabel(detail.user_role),
      },
      {
        key: 'registrationSource',
        label: tOperationsUsers('table.registrationSource'),
        value: resolveRegistrationSourceLabel(detail.registration_source),
      },
      {
        key: 'lastLoginAt',
        label: tOperationsUsers('table.lastLoginAt'),
        value: formatOperatorNaiveDateTime(detail.last_login_at),
      },
      {
        key: 'createdAt',
        label: tOperationsUsers('table.createdAt'),
        value: formatOperatorNaiveDateTime(detail.created_at),
      },
    ],
    [
      contactLabel,
      contactValue,
      defaultUserName,
      detail.created_at,
      detail.last_login_at,
      detail.nickname,
      detail.registration_source,
      detail.user_role,
      resolveRegistrationSourceLabel,
      resolveRoleLabel,
      tOperationsUsers,
    ],
  );
  const overviewItems = useMemo(
    () => [
      {
        key: 'totalPaidAmount',
        label: tOperationsUsers('table.totalPaidAmount'),
        value: `${currencySymbol}${detail.total_paid_amount || '0'}`,
      },
      {
        key: 'learningCourses',
        label: tOperationsUsers('table.learningCourses'),
        value: String(
          resolveCourseCount(
            detail.learning_course_count,
            detail.learning_courses,
          ),
        ),
        valueClassName: 'text-primary',
        valueAriaLabel: tOperationsUsers('table.learningCourses'),
        onClick: () => setDetailTab('learning', { scrollToSection: true }),
      },
      {
        key: 'createdCourses',
        label: tOperationsUsers('table.createdCourses'),
        value: String(
          resolveCourseCount(
            detail.created_course_count,
            detail.created_courses,
          ),
        ),
        valueClassName: 'text-primary',
        valueAriaLabel: tOperationsUsers('table.createdCourses'),
        onClick: () => setDetailTab('created', { scrollToSection: true }),
      },
      {
        key: 'lastLearningAt',
        label: tOperationsUsers('table.lastLearningAt'),
        value: formatOperatorNaiveDateTime(detail.last_learning_at),
      },
    ],
    [
      currencySymbol,
      detail.created_course_count,
      detail.created_courses,
      detail.last_learning_at,
      detail.learning_course_count,
      detail.learning_courses,
      detail.total_paid_amount,
      setDetailTab,
      tOperationsUsers,
    ],
  );
  const creditsOverviewItems = useMemo(
    () => [
      {
        key: 'availableCredits',
        label: tOperationsUsers(
          'detail.creditsOverviewLabels.availableCredits',
        ),
        value: creditSummary.available_credits
          ? formatAdminCredits(
              Number(creditSummary.available_credits),
              i18n.language,
            )
          : '',
      },
      {
        key: 'subscriptionCredits',
        label: tOperationsUsers(
          'detail.creditsOverviewLabels.subscriptionCredits',
        ),
        value: creditSummary.subscription_credits
          ? formatAdminCredits(
              Number(creditSummary.subscription_credits),
              i18n.language,
            )
          : '',
      },
      {
        key: 'topupCredits',
        label: tOperationsUsers('detail.creditsOverviewLabels.topupCredits'),
        value: creditSummary.topup_credits
          ? formatAdminCredits(
              Number(creditSummary.topup_credits),
              i18n.language,
            )
          : '',
      },
      {
        key: 'creditsExpireAt',
        label: creditExpireAtLabel,
        value: resolveCreditsExpireAt(),
      },
    ],
    [
      creditExpireAtLabel,
      creditSummary.available_credits,
      creditSummary.subscription_credits,
      creditSummary.topup_credits,
      i18n.language,
      resolveCreditsExpireAt,
      tOperationsUsers,
    ],
  );

  if (!isReady || detailLoading) {
    return <Loading />;
  }

  if (detailError) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={detailError.code || 0}
          errorMessage={detailError.message}
          onRetry={() => setDetailRetryNonce(value => value + 1)}
        />
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={150}>
      <div
        className='h-full min-h-0 overflow-hidden bg-stone-50 p-0 overscroll-none'
        data-testid='admin-operation-user-detail-page'
      >
        <div className='mx-auto flex h-full min-h-0 w-full max-w-7xl flex-col overflow-hidden'>
          <div className='mb-5 flex shrink-0 flex-col gap-3 px-1 pt-6 sm:flex-row sm:items-start sm:justify-between'>
            <div>
              <h1 className='text-2xl font-semibold text-gray-900'>
                {tOperationsUsers('detail.title')}
              </h1>
            </div>
            <Button
              variant='outline'
              className='sm:mr-3'
              onClick={() => router.push('/admin/operations/users')}
            >
              {tOperationsUsers('detail.back')}
            </Button>
          </div>

          <div className='min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain pr-1'>
            <div className='space-y-5 px-1 pb-6'>
              <UserDetailSummarySection
                emptyValue={EMPTY_VALUE}
                basicInfoTitle={tOperationsUsers('detail.basicInfo')}
                basicInfoItems={basicInfoItems}
                overviewTitle={tOperationsUsers('detail.overview')}
                overviewItems={overviewItems}
              />

              <UserDetailTabsSection
                sectionRef={detailTabsSectionRef}
                activeTab={activeTab}
                emptyValue={EMPTY_VALUE}
                creditsOverviewTitle={tOperationsUsers(
                  'detail.creditsOverview',
                )}
                creditsOverviewItems={creditsOverviewItems}
                creditsTabLabel={tOperationsUsers('detail.tabs.credits')}
                learningTabLabel={tOperationsUsers(
                  'detail.tabs.learningCourses',
                )}
                createdTabLabel={tOperationsUsers('detail.tabs.createdCourses')}
                onTabChange={setDetailTab}
                creditLedgerProps={{
                  filtersDraft: creditFiltersDraft,
                  loading: creditsLoading,
                  error: creditsError,
                  items: credits.items,
                  pageIndex: credits.page || creditsPageIndex,
                  pageCount: credits.page_count || 0,
                  onFiltersChange: setCreditFiltersDraft,
                  onSearch: handleCreditSearch,
                  onReset: handleCreditReset,
                  onPageChange: page => setCreditsPageIndex(page),
                  onRetry: () => setCreditsRetryNonce(value => value + 1),
                }}
                learningCoursesProps={{
                  title: tOperationsUsers('detail.learningCourses'),
                  courses: detail.learning_courses || [],
                  emptyText: tOperationsUsers('detail.emptyCourses'),
                  courseNameLabel: tOperationsUsers(
                    'courseSummary.dialog.courseName',
                  ),
                  courseIdLabel: tOperationsUsers(
                    'courseSummary.dialog.courseId',
                  ),
                  valueLabel: tOperationsUsers('detail.learningProgress'),
                  renderValue: formatLearningProgress,
                }}
                createdCoursesProps={{
                  title: tOperationsUsers('detail.createdCourses'),
                  courses: detail.created_courses || [],
                  emptyText: tOperationsUsers('detail.emptyCourses'),
                  courseNameLabel: tOperationsUsers(
                    'courseSummary.dialog.courseName',
                  ),
                  courseIdLabel: tOperationsUsers(
                    'courseSummary.dialog.courseId',
                  ),
                  valueLabel: tOperationsUsers('courseSummary.dialog.status'),
                  renderValue: course =>
                    resolveCourseStatusLabel(course.course_status),
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
