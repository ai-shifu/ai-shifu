import React from 'react';
import {
  ExclamationTriangleIcon,
  InformationCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import { Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import type { BillingAlert } from '@/types/billing';
import { registerBillingTranslationUsage } from '@/lib/billing';

type BillingAlertsBannerProps = {
  alerts: BillingAlert[];
  actionLoading?: BillingAlert['action_type'] | '';
  isActionDisabled?: (alert: BillingAlert) => boolean;
  onAlertAction?: (alert: BillingAlert) => void;
};

function resolveAlertTone(severity: BillingAlert['severity']): {
  containerClassName: string;
  icon: React.ReactNode;
  iconClassName: string;
} {
  if (severity === 'error') {
    return {
      containerClassName: 'border-rose-200 bg-rose-50 text-rose-800',
      icon: <XCircleIcon className='h-5 w-5' />,
      iconClassName: 'text-rose-600',
    };
  }
  if (severity === 'warning') {
    return {
      containerClassName: 'border-amber-200 bg-amber-50 text-amber-800',
      icon: <ExclamationTriangleIcon className='h-5 w-5' />,
      iconClassName: 'text-amber-600',
    };
  }
  return {
    containerClassName: 'border-sky-200 bg-sky-50 text-sky-800',
    icon: <InformationCircleIcon className='h-5 w-5' />,
    iconClassName: 'text-sky-600',
  };
}

function resolveAlertActionLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  actionType?: BillingAlert['action_type'],
): string {
  if (actionType === 'checkout_topup') {
    return t('module.billing.alerts.actions.checkoutTopup');
  }
  if (actionType === 'resume_subscription') {
    return t('module.billing.alerts.actions.resumeSubscription');
  }
  if (actionType === 'open_orders') {
    return t('module.billing.alerts.actions.openOrders');
  }
  return '';
}

function isLowBalanceAlert(alert: BillingAlert) {
  return (
    alert.code === 'low_balance' ||
    alert.message_key === 'module.billing.alerts.lowBalance'
  );
}

export function BillingAlertsBanner({
  alerts,
  actionLoading = '',
  isActionDisabled,
  onAlertAction,
}: BillingAlertsBannerProps) {
  const { t } = useTranslation();
  registerBillingTranslationUsage(t);

  if (!alerts.length) {
    return null;
  }

  return (
    <div className='space-y-3'>
      {alerts.map(alert => {
        if (isLowBalanceAlert(alert)) {
          return (
            <div
              key={alert.code}
              className='flex items-start gap-3 rounded-[var(--border-radius-rounded-lg,10px)] border border-[var(--base-border,#E5E5E5)] bg-[var(--base-card,#FFF)] px-[var(--spacing-4,16px)] py-[var(--spacing-3,12px)]'
              data-testid='billing-alert-low-balance'
            >
              <Info className='mt-0.5 h-5 w-5 shrink-0 text-[var(--base-foreground,#0A0A0A)]' />
              <div className='space-y-1'>
                <p className='text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]'>
                  {t('module.billing.alerts.lowBalanceTitle')}
                </p>
                <p className='text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
                  {t('module.billing.alerts.lowBalanceDescription')}
                </p>
              </div>
            </div>
          );
        }

        const tone = resolveAlertTone(alert.severity);
        const actionLabel = resolveAlertActionLabel(t, alert.action_type);
        const disabled = isActionDisabled?.(alert) || false;

        return (
          <div
            key={alert.code}
            className={`rounded-2xl border px-4 py-3 shadow-sm ${tone.containerClassName}`}
          >
            <div className='flex flex-col gap-3 md:flex-row md:items-start md:justify-between'>
              <div className='flex items-start gap-3'>
                <div className={`mt-0.5 shrink-0 ${tone.iconClassName}`}>
                  {tone.icon}
                </div>
                <div className='space-y-1'>
                  <p className='text-sm font-medium'>
                    {t(alert.message_key, alert.message_params || {})}
                  </p>
                  <p className='text-xs opacity-80'>{alert.code}</p>
                </div>
              </div>

              {actionLabel && onAlertAction ? (
                <Button
                  variant='outline'
                  size='sm'
                  disabled={disabled || actionLoading === alert.action_type}
                  onClick={() => onAlertAction(alert)}
                >
                  {actionLoading === alert.action_type
                    ? t('module.billing.catalog.actions.processing')
                    : actionLabel}
                </Button>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
