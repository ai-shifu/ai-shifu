'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import AdminOverflowTooltipText from '@/app/admin/components/AdminOverflowTooltipText';
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
import type { EnvStoreState } from '@/c-types/store';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { ErrorWithCode } from '@/lib/request';
import { cn } from '@/lib/utils';
import { buildAdminOperationsCourseDetailUrl } from '../../operation-course-routes';
import { normalizeLoginMethodLabelKey } from '../loginMethodUtils';
import type {
  AdminOperationUserCourseItem,
  AdminOperationUserDetailResponse,
} from '../../operation-user-types';
import useOperatorGuard from '../../useOperatorGuard';

type ErrorState = { message: string; code?: number };

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
  last_login_at: '',
  last_learning_at: '',
  created_at: '',
  updated_at: '',
};

const EMPTY_VALUE = '--';
const DEFAULT_VISIBLE_COURSE_COUNT = 10;

/**
 * t('module.operationsUser.detail.title')
 * t('module.operationsUser.detail.back')
 * t('module.operationsUser.detail.basicInfo')
 * t('module.operationsUser.detail.overview')
 * t('module.operationsUser.detail.learningCourses')
 * t('module.operationsUser.detail.learningProgress')
 * t('module.operationsUser.detail.createdCourses')
 * t('module.operationsUser.detail.emptyCourses')
 * t('module.user.defaultUserName')
 */

const InfoItem = ({ label, value }: { label: string; value?: string }) => (
  <div className='space-y-1 rounded-lg border border-border/70 bg-muted/20 px-4 py-3'>
    <div className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>
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
                          <AdminOverflowTooltipText
                            text={course.course_name}
                            emptyValue={EMPTY_VALUE}
                          />
                        </Link>
                      ) : (
                        <AdminOverflowTooltipText
                          text={course.course_name}
                          emptyValue={EMPTY_VALUE}
                        />
                      )}
                    </TableCell>
                    <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                      <AdminOverflowTooltipText
                        text={course.shifu_bid}
                        emptyValue={EMPTY_VALUE}
                      />
                    </TableCell>
                    <TableCell className='max-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-center'>
                      <AdminOverflowTooltipText
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ErrorState | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const [detail, setDetail] =
    useState<AdminOperationUserDetailResponse>(EMPTY_DETAIL);

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

  useEffect(() => {
    if (!isReady) {
      return;
    }

    if (userBidState.errorMessage) {
      setError({ message: userBidState.errorMessage });
      setLoading(false);
      return;
    }

    let cancelled = false;

    const fetchDetail = async () => {
      setLoading(true);
      setError(null);
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
        setError({
          message: resolvedError.message || t('common.core.networkError'),
          code: resolvedError.code,
        });
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchDetail();

    return () => {
      cancelled = true;
    };
  }, [isReady, retryNonce, t, userBid, userBidState.errorMessage]);

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

  if (!isReady || loading) {
    return <Loading />;
  }

  if (error) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
          onRetry={() => setRetryNonce(value => value + 1)}
        />
      </div>
    );
  }

  return (
    <div className='h-full overflow-auto'>
      <div className='mx-auto max-w-7xl space-y-5 px-1 py-6'>
        <div className='flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between'>
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
                value={detail.last_login_at}
              />
              <InfoItem
                label={tOperationsUsers('table.updatedAt')}
                value={detail.updated_at}
              />
              <InfoItem
                label={tOperationsUsers('table.createdAt')}
                value={detail.created_at}
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
                value={detail.last_learning_at}
              />
            </div>
          </CardContent>
        </Card>

        <div className='grid gap-5 xl:grid-cols-2'>
          <CourseTable
            title={tOperationsUsers('detail.learningCourses')}
            courses={detail.learning_courses || []}
            emptyText={tOperationsUsers('detail.emptyCourses')}
            courseNameLabel={tOperationsUsers(
              'courseSummary.dialog.courseName',
            )}
            courseIdLabel={tOperationsUsers('courseSummary.dialog.courseId')}
            valueLabel={tOperationsUsers('detail.learningProgress')}
            renderValue={formatLearningProgress}
            courseNameAlign='left'
          />
          <CourseTable
            title={tOperationsUsers('detail.createdCourses')}
            courses={detail.created_courses || []}
            emptyText={tOperationsUsers('detail.emptyCourses')}
            courseNameLabel={tOperationsUsers(
              'courseSummary.dialog.courseName',
            )}
            courseIdLabel={tOperationsUsers('courseSummary.dialog.courseId')}
            valueLabel={tOperationsUsers('courseSummary.dialog.status')}
            renderValue={course =>
              resolveCourseStatusLabel(course.course_status)
            }
            courseNameAlign='left'
          />
        </div>
      </div>
    </div>
  );
}
