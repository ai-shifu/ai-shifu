'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { CircleHelp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTimezoneHint from '@/app/admin/components/AdminTimezoneHint';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import { cn } from '@/lib/utils';
import { buildAdminOperationsCourseDetailUrl } from '../../operation-course-routes';
import { formatOperatorUtcDateTime } from '../dateTime';
import { normalizeLoginMethodLabelKey } from '../loginMethodUtils';
import type {
  AdminOperationUserCourseItem,
  AdminOperationUserCreditSummary,
  AdminOperationUserCreditsResponse,
  AdminOperationUserDetailResponse,
} from '../../operation-user-types';
import useOperatorGuard from '../../useOperatorGuard';

type ErrorState = { message: string; code?: number };
type DetailTab = 'credits' | 'learning' | 'created';

const CREDITS_PAGE_SIZE = 10;
const EMPTY_VALUE = '--';
const DEFAULT_VISIBLE_COURSE_COUNT = 10;
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
type OperatorUsersTranslator = (
  key: string,
  options?: { defaultValue?: string },
) => string;
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
  created_courses: [],
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

const InfoItem = ({
  label,
  value,
}: {
  label: React.ReactNode;
  value?: string;
}) => (
  <div className='space-y-1 rounded-lg border border-border/70 bg-muted/20 px-4 py-3'>
    <div className='flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground'>
      {label}
    </div>
    <div className='break-all text-sm font-medium text-foreground'>
      {value && value.trim().length > 0 ? value : EMPTY_VALUE}
    </div>
  </div>
);

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

const resolveCreditLedgerLabel = (
  tOperationsUsers: OperatorUsersTranslator,
  type: 'creditLedgerTypeLabels' | 'creditLedgerSourceLabels',
  displayCode: string,
  fallbackCode: string,
): string => {
  const normalizedDisplayCode = displayCode.trim();
  if (normalizedDisplayCode) {
    return tOperationsUsers(`detail.${type}.${normalizedDisplayCode}`, {
      defaultValue: normalizedDisplayCode,
    });
  }
  return fallbackCode.trim() || EMPTY_VALUE;
};

const resolveCreditLedgerNote = (note: string): string => {
  const normalizedNote = note.trim();
  if (normalizedNote) {
    return normalizedNote;
  }
  return EMPTY_VALUE;
};

