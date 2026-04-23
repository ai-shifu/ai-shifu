import React from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/Badge';
import { useBillingBootstrap } from '@/hooks/useBillingData';
import type {
  BillingCapability,
  BillingCapabilityStatus,
} from '@/types/billing';
import {
  resolveBillingCapabilityDescription,
  resolveBillingCapabilityStatusLabel,
  resolveBillingCapabilityTitle,
} from '@/lib/billing';
import { cn } from '@/lib/utils';

type BillingCapabilitySummaryProps = {
  audience: 'admin' | 'creator';
};

function resolveCapabilityBadgeClass(status: BillingCapabilityStatus): string {
  switch (status) {
    case 'default_disabled':
      return 'border-amber-200 bg-amber-50 text-amber-800';
    case 'internal_only':
      return 'border-slate-200 bg-slate-100 text-slate-700';
    default:
      return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
}

function CapabilityCard({ capability }: { capability: BillingCapability }) {
  const { t } = useTranslation();

  return (
    <div className='rounded-[24px] border border-slate-200 bg-white/90 p-4 shadow-sm'>
      <div className='flex items-start justify-between gap-3'>
        <div className='space-y-1'>
          <h3 className='text-sm font-semibold text-slate-900'>
            {resolveBillingCapabilityTitle(t, capability)}
          </h3>
          <p className='text-sm leading-6 text-slate-500'>
            {resolveBillingCapabilityDescription(t, capability)}
          </p>
        </div>
        <Badge
          className={cn(
            'border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em]',
            resolveCapabilityBadgeClass(capability.status),
          )}
          variant='outline'
        >
          {resolveBillingCapabilityStatusLabel(t, capability.status)}
        </Badge>
      </div>
    </div>
  );
}

export function BillingCapabilitySummary({
  audience,
}: BillingCapabilitySummaryProps) {
  const { t } = useTranslation();
  const { data } = useBillingBootstrap();
  const capabilities = data?.capabilities ?? [];
  const visibleCapabilities = capabilities.filter(
    capability => capability.user_visible && capability.audience === audience,
  );
  const activeCount = visibleCapabilities.filter(
    capability => capability.status === 'active',
  ).length;
  const defaultDisabledCount = capabilities.filter(
    capability => capability.status === 'default_disabled',
  ).length;
  const internalOnlyCount = capabilities.filter(
    capability => capability.status === 'internal_only',
  ).length;

  if (!data || visibleCapabilities.length === 0) {
    return null;
  }

  return (
    <section
      className='grid gap-4 rounded-[28px] border border-slate-200 bg-white/80 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]'
      data-testid={`billing-capability-summary-${audience}`}
    >
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div className='space-y-1'>
          <p className='text-sm font-semibold text-slate-900'>
            {t('module.billing.capabilities.title')}
          </p>
          <p className='text-sm leading-6 text-slate-500'>
            {t('module.billing.capabilities.description')}
          </p>
        </div>
        <div className='flex flex-wrap gap-2'>
          <Badge className='border border-emerald-200 bg-emerald-50 text-emerald-700'>
            {t('module.billing.capabilities.summary.active', {
              count: activeCount,
            })}
          </Badge>
          <Badge className='border border-amber-200 bg-amber-50 text-amber-800'>
            {t('module.billing.capabilities.summary.defaultDisabled', {
              count: defaultDisabledCount,
            })}
          </Badge>
          <Badge className='border border-slate-200 bg-slate-100 text-slate-700'>
            {t('module.billing.capabilities.summary.internalOnly', {
              count: internalOnlyCount,
            })}
          </Badge>
        </div>
      </div>

      <div className='grid gap-3 lg:grid-cols-2'>
        {visibleCapabilities.map(capability => (
          <CapabilityCard
            key={capability.key}
            capability={capability}
          />
        ))}
      </div>
    </section>
  );
}
