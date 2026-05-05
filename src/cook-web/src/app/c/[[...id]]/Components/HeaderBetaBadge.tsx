import { cn } from '@/lib/utils';
import { memo } from 'react';

interface HeaderBetaBadgeProps {
  variant?: 'corner' | 'inline';
  className?: string;
}

export const HeaderBetaBadge = ({
  variant = 'corner',
  className,
}: HeaderBetaBadgeProps) => {
  return (
    <span
      className={cn(
        'pointer-events-none inline-flex shrink-0 items-center justify-center rounded-[24px] bg-[var(--primary,#0f63ee)] px-[5px] py-[1px] text-[10px] font-[var(--font-weight-medium,500)] leading-[12px] text-[var(--base-primary-foreground,#FAFAFA)] shadow-[var(--shadow-xs-offset-x,0)_var(--shadow-xs-offset-y,1px)_var(--shadow-xs-blur-radius,2px)_var(--shadow-xs-spread-radius,0)_var(--shadow-xs-color,rgba(0,0,0,0.05))]',
        variant === 'corner' ? 'absolute -right-2 -top-2' : '',
        className,
      )}
    >
      Beta
    </span>
  );
};

export default memo(HeaderBetaBadge);