const CourseTable = ({
  title,
  courses,
  emptyText,
  courseNameLabel,
  courseIdLabel,
  valueLabel,
  renderValue,
  courseNameAlign = 'center',
}: {
  title: string;
  courses: AdminOperationUserCourseItem[];
  emptyText: string;
  courseNameLabel: string;
  courseIdLabel: string;
  valueLabel: string;
  renderValue: (course: AdminOperationUserCourseItem) => string;
  courseNameAlign?: 'left' | 'center';
}) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const shouldShowToggle = courses.length > DEFAULT_VISIBLE_COURSE_COUNT;
  const visibleCourses = expanded
    ? courses
    : courses.slice(0, DEFAULT_VISIBLE_COURSE_COUNT);
  const toggleLabel = `${expanded ? t('common.core.collapse') : t('common.core.expand')} ${title}`;

  useEffect(() => {
    if (!shouldShowToggle && expanded) {
      setExpanded(false);
    }
  }, [expanded, shouldShowToggle]);

  useEffect(() => {
    setExpanded(false);
  }, [courses, title]);

  return (
    <Card className='shadow-sm'>
      <CardHeader className='pb-3'>
        <CardTitle className='text-base font-semibold'>{title}</CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        <TooltipProvider delayDuration={150}>
          <Table className='table-fixed'>
            <colgroup>
              <col className='w-[38%]' />
              <col className='w-[42%]' />
              <col className='w-[20%]' />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead className='text-center'>{courseNameLabel}</TableHead>
                <TableHead className='text-center'>{courseIdLabel}</TableHead>
                <TableHead className='text-center'>{valueLabel}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {courses.length ? (
                visibleCourses.map(course => {
                  const courseDetailUrl = buildAdminOperationsCourseDetailUrl(
                    course.shifu_bid,
                  );
                  return (
                    <TableRow key={`${title}-${course.shifu_bid}`}>
                      <TableCell
                        className={cn(
                          'max-w-0 overflow-hidden text-ellipsis whitespace-nowrap',
                          courseNameAlign === 'left'
                            ? 'text-left'
                            : 'text-center',
                        )}
                      >
                        {courseDetailUrl ? (
                          <Link
                            href={courseDetailUrl}
                            className={cn(
                              'inline-block max-w-full text-primary transition-colors hover:text-primary/80 hover:underline',
                              courseNameAlign === 'left' && 'align-top',
                            )}
                          >
                            <AdminTooltipText
                              text={course.course_name}
                              emptyValue={EMPTY_VALUE}
                            />
                          </Link>
                        ) : (
                          <AdminTooltipText
                            text={course.course_name}
                            emptyValue={EMPTY_VALUE}
                          />
                        )}
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={course.shifu_bid}
                          emptyValue={EMPTY_VALUE}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={renderValue(course)}
                          emptyValue={EMPTY_VALUE}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })
              ) : (
                <TableEmpty colSpan={3}>{emptyText}</TableEmpty>
              )}
            </TableBody>
          </Table>
        </TooltipProvider>

        {shouldShowToggle ? (
          <div className='flex justify-end'>
            <Button
              type='button'
              variant='link'
              size='sm'
              className='h-auto px-0 py-0 text-sm'
              aria-label={toggleLabel}
              title={toggleLabel}
              onClick={() => setExpanded(previous => !previous)}
            >
              {expanded ? t('common.core.collapse') : t('common.core.expand')}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};

const CreditLedgerTable = ({
  loading,
  error,
  items,
  pageIndex,
  pageCount,
  onPageChange,
  onRetry,
}: {
  loading: boolean;
  error: ErrorState | null;
  items: AdminOperationUserCreditsResponse['items'];
  pageIndex: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  onRetry: () => void;
}) => {
  const { t } = useTranslation();
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');

  if (error) {
    return (
      <div className='rounded-xl border border-border bg-white p-4 shadow-sm'>
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
          onRetry={onRetry}
        />
      </div>
    );
  }

  return (
    <Card
      className='shadow-sm'
      data-testid='admin-operation-user-credit-ledger-card'
    >
      <CardHeader className='pb-3'>
        <CardTitle className='text-base font-semibold'>
          {tOperationsUsers('detail.creditLedger')}
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-4'>
        <TooltipProvider delayDuration={150}>
          <div
            className='overflow-auto'
            data-testid='admin-operation-user-credit-ledger-scroll'
          >
            <Table className='table-fixed'>
              <colgroup>
                <col className='w-[16%]' />
                <col className='w-[13%]' />
                <col className='w-[12%]' />
                <col className='w-[10%]' />
                <col className='w-[11%]' />
                <col className='w-[14%]' />
                <col className='w-[24%]' />
              </colgroup>
              <TableHeader>
                <TableRow>
                  <TableHead className='text-center'>
                    {tOperationsUsers('detail.creditLedgerColumns.createdAt')}
                  </TableHead>
                  <TableHead className='text-center'>
                    {tOperationsUsers('detail.creditLedgerColumns.entryType')}
                  </TableHead>
                  <TableHead className='text-center'>
                    {tOperationsUsers('detail.creditLedgerColumns.sourceType')}
                  </TableHead>
                  <TableHead className='text-center'>
                    {tOperationsUsers('detail.creditLedgerColumns.amount')}
                  </TableHead>
                  <TableHead className='text-center'>
                    {tOperationsUsers(
                      'detail.creditLedgerColumns.balanceAfter',
                    )}
                  </TableHead>
                  <TableHead className='text-center'>
                    {tOperationsUsers('detail.creditLedgerColumns.expiresAt')}
                  </TableHead>
                  <TableHead className='text-center'>
                    {tOperationsUsers('detail.creditLedgerColumns.note')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableEmpty colSpan={7}>
                    {tOperationsUsers('detail.loadingCredits')}
                  </TableEmpty>
                ) : items.length ? (
                  items.map(item => (
                    <TableRow key={item.ledger_bid}>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={formatOperatorUtcDateTime(item.created_at)}
                          emptyValue={EMPTY_VALUE}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={resolveCreditLedgerLabel(
                            tOperationsUsers,
                            'creditLedgerTypeLabels',
                            item.display_entry_type,
                            item.entry_type,
                          )}
                          emptyValue={EMPTY_VALUE}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={resolveCreditLedgerLabel(
                            tOperationsUsers,
                            'creditLedgerSourceLabels',
                            item.display_source_type,
                            item.source_type,
                          )}
                          emptyValue={EMPTY_VALUE}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={item.amount}
                          emptyValue={EMPTY_VALUE}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={item.balance_after}
                          emptyValue={EMPTY_VALUE}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={formatOperatorUtcDateTime(item.expires_at)}
                          emptyValue={EMPTY_VALUE}
                        />
                      </TableCell>
                      <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                        <AdminTooltipText
                          text={resolveCreditLedgerNote(item.note)}
                          emptyValue={EMPTY_VALUE}
                        />
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableEmpty colSpan={7}>
                    {tOperationsUsers('detail.emptyCredits')}
                  </TableEmpty>
                )}
              </TableBody>
            </Table>
          </div>
        </TooltipProvider>

        {pageCount > 1 ? (
          <AdminPagination
            pageIndex={pageIndex}
            pageCount={pageCount}
            onPageChange={onPageChange}
            prevLabel={t('module.order.paginationPrev', 'Previous')}
            nextLabel={t('module.order.paginationNext', 'Next')}
            prevAriaLabel={t(
              'module.order.paginationPrevAriaLabel',
              'Go to previous page',
            )}
            nextAriaLabel={t(
              'module.order.paginationNextAriaLabel',
              'Go to next page',
            )}
            className='justify-end w-auto mx-0'
          />
        ) : null}
      </CardContent>
    </Card>
  );
};

export default function AdminOperationUserDetailPage() {
  const { t } = useTranslation();
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
  const creditsSectionRef = useRef<HTMLDivElement | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState<ErrorState | null>(null);
  const [creditsLoading, setCreditsLoading] = useState(true);
  const [creditsError, setCreditsError] = useState<ErrorState | null>(null);
  const [detailRetryNonce, setDetailRetryNonce] = useState(0);
  const [creditsRetryNonce, setCreditsRetryNonce] = useState(0);
  const [creditsPageIndex, setCreditsPageIndex] = useState(1);
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
    setCreditsPageIndex(1);
    setCreditsError(null);
    setCredits(createEmptyCreditsResponse());
    setActiveTab('credits');
  }, [userBid]);

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
    creditsRetryNonce,
    isReady,
    t,
    userBid,
    userBidState.errorMessage,
  ]);

  useEffect(() => {
    if (typeof window === 'undefined' || detailLoading) {
      return;
    }
    if (window.location.hash !== '#credits') {
      return;
    }

    setActiveTab('credits');
    creditsSectionRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    });
  }, [detailLoading]);

  const resolveStatusLabel = (status: string) =>
    tOperationsUsers(`statusLabels.${status || 'unknown'}`);
  const resolveRoleLabel = (role: string) =>
    tOperationsUsers(`roleLabels.${role || 'unknown'}`);
  const resolveRegistrationSourceLabel = (source: string) =>
    tOperationsUsers(`registrationSourceLabels.${source || 'unknown'}`);
  const resolveLoginMethods = (methods: string[]) =>
    methods.length
      ? methods
          .map(method =>
            tOperationsUsers(
              `loginMethodLabels.${normalizeLoginMethodLabelKey(method)}`,
            ),
          )
          .join(' / ')
      : EMPTY_VALUE;
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
  const resolveCreditsExpireAt = () => {
    if (creditSummary.credits_expire_at) {
      return formatOperatorUtcDateTime(creditSummary.credits_expire_at);
    }
    if (Number(creditSummary.available_credits || 0) > 0) {
      return tOperationsUsers('credits.longTerm');
    }
    return EMPTY_VALUE;
  };
  const creditExpireAtLabel = (
    <>
      <span>
        {tOperationsUsers('detail.creditsOverviewLabels.creditsExpireAt')}
      </span>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type='button'
            aria-label={tOperationsUsers('detail.creditExpireAtHintAriaLabel')}
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
              <AdminTimezoneHint
                namespace='module.operationsUser'
                textKey='detail.timezoneHint'
                className='mt-1'
              />
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
              <Card className='shadow-sm'>
                <CardHeader className='pb-3'>
                  <CardTitle className='text-base font-semibold'>
                    {tOperationsUsers('detail.basicInfo')}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
                    <InfoItem
                      label={tOperationsUsers('table.userId')}
                      value={detail.user_bid}
                    />
                    <InfoItem
                      label={contactLabel}
                      value={contactValue}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.nickname')}
                      value={detail.nickname || defaultUserName}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.status')}
                      value={resolveStatusLabel(detail.user_status)}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.role')}
                      value={resolveRoleLabel(detail.user_role)}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.loginMethods')}
                      value={resolveLoginMethods(detail.login_methods)}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.registrationSource')}
                      value={resolveRegistrationSourceLabel(
                        detail.registration_source,
                      )}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.lastLoginAt')}
                      value={formatOperatorUtcDateTime(detail.last_login_at)}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.updatedAt')}
                      value={formatOperatorUtcDateTime(detail.updated_at)}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.createdAt')}
                      value={formatOperatorUtcDateTime(detail.created_at)}
                    />
                  </div>
                </CardContent>
              </Card>

              <Card className='shadow-sm'>
                <CardHeader className='pb-3'>
                  <CardTitle className='text-base font-semibold'>
                    {tOperationsUsers('detail.overview')}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
                    <InfoItem
                      label={tOperationsUsers('table.totalPaidAmount')}
                      value={`${currencySymbol}${detail.total_paid_amount || '0'}`}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.learningCourses')}
                      value={String((detail.learning_courses || []).length)}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.createdCourses')}
                      value={String((detail.created_courses || []).length)}
                    />
                    <InfoItem
                      label={tOperationsUsers('table.lastLearningAt')}
                      value={formatOperatorUtcDateTime(detail.last_learning_at)}
                    />
                  </div>
                </CardContent>
              </Card>

              <div
                id='credits'
                ref={creditsSectionRef}
                className='space-y-5'
              >
                <Card className='shadow-sm'>
                  <CardHeader className='pb-3'>
                    <CardTitle className='text-base font-semibold'>
                      {tOperationsUsers('detail.creditsOverview')}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
                      <InfoItem
                        label={tOperationsUsers(
                          'detail.creditsOverviewLabels.availableCredits',
                        )}
                        value={creditSummary.available_credits}
                      />
                      <InfoItem
                        label={tOperationsUsers(
                          'detail.creditsOverviewLabels.subscriptionCredits',
                        )}
                        value={creditSummary.subscription_credits}
                      />
                      <InfoItem
                        label={tOperationsUsers(
                          'detail.creditsOverviewLabels.topupCredits',
                        )}
                        value={creditSummary.topup_credits}
                      />
                      <InfoItem
                        label={creditExpireAtLabel}
                        value={resolveCreditsExpireAt()}
                      />
                    </div>
                  </CardContent>
                </Card>

                <Tabs
                  className='space-y-4'
                  value={activeTab}
                  onValueChange={value => setActiveTab(value as DetailTab)}
                >
                  <TabsList>
                    <TabsTrigger value='credits'>
                      {tOperationsUsers('detail.tabs.credits')}
                    </TabsTrigger>
                    <TabsTrigger value='learning'>
                      {tOperationsUsers('detail.tabs.learningCourses')}
                    </TabsTrigger>
                    <TabsTrigger value='created'>
                      {tOperationsUsers('detail.tabs.createdCourses')}
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent
                    value='credits'
                    className='mt-0'
                  >
                    <CreditLedgerTable
                      loading={creditsLoading}
                      error={creditsError}
                      items={credits.items}
                      pageIndex={credits.page || creditsPageIndex}
                      pageCount={credits.page_count || 0}
                      onPageChange={page => setCreditsPageIndex(page)}
                      onRetry={() => setCreditsRetryNonce(value => value + 1)}
                    />
                  </TabsContent>

                  <TabsContent
                    value='learning'
                    className='mt-0'
                  >
                    <CourseTable
                      title={tOperationsUsers('detail.learningCourses')}
                      courses={detail.learning_courses || []}
                      emptyText={tOperationsUsers('detail.emptyCourses')}
                      courseNameLabel={tOperationsUsers(
                        'courseSummary.dialog.courseName',
                      )}
                      courseIdLabel={tOperationsUsers(
                        'courseSummary.dialog.courseId',
                      )}
                      valueLabel={tOperationsUsers('detail.learningProgress')}
                      renderValue={formatLearningProgress}
                      courseNameAlign='left'
                    />
                  </TabsContent>

                  <TabsContent
                    value='created'
                    className='mt-0'
                  >
                    <CourseTable
                      title={tOperationsUsers('detail.createdCourses')}
                      courses={detail.created_courses || []}
                      emptyText={tOperationsUsers('detail.emptyCourses')}
                      courseNameLabel={tOperationsUsers(
                        'courseSummary.dialog.courseName',
                      )}
                      courseIdLabel={tOperationsUsers(
                        'courseSummary.dialog.courseId',
                      )}
                      valueLabel={tOperationsUsers(
                        'courseSummary.dialog.status',
                      )}
                      renderValue={course =>
                        resolveCourseStatusLabel(course.course_status)
                      }
                      courseNameAlign='left'
                    />
                  </TabsContent>
                </Tabs>
              </div>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
