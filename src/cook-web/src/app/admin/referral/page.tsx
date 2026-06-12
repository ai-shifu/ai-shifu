'use client';

import React from 'react';
import { Check, Copy, RefreshCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { AdminMetricCardGroup } from '@/app/admin/components/AdminMetricCard';
import AdminTitle from '@/app/admin/components/AdminTitle';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { copyText } from '@/c-utils/textutils';
import { formatBillingCredits } from '@/lib/billing';
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
 * t('module.referral.creator.queueColumns.credits')
 * t('module.referral.creator.queueColumns.effectiveAt')
 * t('module.referral.creator.queueColumns.expiresAt')
 * t('module.referral.creator.queueColumns.index')
 * t('module.referral.creator.queueColumns.invitee')
 * t('module.referral.creator.queueColumns.ledgerState')
 * t('module.referral.creator.queueColumns.status')
 * t('module.referral.creator.queueTitle')
 * t('module.referral.creator.ledgerStates.available')
 * t('module.referral.creator.ledgerStates.reserved')
 * t('module.referral.creator.ledgerStates.unknown')
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

const formatCreditAmount = (
  value: string | number | null | undefined,
  locale: string,
) => {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  const numericValue = Number(value);
  return Number.isFinite(numericValue)
    ? formatBillingCredits(numericValue, locale)
    : '-';
};

const formatQueueIndex = (value: number) => `#${value}`;

const ledgerStateKey = (state: string | null | undefined) => {
  if (state === 'available' || state === 'reserved') {
    return state;
  }
  return 'unknown';
};

export default function AdminReferralPage() {
  const { t, i18n } = useTranslation('module.referral');
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

  const rewardQueue = profile?.reward_queue || [];
  const locale = i18n.language || 'en-US';

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
                  credits: formatCreditAmount(
                    profile.reward_credit_amount,
                    locale,
                  ),
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
            <Table
              className='mt-3 min-w-[760px] table-auto'
              containerClassName='mt-3 rounded-md border border-border/70'
            >
              <TableHeader>
                <TableRow>
                  <TableHead>{t('creator.queueColumns.index')}</TableHead>
                  <TableHead>{t('creator.queueColumns.status')}</TableHead>
                  <TableHead>{t('creator.queueColumns.credits')}</TableHead>
                  <TableHead>{t('creator.queueColumns.invitee')}</TableHead>
                  <TableHead>{t('creator.queueColumns.effectiveAt')}</TableHead>
                  <TableHead>{t('creator.queueColumns.expiresAt')}</TableHead>
                  <TableHead>{t('creator.queueColumns.ledgerState')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rewardQueue.length ? (
                  rewardQueue.map(item => (
                    <TableRow key={item.reward_bid || item.queue_index}>
                      <TableCell className='whitespace-nowrap font-medium'>
                        {formatQueueIndex(item.queue_index)}
                      </TableCell>
                      <TableCell className='whitespace-nowrap'>
                        {t(
                          `rewardStatus.${
                            REWARD_STATUS_KEY_BY_VALUE[item.reward_status] ||
                            'unknown'
                          }`,
                        )}
                      </TableCell>
                      <TableCell className='whitespace-nowrap tabular-nums'>
                        {formatCreditAmount(item.reward_credit_amount, locale)}
                      </TableCell>
                      <TableCell className='whitespace-nowrap'>
                        {item.invitee_mobile_snapshot || '-'}
                      </TableCell>
                      <TableCell className='whitespace-nowrap'>
                        {item.effective_at || '-'}
                      </TableCell>
                      <TableCell className='whitespace-nowrap'>
                        {item.expires_at || '-'}
                      </TableCell>
                      <TableCell className='whitespace-nowrap'>
                        {t(
                          `creator.ledgerStates.${ledgerStateKey(
                            item.ledger_credit_state,
                          )}`,
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableEmpty colSpan={7}>{t('creator.emptyQueue')}</TableEmpty>
                )}
              </TableBody>
            </Table>
          </section>
        </div>
      ) : null}
    </div>
  );
}
