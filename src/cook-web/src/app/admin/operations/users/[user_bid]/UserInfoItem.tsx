'use client';

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

type UserInfoItemProps = {
  label: ReactNode;
  value?: string;
  emptyValue: string;
  onClick?: () => void;
  valueClassName?: string;
  valueAriaLabel?: string;
};

export default function UserInfoItem({
  label,
  value,
  emptyValue,
  onClick,
  valueClassName,
  valueAriaLabel,
}: UserInfoItemProps) {
  const displayValue = value && value.trim().length > 0 ? value : emptyValue;
  const accessibleValueLabel = valueAriaLabel
    ? `${valueAriaLabel}: ${displayValue}`
    : undefined;

  return (
    <div className='space-y-1 rounded-lg border border-border/70 bg-muted/20 px-4 py-3'>
      <div className='flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground'>
        {label}
      </div>
      {onClick ? (
        <button
          type='button'
          aria-label={accessibleValueLabel}
          className={cn(
            'w-full break-all text-left text-sm font-medium text-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            valueClassName,
          )}
          onClick={onClick}
        >
          {displayValue}
        </button>
      ) : (
        <div
          className={cn(
            'break-all text-sm font-medium text-foreground',
            valueClassName,
          )}
        >
          {displayValue}
        </div>
      )}
    </div>
  );
}
