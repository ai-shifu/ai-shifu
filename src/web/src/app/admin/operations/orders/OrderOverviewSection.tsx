'use client';

import React from 'react';
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
    <AdminMetricCardGroup
      title={title}
      items={cards}
      gridClassName={cn(
        'grid-cols-2 md:grid-cols-3 xl:grid-cols-4 min-[1680px]:grid-cols-6',
        gridClassName,
      )}
      staleMessage={staleMessage}
      activeFilter={
        activeCardLabel && onClearActive
          ? {
              label: activeFilterLabel,
              value: activeCardLabel,
              clearAriaLabel: `${activeCardLabel} ${clearLabel}`,
              onClear: onClearActive,
            }
          : null
      }
    />
  );
}
