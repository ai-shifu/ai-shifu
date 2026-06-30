import type { CSSProperties, ReactNode } from 'react';
import { cn } from '@/lib/utils';

type AdminCountCardProps = {
  title: ReactNode;
  value: ReactNode;
  className?: string;
  valueClassName?: string;
};

const ADMIN_COUNT_CARD_STYLE: CSSProperties = {
  borderRadius: 'var(--border-radius-rounded-xl, 14px)',
  border: 'var(--border-width-border, 1px) solid var(--base-border, #E5E5E5)',
  background:
    'linear-gradient(180deg, rgba(23, 23, 23, 0.00) 0%, var(--base-primary, rgba(23, 23, 23, 0.05)) 100%), var(--base-card, #FFF)',
  boxShadow:
    'var(--shadow-sm-1-offset-x, 0) var(--shadow-sm-1-offset-y, 1px) var(--shadow-sm-1-blur-radius, 3px) var(--shadow-sm-1-spread-radius, 0) var(--shadow-sm-1-color, rgba(0, 0, 0, 0.10)), var(--shadow-sm-2-offset-x, 0) var(--shadow-sm-2-offset-y, 1px) var(--shadow-sm-2-blur-radius, 2px) var(--shadow-sm-2-spread-radius, -1px) var(--shadow-sm-2-color, rgba(0, 0, 0, 0.10))',
};

export default function AdminCountCard({
  title,
  value,
  className,
  valueClassName,
}: AdminCountCardProps) {
  return (
    <div
      className={cn('p-[var(--spacing-6,24px)]', className)}
      style={ADMIN_COUNT_CARD_STYLE}
    >
      <div className='text-[length:var(--text-sm-font-size,14px)] font-[var(--font-weight-normal,400)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'>
        {title}
      </div>
      <div
        className={cn(
          'mt-1.5 text-[length:var(--text-3xl-font-size,30px)] font-[var(--font-weight-semibold,600)] leading-[var(--text-3xl-line-height,36px)] text-[var(--base-card-foreground,#0A0A0A)]',
          valueClassName,
        )}
      >
        {value}
      </div>
    </div>
  );
}
