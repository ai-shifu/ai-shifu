'use client';

import React from 'react';
import { RefreshCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import { AdminMetricCardGroup } from '@/app/admin/components/AdminMetricCard';
import AdminTitle from '@/app/admin/components/AdminTitle';
import useOperatorGuard from '@/app/admin/operations/useOperatorGuard';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import type { AdminReferralOverview } from '@/types/referral';
import ReferralRelationsPanel from './ReferralRelationsPanel';

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.referral.operator.description')
 * t('module.referral.operator.metrics.abnormalRelations')
 * t('module.referral.operator.metrics.generatedRewards')
 * t('module.referral.operator.metrics.totalRelations')
 * t('module.referral.operator.refresh')
 * t('module.referral.operator.title')
 * t('module.referral.operator.tooltips.abnormalRelations')
 * t('module.referral.operator.tooltips.generatedRewards')
 * t('module.referral.operator.tooltips.totalRelations')
 */

const normalizeCount = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) ? value : 0;

export default function AdminOperationReferralsPage() {
  const { t } = useTranslation('module.referral');
  const { isReady } = useOperatorGuard();
  const [overview, setOverview] = React.useState<AdminReferralOverview>({
    total_relations: 0,
    abnormal_relations: 0,
    generated_rewards: 0,
  });
  const [refreshToken, setRefreshToken] = React.useState(0);

  const fetchOverview = React.useCallback(async () => {
    const response = (await api.getAdminOperationReferralsOverview(
      {},
    )) as AdminReferralOverview;
    setOverview({
      total_relations: normalizeCount(response.total_relations),
      abnormal_relations: normalizeCount(response.abnormal_relations),
      generated_rewards: normalizeCount(response.generated_rewards),
    });
  }, []);

  React.useEffect(() => {
    if (!isReady) {
      return;
    }
    void fetchOverview();
  }, [fetchOverview, isReady, refreshToken]);

  if (!isReady) {
    return <Loading />;
  }

  return (
    <div className='flex min-h-0 flex-col pb-6'>
      <AdminBreadcrumb items={[{ label: t('operator.title') }]} />
      <AdminTitle
        title={t('operator.title')}
        description={t('operator.description')}
        actions={
          <Button
            type='button'
            variant='outline'
            className='gap-2'
            onClick={() => {
              void fetchOverview();
              setRefreshToken(current => current + 1);
            }}
          >
            <RefreshCcw className='h-4 w-4' />
            {t('operator.refresh')}
          </Button>
        }
      />

      <AdminMetricCardGroup
        gridClassName='md:grid-cols-3'
        items={[
          {
            key: 'total-relations',
            label: t('operator.metrics.totalRelations'),
            value: overview.total_relations,
            tooltip: t('operator.tooltips.totalRelations'),
          },
          {
            key: 'generated-rewards',
            label: t('operator.metrics.generatedRewards'),
            value: overview.generated_rewards,
            tooltip: t('operator.tooltips.generatedRewards'),
          },
          {
            key: 'abnormal-relations',
            label: t('operator.metrics.abnormalRelations'),
            value: overview.abnormal_relations,
            tooltip: t('operator.tooltips.abnormalRelations'),
          },
        ]}
      />

      <ReferralRelationsPanel
        refreshToken={refreshToken}
        className='mt-5 space-y-5'
      />
    </div>
  );
}
