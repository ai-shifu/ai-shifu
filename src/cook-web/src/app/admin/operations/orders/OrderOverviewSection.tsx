'use client';

import React from 'react';
import { X } from 'lucide-react';
import { AdminMetricCardGroup } from '@/app/admin/components/AdminMetricCard';
import { cn } from '@/lib/utils';

type OrderOverviewCard = {
  key: string;
  label: string;
  value: string;
  tooltip: string;
  onClick?: () => void;
};

type OrderOverviewSectionProps = {
  title: string;
  cards: OrderOverviewCard[];
  activeCardLabel?: string | null;
  activeFilterLabel: string;
  clearLabel: string;
  staleMessage?: string | null;
  onClearActive?: () => void;
  gridClassName?: string;
};

export default function OrderOverviewSection({
  title,
  cards,
  activeCardLabel,
  activeFilterLabel,
  clearLabel,
  staleMessage,
  onClearActive,
  gridClassName,
}: OrderOverviewSectionProps) {
  return (
    <div className='mb-5 rounded-xl border border-border bg-white p-4 shadow-sm'>
      <div className='mb-3'>
        <h2 className='text-base font-semibold text-foreground'>{title}</h2>
      </div>

      {staleMessage ? (
        <div className='mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800'>
          {staleMessage}
        </div>
      ) : null}

      <AdminMetricCardGroup
        items={cards}
        gridClassName={cn(
          'grid-cols-2 md:grid-cols-3 xl:grid-cols-4 min-[1680px]:grid-cols-6',
          gridClassName,
        )}
      />

      {activeCardLabel && onClearActive ? (
        <div className='mt-4 flex flex-wrap items-center gap-2'>
          <span className='text-sm text-muted-foreground'>
            {activeFilterLabel}
          </span>
          <button
            type='button'
            aria-label={`${activeCardLabel} ${clearLabel}`}
            className='inline-flex items-center gap-1 rounded-full border border-border bg-muted/30 px-3 py-1 text-sm text-foreground transition-colors hover:bg-muted'
            onClick={onClearActive}
          >
            <span>{activeCardLabel}</span>
            <X className='h-3.5 w-3.5' />
          </button>
        </div>
      ) : null}
    </div>
  );
}
