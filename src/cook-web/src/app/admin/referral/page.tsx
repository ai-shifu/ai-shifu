'use client';

import React from 'react';
import { Check, Copy, RefreshCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import { AdminMetricCardGroup } from '@/app/admin/components/AdminMetricCard';
import AdminTitle from '@/app/admin/components/AdminTitle';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { copyText } from '@/c-utils/textutils';
import { ErrorWithCode } from '@/lib/request';
import {
  REFERRAL_REWARD_STATUS,
  type ReferralInviteProfile,
} from '@/types/referral';

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.referral.creator.capAvailableHint')
 * t('module.referral.creator.capReached')
 * t('module.referral.creator.capReachedHint')
 * t('module.referral.creator.copied')
 * t('module.referral.creator.copyLink')
 * t('module.referral.creator.description')
 * t('module.referral.creator.emptyQueue')
 * t('module.referral.creator.inviteCardDescription')
 * t('module.referral.creator.inviteCardTitle')
 * t('module.referral.creator.inviteCode')
 * t('module.referral.creator.inviteLink')
 * t('module.referral.creator.metrics.cap')
 * t('module.referral.creator.metrics.remaining')
 * t('module.referral.creator.metrics.rewarded')
 * t('module.referral.creator.queueTitle')
 * t('module.referral.creator.refresh')
 * t('module.referral.creator.rewardRule')
 * t('module.referral.creator.rewardRulesTitle')
 * t('module.referral.creator.title')
 * t('module.referral.creator.tooltips.cap')
 * t('module.referral.creator.tooltips.remaining')
 * t('module.referral.creator.tooltips.rewarded')
 * t('module.referral.rewardStatus.active')
 * t('module.referral.rewardStatus.canceled')
 * t('module.referral.rewardStatus.expired')
 * t('module.referral.rewardStatus.frozen')
 * t('module.referral.rewardStatus.generated')
 * t('module.referral.rewardStatus.pendingEffective')
 * t('module.referral.rewardStatus.skippedCap')
 * t('module.referral.rewardStatus.unknown')
 */

const REWARD_STATUS_KEY_BY_VALUE: Record<number, string> = {
  [REFERRAL_REWARD_STATUS.generated]: 'generated',
  [REFERRAL_REWARD_STATUS.pendingEffective]: 'pendingEffective',
  [REFERRAL_REWARD_STATUS.active]: 'active',
  [REFERRAL_REWARD_STATUS.expired]: 'expired',
  [REFERRAL_REWARD_STATUS.frozen]: 'frozen',
  [REFERRAL_REWARD_STATUS.canceled]: 'canceled',
  [REFERRAL_REWARD_STATUS.skippedCap]: 'skippedCap',
};

const formatCount = (value: number | null | undefined) =>
  typeof value === 'number' && Number.isFinite(value) ? value : '-';

export default function AdminReferralPage() {
  const { t } = useTranslation('module.referral');
  const [profile, setProfile] = React.useState<ReferralInviteProfile | null>(
    null,
  );
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<ErrorWithCode | null>(null);
  const [copied, setCopied] = React.useState(false);

  const loadProfile = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = (await api.getReferralInviteProfile(
        {},
      )) as ReferralInviteProfile;
      setProfile(response);
    } catch (nextError) {
      setError(nextError as ErrorWithCode);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const copyInviteLink = async () => {
    if (!profile?.invite_url) {
      return;
    }
    await copyText(profile.invite_url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const capReached =
    profile?.reward_cap_count !== null &&
    profile?.reward_cap_count !== undefined &&
    Number(profile.reward_remaining_count || 0) <= 0;

  const queueEntries = Object.entries(profile?.reward_queue_summary || {})
    .map(([status, count]) => ({
      status: Number(status),
      count,
    }))
    .filter(item => item.count > 0);

  if (loading) {
    return <Loading />;
  }

  if (error) {
    return (
      <ErrorDisplay
        errorCode={error.code || error.status || 500}
        errorMessage={error.message}
        onRetry={loadProfile}
      />
    );
  }

  return (
    <div className='flex min-h-0 flex-col'>
      <AdminBreadcrumb items={[{ label: t('creator.title') }]} />
      <AdminTitle
        title={t('creator.title')}
        description={t('creator.description')}
        actions={
          <Button
            type='button'
            variant='outline'
            className='gap-2'
            onClick={loadProfile}
          >
            <RefreshCcw className='h-4 w-4' />
            {t('creator.refresh')}
          </Button>
        }
      />

      {profile ? (
        <div className='min-h-0 space-y-5'>
          <AdminMetricCardGroup
            gridClassName='md:grid-cols-3'
            items={[
              {
                key: 'rewarded',
                label: t('creator.metrics.rewarded'),
                value: formatCount(profile.reward_granted_count),
                tooltip: t('creator.tooltips.rewarded'),
              },
              {
                key: 'remaining',
                label: t('creator.metrics.remaining'),
                value: formatCount(profile.reward_remaining_count),
                tooltip: t('creator.tooltips.remaining'),
              },
              {
                key: 'cap',
                label: t('creator.metrics.cap'),
                value: formatCount(profile.reward_cap_count),
                tooltip: t('creator.tooltips.cap'),
              },
            ]}
          />

          <section className='rounded-lg border border-border bg-white p-4'>
            <div className='mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between'>
              <div>
                <h2 className='text-base font-semibold text-foreground'>
                  {t('creator.inviteCardTitle')}
                </h2>
                <p className='mt-1 text-sm text-muted-foreground'>
                  {t('creator.inviteCardDescription')}
                </p>
              </div>
              {capReached ? (
                <Badge
                  variant='outline'
                  className='w-fit border-amber-300 bg-amber-50 text-amber-700'
                >
                  {t('creator.capReached')}
                </Badge>
              ) : null}
            </div>

            <div className='grid gap-4 lg:grid-cols-[1fr_160px]'>
              <div className='space-y-2'>
                <label
                  htmlFor='referral-invite-url'
                  className='text-sm font-medium text-foreground'
                >
                  {t('creator.inviteLink')}
                </label>
                <Input
                  id='referral-invite-url'
                  readOnly
                  value={profile.invite_url}
                />
              </div>
              <div className='space-y-2'>
                <div className='text-sm font-medium text-foreground'>
                  {t('creator.inviteCode')}
                </div>
                <div className='flex h-10 items-center rounded-md border border-border bg-muted/30 px-3 font-mono text-sm font-semibold tracking-wide'>
                  {profile.invite_code}
                </div>
              </div>
            </div>

            <div className='mt-4 flex flex-wrap gap-3'>
              <Button
                type='button'
                className='gap-2'
                onClick={copyInviteLink}
              >
                {copied ? (
                  <Check className='h-4 w-4' />
                ) : (
                  <Copy className='h-4 w-4' />
                )}
                {copied ? t('creator.copied') : t('creator.copyLink')}
              </Button>
            </div>
          </section>

          <section className='rounded-lg border border-border bg-white p-4'>
            <h2 className='text-base font-semibold text-foreground'>
              {t('creator.rewardRulesTitle')}
            </h2>
            <div className='mt-3 grid gap-3 md:grid-cols-2'>
              <div className='rounded-md border border-border/70 bg-muted/20 p-3 text-sm leading-6'>
                {t('creator.rewardRule', {
                  cycles: profile.reward_cycle_count,
                  credits: profile.reward_credit_amount || '-',
                  days: profile.reward_credit_validity_days || '-',
                })}
              </div>
              <div className='rounded-md border border-border/70 bg-muted/20 p-3 text-sm leading-6'>
                {capReached
                  ? t('creator.capReachedHint')
                  : t('creator.capAvailableHint', {
                      remaining: formatCount(profile.reward_remaining_count),
                    })}
              </div>
            </div>
          </section>

          <section className='rounded-lg border border-border bg-white p-4'>
            <h2 className='text-base font-semibold text-foreground'>
              {t('creator.queueTitle')}
            </h2>
            {queueEntries.length ? (
              <div className='mt-3 grid gap-2 md:grid-cols-2'>
                {queueEntries.map(item => (
                  <div
                    key={item.status}
                    className='flex items-center justify-between rounded-md border border-border/70 px-3 py-2 text-sm'
                  >
                    <span>
                      {t(
                        `rewardStatus.${
                          REWARD_STATUS_KEY_BY_VALUE[item.status] || 'unknown'
                        }`,
                      )}
                    </span>
                    <span className='font-semibold'>{item.count}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className='mt-3 text-sm text-muted-foreground'>
                {t('creator.emptyQueue')}
              </p>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
