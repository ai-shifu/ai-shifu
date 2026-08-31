import { useCallback, useMemo } from 'react';
import { CircleHelp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { formatAdminCredits } from '@/app/admin/lib/numberFormat';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { formatOperatorUtcDateTime } from '../dateTime';
import type {
  AdminOperationUserCourseItem,
  AdminOperationUserCreditSummary,
  AdminOperationUserCreditsResponse,
  AdminOperationUserDetailResponse,
} from '../../operation-user-types';
import { DEFAULT_CREDIT_SUMMARY, EMPTY_VALUE } from './userDetailConstants';

const resolveCourseCount = (
  count: number,
  courses?: AdminOperationUserCourseItem[],
) => (count > 0 ? count : (courses || []).length);

const formatCreditBalanceValue = (value: string, locale: string) => {
  if (!value) {
    return '';
  }
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return '';
  }
  return formatAdminCredits(numericValue, locale);
};

export const formatLearningProgress = (
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

type UseUserDetailViewModelOptions = {
  detail: AdminOperationUserDetailResponse;
  credits: AdminOperationUserCreditsResponse;
  userBid: string;
  onLearningCoursesClick: () => void;
  onCreatedCoursesClick: () => void;
};

export default function useUserDetailViewModel({
  detail,
  credits,
  userBid,
  onLearningCoursesClick,
  onCreatedCoursesClick,
}: UseUserDetailViewModelOptions) {
  const { t, i18n } = useTranslation();
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');
  const { t: tOperationsCourse } = useTranslation('module.operationsCourse');
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
  const creditOwnerLabel = useMemo(() => {
    const mobile = detail.mobile || '';
    const displayName = detail.nickname || contactValue || userBid || '';
    if (mobile && displayName && displayName !== mobile) {
      return `${mobile} / ${displayName}`;
    }
    return mobile || displayName || EMPTY_VALUE;
  }, [contactValue, detail.mobile, detail.nickname, userBid]);
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
        credits.summary === DEFAULT_CREDIT_SUMMARY
          ? detail.has_active_subscription
          : credits.summary.has_active_subscription,
    }),
    [
      credits.summary,
      detail.available_credits,
      detail.credits_expire_at,
      detail.has_active_subscription,
      detail.subscription_credits,
      detail.topup_credits,
    ],
  );

  const resolveRoleLabel = useCallback(
    (role: string) => tOperationsUsers(`roleLabels.${role || 'unknown'}`),
    [tOperationsUsers],
  );
  const resolveRegistrationSourceLabel = useCallback(
    (source: string) =>
      tOperationsUsers(`registrationSourceLabels.${source || 'unknown'}`),
    [tOperationsUsers],
  );
  const resolveCourseStatusLabel = useCallback(
    (status: string) => {
      if (status === 'published') {
        return tOperationsCourse('statusLabels.published');
      }
      if (status === 'unpublished') {
        return tOperationsCourse('statusLabels.unpublished');
      }
      const unknownLabel = tOperationsCourse('statusLabels.unknown');
      return status ? `${unknownLabel} (${status})` : unknownLabel;
    },
    [tOperationsCourse],
  );
  const resolveCreditsExpireAt = useCallback(() => {
    if (creditSummary.credits_expire_at) {
      return formatOperatorUtcDateTime(creditSummary.credits_expire_at);
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
        value: formatOperatorUtcDateTime(detail.last_login_at),
      },
      {
        key: 'createdAt',
        label: tOperationsUsers('table.createdAt'),
        value: formatOperatorUtcDateTime(detail.created_at),
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
        onClick: onLearningCoursesClick,
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
        onClick: onCreatedCoursesClick,
      },
      {
        key: 'lastLearningAt',
        label: tOperationsUsers('table.lastLearningAt'),
        value: formatOperatorUtcDateTime(detail.last_learning_at),
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
      onCreatedCoursesClick,
      onLearningCoursesClick,
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
        value: formatCreditBalanceValue(
          creditSummary.available_credits,
          i18n.language,
        ),
      },
      {
        key: 'subscriptionCredits',
        label: tOperationsUsers(
          'detail.creditsOverviewLabels.subscriptionCredits',
        ),
        value: formatCreditBalanceValue(
          creditSummary.subscription_credits,
          i18n.language,
        ),
      },
      {
        key: 'topupCredits',
        label: tOperationsUsers('detail.creditsOverviewLabels.topupCredits'),
        value: formatCreditBalanceValue(
          creditSummary.topup_credits,
          i18n.language,
        ),
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

  return {
    basicInfoItems,
    overviewItems,
    creditsOverviewItems,
    creditOwnerLabel,
    resolveCourseStatusLabel,
  };
}
