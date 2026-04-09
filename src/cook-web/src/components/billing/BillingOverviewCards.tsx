import type { ReactNode } from 'react';
import { CheckIcon, InformationCircleIcon } from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import type { BillingPlan } from '@/types/billing';
import { cn } from '@/lib/utils';

export type ShowcaseTab = 'monthly' | 'yearly' | 'topup';

export function getPlanFeatureKeys(product: BillingPlan): string[] {
  const productHighlights = product.highlights?.filter(item => Boolean(item));
  if (productHighlights && productHighlights.length > 0) {
    return productHighlights;
  }
  if (product.billing_interval === 'year') {
    return [
      'module.billing.package.features.yearly.pro.branding',
      'module.billing.package.features.yearly.pro.domain',
      'module.billing.package.features.yearly.pro.priority',
      'module.billing.package.features.yearly.pro.analytics',
      'module.billing.package.features.yearly.pro.support',
    ];
  }
  return [
    'module.billing.package.features.monthly.publish',
    'module.billing.package.features.monthly.preview',
    'module.billing.package.features.monthly.support',
  ];
}

export function getFreeFeatureKeys(): string[] {
  return [
    'module.billing.package.features.free.publish',
    'module.billing.package.features.free.preview',
  ];
}

export function PlanFeatureList({ items }: { items: string[] }) {
  const { t } = useTranslation();

  return (
    <div className='space-y-3'>
      <p className='text-sm font-semibold text-slate-950'>
        {t('module.billing.package.featuresTitle')}
      </p>
      <ul className='space-y-3'>
        {items.map(item => (
          <li
            key={item}
            className='flex items-center justify-between gap-4 text-sm text-slate-600'
          >
            <div className='flex items-center gap-3'>
              <CheckIcon className='h-5 w-5 text-slate-950' />
              <span>{t(item)}</span>
            </div>
            <InformationCircleIcon className='h-4 w-4 shrink-0 text-slate-300' />
          </li>
        ))}
      </ul>
    </div>
  );
}

type PlanShowcaseCardProps = {
  actionLabel: string;
  actionLoading?: boolean;
  compact?: boolean;
  creditSummary: string;
  description: string;
  disabled?: boolean;
  featured?: boolean;
  footer: ReactNode;
  onAction?: () => void;
  priceLabel: string;
  priceMetaLabel?: string;
  testId: string;
  title: string;
};

export function PlanShowcaseCard({
  actionLabel,
  actionLoading = false,
  compact = false,
  creditSummary,
  description,
  disabled = false,
  featured = false,
  footer,
  onAction,
  priceLabel,
  priceMetaLabel,
  testId,
  title,
}: PlanShowcaseCardProps) {
  return (
    <div
      className={cn(
        'flex h-full flex-col rounded-[34px] border bg-white p-7 shadow-[0_20px_56px_rgba(15,23,42,0.08)] transition-all',
        compact ? 'min-h-[260px]' : 'min-h-[620px]',
        featured
          ? 'border-[#1d5bd8] bg-[radial-gradient(circle_at_top,#eef5ff_0%,#ffffff_72%)] shadow-[0_24px_64px_rgba(29,91,216,0.18)]'
          : 'border-slate-200',
      )}
      data-testid={testId}
    >
      <div className='space-y-4'>
        <h3
          className={cn(
            'text-xl font-semibold leading-tight tracking-tight md:text-2xl',
            featured ? 'text-[#1d5bd8]' : 'text-slate-950',
          )}
        >
          {title}
        </h3>
        <p className='min-h-[52px] text-sm leading-6 text-slate-500 md:text-base'>
          {description}
        </p>
      </div>

      <div className='mt-8 flex flex-wrap items-end gap-x-2 gap-y-1'>
        <div className='text-3xl font-semibold leading-none tracking-tight text-slate-950 md:text-4xl'>
          {priceLabel}
        </div>
        {priceMetaLabel ? (
          <div className='text-sm font-medium leading-6 text-slate-500 md:text-base'>
            {priceMetaLabel}
          </div>
        ) : null}
      </div>

      <Button
        className={cn(
          'mt-8 h-12 rounded-2xl text-sm font-semibold md:text-base',
          featured
            ? 'bg-[#1d5bd8] text-white hover:bg-[#194fbc]'
            : 'bg-slate-100 text-slate-900 hover:bg-slate-200',
        )}
        data-testid={`${testId}-action`}
        disabled={disabled || actionLoading}
        onClick={onAction}
        type='button'
        variant={featured ? 'default' : 'secondary'}
      >
        {actionLoading ? '...' : actionLabel}
      </Button>

      <div className='mt-8 rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-sm'>
        <div className='text-lg font-semibold leading-tight text-slate-950 md:text-xl'>
          {creditSummary}
        </div>
      </div>

      <div className='mt-8 flex-1'>{footer}</div>
    </div>
  );
}

type TopupCardProps = {
  actionLabel: string;
  actionLoading?: boolean;
  creditsLabel: string;
  description: string;
  disabled?: boolean;
  featured?: boolean;
  onAction?: () => void;
  priceLabel: string;
  testId: string;
};

export function TopupCard({
  actionLabel,
  actionLoading = false,
  creditsLabel,
  description,
  disabled = false,
  featured = false,
  onAction,
  priceLabel,
  testId,
}: TopupCardProps) {
  return (
    <div
      className={cn(
        'flex min-h-[250px] flex-col justify-between rounded-[30px] border bg-white p-8 shadow-[0_18px_48px_rgba(15,23,42,0.08)]',
        featured
          ? 'border-[#1d5bd8] shadow-[0_24px_60px_rgba(29,91,216,0.16)]'
          : 'border-slate-200',
      )}
      data-testid={testId}
    >
      <div className='space-y-3'>
        <div className='flex items-center gap-4'>
          <div className='flex h-11 w-11 items-center justify-center rounded-2xl bg-[#eef5ff] text-[#1d5bd8]'>
            <InformationCircleIcon className='h-6 w-6' />
          </div>
          <div>
            <div className='text-xl font-semibold leading-tight text-slate-950 md:text-2xl'>
              {creditsLabel}
            </div>
            <div className='text-sm leading-6 text-slate-500'>
              {description}
            </div>
          </div>
        </div>
      </div>

      <div className='mt-8 flex items-end justify-between gap-4'>
        <div className='text-2xl font-semibold leading-none tracking-tight text-slate-950 md:text-3xl'>
          {priceLabel}
        </div>
        <Button
          className='h-11 rounded-2xl px-6 text-sm font-semibold'
          data-testid={`${testId}-action`}
          disabled={disabled || actionLoading}
          onClick={onAction}
          type='button'
        >
          {actionLoading ? '...' : actionLabel}
        </Button>
      </div>
    </div>
  );
}
