'use client';

import type { ReactNode, RefObject } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import type {
  AdminOperationUserCourseItem,
  AdminOperationUserCreditFilters,
  AdminOperationUserCreditsResponse,
} from '../../operation-user-types';
import UserCoursesTab from './UserCoursesTab';
import UserCreditLedgerTab from './UserCreditLedgerTab';
import UserDetailInfoCard from './UserDetailInfoCard';

type DetailTab = 'credits' | 'learning' | 'created';

type UserDetailTabsSectionProps = {
  sectionRef: RefObject<HTMLDivElement | null>;
  activeTab: DetailTab;
  emptyValue: string;
  creditsOverviewTitle: string;
  creditsOverviewItems: Array<{
    key: string;
    label: ReactNode;
    value?: string;
    onClick?: () => void;
    valueClassName?: string;
    valueAriaLabel?: string;
  }>;
  creditsTabLabel: string;
  learningTabLabel: string;
  createdTabLabel: string;
  onTabChange: (tab: DetailTab) => void;
  creditLedgerProps: {
    filtersDraft: AdminOperationUserCreditFilters;
    loading: boolean;
    error: { message: string; code?: number } | null;
    items: AdminOperationUserCreditsResponse['items'];
    pageIndex: number;
    pageCount: number;
    onFiltersChange: (filters: AdminOperationUserCreditFilters) => void;
    onSearch: () => void;
    onReset: () => void;
    onPageChange: (page: number) => void;
    onRetry: () => void;
  };
  learningCoursesProps: {
    title: string;
    courses: AdminOperationUserCourseItem[];
    emptyText: string;
    courseNameLabel: string;
    courseIdLabel: string;
    valueLabel: string;
    renderValue: (course: AdminOperationUserCourseItem) => string;
  };
  createdCoursesProps: {
    title: string;
    courses: AdminOperationUserCourseItem[];
    emptyText: string;
    courseNameLabel: string;
    courseIdLabel: string;
    valueLabel: string;
    renderValue: (course: AdminOperationUserCourseItem) => string;
  };
};

const isDetailTab = (value: string): value is DetailTab =>
  value === 'credits' || value === 'learning' || value === 'created';

export default function UserDetailTabsSection({
  sectionRef,
  activeTab,
  emptyValue,
  creditsOverviewTitle,
  creditsOverviewItems,
  creditsTabLabel,
  learningTabLabel,
  createdTabLabel,
  onTabChange,
  creditLedgerProps,
  learningCoursesProps,
  createdCoursesProps,
}: UserDetailTabsSectionProps) {
  return (
    <div
      id='credits'
      ref={sectionRef}
      className='space-y-5'
    >
      <UserDetailInfoCard
        title={creditsOverviewTitle}
        items={creditsOverviewItems}
        emptyValue={emptyValue}
      />

      <Tabs
        className='space-y-4'
        value={activeTab}
        onValueChange={value => {
          if (!isDetailTab(value)) {
            return;
          }
          onTabChange(value);
        }}
      >
        <TabsList>
          <TabsTrigger value='credits'>{creditsTabLabel}</TabsTrigger>
          <TabsTrigger value='learning'>{learningTabLabel}</TabsTrigger>
          <TabsTrigger value='created'>{createdTabLabel}</TabsTrigger>
        </TabsList>

        <TabsContent
          value='credits'
          className='mt-0'
        >
          <UserCreditLedgerTab
            filtersDraft={creditLedgerProps.filtersDraft}
            loading={creditLedgerProps.loading}
            error={creditLedgerProps.error}
            items={creditLedgerProps.items}
            pageIndex={creditLedgerProps.pageIndex}
            pageCount={creditLedgerProps.pageCount}
            emptyValue={emptyValue}
            onFiltersChange={creditLedgerProps.onFiltersChange}
            onSearch={creditLedgerProps.onSearch}
            onReset={creditLedgerProps.onReset}
            onPageChange={creditLedgerProps.onPageChange}
            onRetry={creditLedgerProps.onRetry}
          />
        </TabsContent>

        <TabsContent
          value='learning'
          className='mt-0'
        >
          <UserCoursesTab
            title={learningCoursesProps.title}
            courses={learningCoursesProps.courses}
            emptyText={learningCoursesProps.emptyText}
            courseNameLabel={learningCoursesProps.courseNameLabel}
            courseIdLabel={learningCoursesProps.courseIdLabel}
            valueLabel={learningCoursesProps.valueLabel}
            emptyValue={emptyValue}
            renderValue={learningCoursesProps.renderValue}
            courseNameAlign='left'
          />
        </TabsContent>

        <TabsContent
          value='created'
          className='mt-0'
        >
          <UserCoursesTab
            title={createdCoursesProps.title}
            courses={createdCoursesProps.courses}
            emptyText={createdCoursesProps.emptyText}
            courseNameLabel={createdCoursesProps.courseNameLabel}
            courseIdLabel={createdCoursesProps.courseIdLabel}
            valueLabel={createdCoursesProps.valueLabel}
            emptyValue={emptyValue}
            renderValue={createdCoursesProps.renderValue}
            courseNameAlign='left'
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
