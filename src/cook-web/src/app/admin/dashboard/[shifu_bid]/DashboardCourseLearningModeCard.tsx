'use client';

import { useTranslation } from 'react-i18next';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { Card, CardContent } from '@/components/ui/Card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import type { DashboardCourseLearningModeMetric } from '@/types/dashboard';

type DashboardCourseLearningModeCardProps = {
  rows: DashboardCourseLearningModeMetric[];
  emptyValue: string;
};

const formatCount = (value: number, emptyValue: string): string => {
  if (!Number.isFinite(value)) {
    return emptyValue;
  }
  return value.toLocaleString();
};

const formatMetricText = (value: string, emptyValue: string): string => {
  const normalized = String(value || '').trim();
  return normalized || emptyValue;
};

const resolveLearningModeMetricLabelKey = (mode: string) => {
  if (mode === 'listen') {
    return 'module.dashboard.detail.learningModePerformance.modes.listen';
  }
  if (mode === 'classroom') {
    return 'module.dashboard.detail.learningModePerformance.modes.classroom';
  }
  return 'module.dashboard.detail.learningModePerformance.modes.read';
};

export default function DashboardCourseLearningModeCard({
  rows,
  emptyValue,
}: DashboardCourseLearningModeCardProps) {
  const { t } = useTranslation();

  return (
    <Card className='overflow-hidden border-border/80 shadow-sm ring-1 ring-border/40'>
      <CardContent className='space-y-4 px-5 py-5'>
        <div className='space-y-1'>
          <h2 className='text-base font-semibold text-foreground'>
            {t('module.dashboard.detail.learningModePerformance.title')}
          </h2>
          <p className='text-xs text-muted-foreground'>
            {t('module.dashboard.detail.learningModePerformance.scopeHint')}
          </p>
        </div>

        <AdminTableShell
          loading={false}
          isEmpty={rows.length === 0}
          emptyContent={t(
            'module.dashboard.detail.learningModePerformance.empty',
          )}
          emptyColSpan={5}
          tableWrapperClassName='overflow-auto'
          table={emptyRow => (
            <Table className='min-w-[760px] table-auto'>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    {t(
                      'module.dashboard.detail.learningModePerformance.columns.mode',
                    )}
                  </TableHead>
                  <TableHead>
                    {t(
                      'module.dashboard.detail.learningModePerformance.columns.participants',
                    )}
                  </TableHead>
                  <TableHead>
                    {t(
                      'module.dashboard.detail.learningModePerformance.columns.consumedCredits',
                    )}
                  </TableHead>
                  <TableHead>
                    {t(
                      'module.dashboard.detail.learningModePerformance.columns.consumptionSpeed',
                    )}
                  </TableHead>
                  <TableHead>
                    {t(
                      'module.dashboard.detail.learningModePerformance.columns.averageConsumedCredits',
                    )}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {emptyRow}
                {rows.map(row => (
                  <TableRow key={row.mode}>
                    <TableCell className='whitespace-nowrap font-medium text-foreground'>
                      {t(resolveLearningModeMetricLabelKey(row.mode))}
                    </TableCell>
                    <TableCell className='whitespace-nowrap font-medium tabular-nums text-foreground'>
                      {formatCount(row.participant_count, emptyValue)}
                    </TableCell>
                    <TableCell className='whitespace-nowrap font-medium tabular-nums text-foreground'>
                      {formatMetricText(row.consumed_credits, emptyValue)}
                    </TableCell>
                    <TableCell className='whitespace-nowrap text-muted-foreground'>
                      {formatMetricText(row.consumption_speed, emptyValue)}
                    </TableCell>
                    <TableCell className='whitespace-nowrap font-medium tabular-nums text-foreground'>
                      {formatMetricText(
                        row.average_consumed_credits,
                        emptyValue,
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        />
      </CardContent>
    </Card>
  );
}
