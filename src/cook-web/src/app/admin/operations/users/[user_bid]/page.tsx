'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminTitle from '@/app/admin/components/AdminTitle';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { TooltipProvider } from '@/components/ui/tooltip';
import AdminOperationsBreadcrumb from '../../AdminOperationsBreadcrumb';
import type { AdminOperationUserCreditUsageDetailResponse } from '../../operation-user-types';
import useOperatorGuard from '../../useOperatorGuard';
import UserDetailSummarySection from './UserDetailSummarySection';
import UserDetailTabsSection from './UserDetailTabsSection';
import useUserCreditLedgerData from './useUserCreditLedgerData';
import useUserDetailData from './useUserDetailData';
import useUserDetailViewModel, {
  formatLearningProgress,
} from './useUserDetailViewModel';
import {
  DETAIL_TAB_HASHES,
  EMPTY_VALUE,
  resolveDetailTabFromHash,
  type DetailTab,
} from './userDetailConstants';

type UserBidParams = {
  user_bid: string;
};

/**
 * t('module.operationsUser.detail.title')
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
 * t('module.operationsUser.detail.creditLedgerFilters.usageScene')
 * t('module.operationsUser.detail.creditLedgerFilters.usageSceneOptions.all')
 * t('module.operationsUser.detail.creditLedgerFilters.usageSceneOptions.learning')
 * t('module.operationsUser.detail.creditLedgerFilters.usageSceneOptions.preview')
 * t('module.operationsUser.detail.creditLedgerFilters.usageSceneOptions.debug')
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

export default function AdminOperationUserDetailPage() {
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');
  const router = useRouter();
  const params = useParams<UserBidParams>();
  const { isReady } = useOperatorGuard();
  const detailTabsSectionRef = useRef<HTMLDivElement | null>(null);
  const hasInitializedDetailTabRef = useRef(false);
  const [activeTab, setActiveTab] = useState<DetailTab>('credits');
  const {
    detail,
    detailLoading,
    detailError,
    retryDetail,
    userBid,
    userBidErrorMessage,
  } = useUserDetailData({
    isReady,
    rawUserBid: params?.user_bid,
  });
  const {
    credits,
    creditsLoading,
    creditsError,
    creditsPageIndex,
    creditFilters,
    creditFiltersDraft,
    setCreditFiltersDraft,
    setCreditsPageIndex,
    handleCreditSearch,
    handleCreditTypeChange,
    handleCreditReset,
    retryCredits,
  } = useUserCreditLedgerData({
    isReady,
    userBid,
    userBidErrorMessage,
  });

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
  const handleLearningCoursesClick = useCallback(() => {
    setDetailTab('learning', { scrollToSection: true });
  }, [setDetailTab]);
  const handleCreatedCoursesClick = useCallback(() => {
    setDetailTab('created', { scrollToSection: true });
  }, [setDetailTab]);
  const {
    basicInfoItems,
    overviewItems,
    creditsOverviewItems,
    creditOwnerLabel,
    resolveCourseStatusLabel,
  } = useUserDetailViewModel({
    detail,
    credits,
    userBid,
    onLearningCoursesClick: handleLearningCoursesClick,
    onCreatedCoursesClick: handleCreatedCoursesClick,
  });

  const handleCreditCourseOpen = useCallback(
    (courseBid: string) => {
      const normalizedCourseBid = courseBid.trim();
      if (!normalizedCourseBid) {
        return;
      }
      router.push(
        `/admin/operations/${encodeURIComponent(
          normalizedCourseBid,
        )}?tab=creditUsage`,
      );
    },
    [router],
  );

  useEffect(() => {
    if (!hasInitializedDetailTabRef.current) {
      hasInitializedDetailTabRef.current = true;
      return;
    }
    setActiveTab('credits');
    syncDetailTabHash('credits');
  }, [syncDetailTabHash, userBid]);

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

  if (!isReady || detailLoading) {
    return <Loading />;
  }

  if (detailError) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={detailError.code || 0}
          errorMessage={detailError.message}
          onRetry={retryDetail}
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
          <div className='mb-5 shrink-0 space-y-3 px-1 pt-6'>
            <AdminOperationsBreadcrumb
              items={[
                {
                  label: tOperationsUsers('title'),
                  href: '/admin/operations/users',
                },
                { label: tOperationsUsers('detail.title') },
              ]}
            />
            <AdminTitle title={tOperationsUsers('detail.title')} />
          </div>

          <div
            className='min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain bg-stone-50 pr-1'
            data-testid='admin-operation-user-detail-scroll'
          >
            <div className='flex min-h-0 flex-1 flex-col gap-5 px-1 pb-6'>
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
                  activeCreditType: creditFilters.creditType,
                  loading: creditsLoading,
                  error: creditsError,
                  items: credits.items,
                  pageIndex: credits.page || creditsPageIndex,
                  pageCount: credits.page_count || 0,
                  userLabel: creditOwnerLabel,
                  onFiltersChange: setCreditFiltersDraft,
                  onTypeChange: handleCreditTypeChange,
                  onSearch: handleCreditSearch,
                  onReset: handleCreditReset,
                  onPageChange: setCreditsPageIndex,
                  onRetry: retryCredits,
                  onCourseOpen: handleCreditCourseOpen,
                  onUsageDetailLoad: usageBid =>
                    api.getAdminOperationUserCreditUsageDetail({
                      user_bid: userBid,
                      usage_bid: usageBid,
                    }) as Promise<AdminOperationUserCreditUsageDetailResponse>,
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
