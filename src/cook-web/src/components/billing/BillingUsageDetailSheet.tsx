import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import type { BillingLedgerItem } from '@/types/billing';
import {
  formatBillingCredits,
  formatBillingDateTime,
  resolveBillingLedgerEntryLabel,
  resolveBillingUsageSceneLabel,
} from '@/lib/billing';

type BillingUsageDetailSheetProps = {
  item: BillingLedgerItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className='flex items-start justify-between gap-4 border-b border-slate-100 py-3 text-sm last:border-b-0'>
      <span className='text-slate-500'>{label}</span>
      <span className='text-right font-medium text-slate-900'>{value}</span>
    </div>
  );
}

export function BillingUsageDetailSheet({
  item,
  open,
  onOpenChange,
}: BillingUsageDetailSheetProps) {
  const { t, i18n } = useTranslation();
  const breakdown = item?.metadata.metric_breakdown || [];

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[360px] md:w-[420px] lg:w-[520px]'>
        <SheetHeader className='border-b border-border px-6 py-4 pr-12'>
          <SheetTitle>{t('module.billing.ledger.detail.title')}</SheetTitle>
          <SheetDescription>
            {item ? resolveBillingLedgerEntryLabel(t, item.entry_type) : ''}
          </SheetDescription>
        </SheetHeader>

        <div className='flex-1 overflow-auto px-6 py-4'>
          {item ? (
            <div className='space-y-6'>
              <div className='rounded-2xl bg-slate-50 p-4'>
                <DetailRow
                  label={t('module.billing.ledger.detail.usageBid')}
                  value={item.metadata.usage_bid || item.source_bid}
                />
                <DetailRow
                  label={t('module.billing.ledger.detail.scene')}
                  value={
                    resolveBillingUsageSceneLabel(
                      t,
                      item.metadata.usage_scene,
                    ) || '--'
                  }
                />
                <DetailRow
                  label={t('module.billing.ledger.detail.sourceBid')}
                  value={item.source_bid}
                />
                <DetailRow
                  label={t('module.billing.ledger.detail.balanceAfter')}
                  value={formatBillingCredits(
                    item.balance_after,
                    i18n.language,
                  )}
                />
                <DetailRow
                  label={t('module.billing.ledger.table.createdAt')}
                  value={formatBillingDateTime(item.created_at, i18n.language)}
                />
              </div>

              <div className='space-y-3'>
                {breakdown.length ? (
                  breakdown.map(breakdownItem => (
                    <div
                      key={`${breakdownItem.billing_metric}-${breakdownItem.raw_amount}`}
                      className='rounded-2xl border border-slate-200 bg-white p-4 shadow-sm'
                    >
                      <DetailRow
                        label={t('module.billing.ledger.detail.billingMetric')}
                        value={breakdownItem.billing_metric}
                      />
                      <DetailRow
                        label={t('module.billing.ledger.detail.rawAmount')}
                        value={String(breakdownItem.raw_amount)}
                      />
                      <DetailRow
                        label={t('module.billing.ledger.detail.unitSize')}
                        value={String(breakdownItem.unit_size)}
                      />
                      <DetailRow
                        label={t('module.billing.ledger.detail.creditsPerUnit')}
                        value={String(breakdownItem.credits_per_unit)}
                      />
                      <DetailRow
                        label={t('module.billing.ledger.detail.roundingMode')}
                        value={String(breakdownItem.rounding_mode)}
                      />
                      <DetailRow
                        label={t(
                          'module.billing.ledger.detail.consumedCredits',
                        )}
                        value={formatBillingCredits(
                          breakdownItem.consumed_credits,
                          i18n.language,
                        )}
                      />
                    </div>
                  ))
                ) : (
                  <div className='rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500'>
                    {t('module.billing.ledger.detail.emptyBreakdown')}
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
