'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { useParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import Loading from '@/components/loading';
import { Card, CardContent } from '@/components/ui/Card';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/Breadcrumb';
import {
  Table,
  TableBody,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { useUserStore } from '@/store';

export default function AdminDashboardCourseDetailPage() {
  const { t } = useTranslation();
  const params = useParams<{ shifu_bid?: string }>();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const emptyValue = '--';
  const placeholderValue = t('module.dashboard.detail.placeholderValue');
  const metricLabels = [
    t('module.dashboard.detail.metrics.totalLearners'),
    t('module.dashboard.detail.metrics.totalQuestions'),
    t('module.dashboard.detail.metrics.activeLearnersLast7Days'),
    t('module.dashboard.detail.metrics.avgQuestionsPerLearner'),
    t('module.dashboard.detail.metrics.completedLearners'),
    t('module.dashboard.detail.metrics.completionRate'),
  ];
  const chartLabels = [
    t('module.dashboard.detail.charts.questionsByChapter'),
    t('module.dashboard.detail.charts.questionsByTime'),
    t('module.dashboard.detail.charts.learningTrend'),
    t('module.dashboard.detail.charts.chapterProgress'),
  ];
  const learnerTableColumnLabels = [
    t('module.dashboard.detail.learners.columns.name'),
    t('module.dashboard.detail.learners.columns.progress'),
    t('module.dashboard.detail.learners.columns.questions'),
    t('module.dashboard.detail.learners.columns.lastActiveAt'),
  ];

  useEffect(() => {
    if (!isInitialized || !isGuest) {
      return;
    }

    const currentPath = encodeURIComponent(
      window.location.pathname + window.location.search,
    );
    window.location.href = `/login?redirect=${currentPath}`;
  }, [isGuest, isInitialized]);

  if (!isInitialized || isGuest) {
    return (
      <div className='flex h-full items-center justify-center'>
        <Loading />
      </div>
    );
  }

  return (
    <div className='h-full overflow-auto pr-1'>
      <div className='space-y-5 pb-6'>
        <div className='space-y-3'>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link href='/admin/dashboard'>
                    {t('module.dashboard.title')}
                  </Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>
                  {t('module.dashboard.detail.title')}
                </BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>

          <div className='space-y-1'>
            <h1 className='text-2xl font-semibold text-gray-900'>
              {t('module.dashboard.detail.title')}
            </h1>
            <div className='text-sm text-muted-foreground'>
              <span>{t('module.dashboard.detail.courseIdLabel')}</span>
              <span className='ml-1 font-medium text-foreground'>
                {shifuBid || emptyValue}
              </span>
            </div>
            <p className='text-sm text-muted-foreground'>
              {t('module.dashboard.detail.subtitle')}
            </p>
          </div>
        </div>

        <Card>
          <CardContent className='p-5'>
            <div className='mb-4'>
              <h2 className='text-base font-semibold text-foreground'>
                {t('module.dashboard.detail.basicInfo.title')}
              </h2>
            </div>
            <dl className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
              <div className='space-y-1'>
                <dt className='text-sm text-muted-foreground'>
                  {t('module.dashboard.detail.basicInfo.courseName')}
                </dt>
                <dd className='text-sm font-medium text-foreground'>
                  {placeholderValue}
                </dd>
              </div>
              <div className='space-y-1'>
                <dt className='text-sm text-muted-foreground'>
                  {t('module.dashboard.detail.basicInfo.createdAt')}
                </dt>
                <dd className='text-sm font-medium text-foreground'>
                  {placeholderValue}
                </dd>
              </div>
              <div className='space-y-1'>
                <dt className='text-sm text-muted-foreground'>
                  {t('module.dashboard.detail.basicInfo.chapterCount')}
                </dt>
                <dd className='text-sm font-medium text-foreground'>
                  {placeholderValue}
                </dd>
              </div>
              <div className='space-y-1'>
                <dt className='text-sm text-muted-foreground'>
                  {t('module.dashboard.detail.basicInfo.learnerCount')}
                </dt>
                <dd className='text-sm font-medium text-foreground'>
                  {placeholderValue}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <div className='space-y-3'>
          <h2 className='text-base font-semibold text-foreground'>
            {t('module.dashboard.detail.metrics.title')}
          </h2>
          <div className='grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3'>
            {metricLabels.map(metricLabel => (
              <Card key={metricLabel}>
                <CardContent className='p-4'>
                  <div className='text-sm text-muted-foreground'>
                    {metricLabel}
                  </div>
                  <div className='mt-3 text-sm font-medium text-muted-foreground'>
                    {placeholderValue}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        <div className='space-y-3'>
          <h2 className='text-base font-semibold text-foreground'>
            {t('module.dashboard.detail.charts.title')}
          </h2>
          <div className='grid grid-cols-1 gap-4 xl:grid-cols-2'>
            {chartLabels.map(chartLabel => (
              <Card key={chartLabel}>
                <CardContent className='flex h-56 flex-col p-5'>
                  <div className='text-sm font-medium text-foreground'>
                    {chartLabel}
                  </div>
                  <div className='mt-4 flex flex-1 items-center justify-center rounded-lg border border-dashed border-border bg-muted/30 text-sm text-muted-foreground'>
                    {t('module.dashboard.detail.charts.placeholder')}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        <Card>
          <CardContent className='p-0'>
            <div className='border-b border-border px-5 py-4'>
              <h2 className='text-base font-semibold text-foreground'>
                {t('module.dashboard.detail.learners.title')}
              </h2>
            </div>
            <div className='p-5 pt-0'>
              <Table className='min-w-[720px]'>
                <TableHeader>
                  <TableRow>
                    {learnerTableColumnLabels.map(columnLabel => (
                      <TableHead key={columnLabel}>{columnLabel}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableEmpty colSpan={learnerTableColumnLabels.length}>
                    {t('module.dashboard.detail.learners.empty')}
                  </TableEmpty>
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
