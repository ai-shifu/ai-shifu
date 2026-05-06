import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

type BillingNoticeCalloutProps = {
  children: ReactNode;
  className?: string;
  testId?: string;
};

export function BillingNoticeCallout({
  children,
  className,
  testId,
}: BillingNoticeCalloutProps) {
  return (
    <div
      className={cn(
        'rounded-2xl border border-[rgba(0,82,217,0.12)] bg-[rgba(0,82,217,0.04)] px-5 py-4 text-sm leading-6 text-[var(--base-foreground,#0A0A0A)]',
        className,
      )}
      data-testid={testId}
    >
      <ul className='list-disc space-y-2 pl-5 text-[var(--base-muted-foreground,#525252)]'>
        {children}
      </ul>
    </div>
  );
}
