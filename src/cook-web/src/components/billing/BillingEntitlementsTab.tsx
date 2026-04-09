import React from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/Badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { useBillingEntitlements } from '@/hooks/useBillingData';
import { registerBillingTranslationUsage } from '@/lib/billing';
import type { BillingEntitlements } from '@/types/billing';

type EntitlementMetricCardProps = {
  title: string;
  value: string;
  description: string;
  accentClassName: string;
};

function EntitlementMetricCard({
  title,
  value,
  description,
  accentClassName,
}: EntitlementMetricCardProps) {
  return (
    <div className='rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-[0_8px_24px_rgba(15,23,42,0.05)]'>
      <p className='text-xs font-medium uppercase tracking-[0.24em] text-slate-400'>
        {title}
      </p>
      <div className='mt-4 flex items-center gap-3'>
        <div
          className={`h-3 w-3 rounded-full ${accentClassName}`}
          aria-hidden='true'
        />
        <p className='text-2xl font-semibold tracking-tight text-slate-900'>
          {value}
        </p>
      </div>
      <p className='mt-3 text-sm leading-6 text-slate-600'>{description}</p>
    </div>
  );
}

function resolvePriorityValue(
  t: (key: string) => string,
  priorityClass: BillingEntitlements['priority_class'],
): string {
  switch (priorityClass) {
    case 'priority':
      return t('module.billing.entitlements.priority.priority');
    case 'vip':
      return t('module.billing.entitlements.priority.vip');
    default:
      return t('module.billing.entitlements.priority.standard');
  }
}

function resolveAnalyticsValue(
  t: (key: string) => string,
  analyticsTier: BillingEntitlements['analytics_tier'],
): string {
  switch (analyticsTier) {
    case 'advanced':
      return t('module.billing.entitlements.analytics.advanced');
    case 'enterprise':
      return t('module.billing.entitlements.analytics.enterprise');
    default:
      return t('module.billing.entitlements.analytics.basic');
  }
}

function resolveSupportValue(
  t: (key: string) => string,
  supportTier: BillingEntitlements['support_tier'],
): string {
  switch (supportTier) {
    case 'business_hours':
      return t('module.billing.entitlements.support.businessHours');
    case 'priority':
      return t('module.billing.entitlements.support.priority');
    default:
      return t('module.billing.entitlements.support.selfServe');
  }
}

export function BillingEntitlementsTab() {
  const { t } = useTranslation();
  registerBillingTranslationUsage(t);
  const { data, error, isLoading } = useBillingEntitlements();

  return (
    <div className='space-y-4'>
      <Card className='border-slate-200 bg-[linear-gradient(135deg,#eff6ff_0%,#ffffff_58%,#f8fafc_100%)] shadow-[0_18px_50px_rgba(15,23,42,0.08)]'>
        <CardHeader className='space-y-3'>
          <div className='flex flex-wrap items-center justify-between gap-3'>
            <div className='space-y-2'>
              <CardTitle className='text-lg text-slate-900'>
                {t('module.billing.entitlements.title')}
              </CardTitle>
              <CardDescription className='leading-6 text-slate-600'>
                {t('module.billing.entitlements.description')}
              </CardDescription>
            </div>
            {data ? (
              <Badge
                variant='outline'
                className='border-sky-200 bg-sky-50 text-sky-700'
              >
                {t('module.billing.entitlements.runtimeBadge')}
              </Badge>
            ) : null}
          </div>
          <div className='rounded-2xl border border-sky-100 bg-white/85 px-4 py-3 text-sm text-slate-600'>
            {t('module.billing.entitlements.runtimeNote')}
          </div>
        </CardHeader>
      </Card>

      {error ? (
        <Card className='border-rose-200 bg-rose-50/80 shadow-none'>
          <CardContent className='px-6 py-4 text-sm text-rose-700'>
            {t('module.billing.entitlements.loadError')}
          </CardContent>
        </Card>
      ) : null}

      {isLoading ? (
        <div className='grid gap-4 lg:grid-cols-2'>
          <Skeleton className='h-40 rounded-[24px]' />
          <Skeleton className='h-40 rounded-[24px]' />
          <Skeleton className='h-40 rounded-[24px]' />
          <Skeleton className='h-40 rounded-[24px]' />
        </div>
      ) : null}

      {data ? (
        <>
          <div className='grid gap-4 lg:grid-cols-2 xl:grid-cols-4'>
            <EntitlementMetricCard
              title={t('module.billing.entitlements.metrics.priorityClass')}
              value={resolvePriorityValue(t, data.priority_class)}
              description={t(
                'module.billing.entitlements.metricDescriptions.priorityClass',
              )}
              accentClassName='bg-amber-400'
            />
            <EntitlementMetricCard
              title={t('module.billing.entitlements.metrics.maxConcurrency')}
              value={String(data.max_concurrency)}
              description={t(
                'module.billing.entitlements.metricDescriptions.maxConcurrency',
              )}
              accentClassName='bg-sky-400'
            />
            <EntitlementMetricCard
              title={t('module.billing.entitlements.metrics.analyticsTier')}
              value={resolveAnalyticsValue(t, data.analytics_tier)}
              description={t(
                'module.billing.entitlements.metricDescriptions.analyticsTier',
              )}
              accentClassName='bg-violet-400'
            />
            <EntitlementMetricCard
              title={t('module.billing.entitlements.metrics.supportTier')}
              value={resolveSupportValue(t, data.support_tier)}
              description={t(
                'module.billing.entitlements.metricDescriptions.supportTier',
              )}
              accentClassName='bg-emerald-400'
            />
          </div>

          <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
            <CardHeader className='space-y-2'>
              <CardTitle className='text-lg text-slate-900'>
                {t('module.billing.entitlements.flags.title')}
              </CardTitle>
              <CardDescription className='leading-6 text-slate-600'>
                {t('module.billing.entitlements.flags.description')}
              </CardDescription>
            </CardHeader>
            <CardContent className='grid gap-3 md:grid-cols-2'>
              <div className='rounded-2xl border border-slate-200 bg-slate-50/80 p-4'>
                <div className='flex items-center justify-between gap-3'>
                  <p className='font-medium text-slate-900'>
                    {t('module.billing.entitlements.flags.branding')}
                  </p>
                  <Badge
                    variant='outline'
                    className={
                      data.branding_enabled
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : 'border-slate-200 bg-slate-100 text-slate-600'
                    }
                  >
                    {data.branding_enabled
                      ? t('module.billing.entitlements.flags.enabled')
                      : t('module.billing.entitlements.flags.disabled')}
                  </Badge>
                </div>
                <p className='mt-3 text-sm leading-6 text-slate-600'>
                  {t('module.billing.entitlements.flags.brandingDescription')}
                </p>
              </div>

              <div className='rounded-2xl border border-slate-200 bg-slate-50/80 p-4'>
                <div className='flex items-center justify-between gap-3'>
                  <p className='font-medium text-slate-900'>
                    {t('module.billing.entitlements.flags.customDomain')}
                  </p>
                  <Badge
                    variant='outline'
                    className={
                      data.custom_domain_enabled
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : 'border-slate-200 bg-slate-100 text-slate-600'
                    }
                  >
                    {data.custom_domain_enabled
                      ? t('module.billing.entitlements.flags.enabled')
                      : t('module.billing.entitlements.flags.disabled')}
                  </Badge>
                </div>
                <p className='mt-3 text-sm leading-6 text-slate-600'>
                  {t(
                    'module.billing.entitlements.flags.customDomainDescription',
                  )}
                </p>
              </div>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
