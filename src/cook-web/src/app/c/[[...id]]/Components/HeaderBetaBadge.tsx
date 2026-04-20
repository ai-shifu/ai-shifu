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
        'pointer-events-none inline-flex shrink-0 rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none text-white shadow-sm',
        variant === 'corner' ? 'absolute -right-2 -top-2' : '',
        className,
      )}
    >
      Beta
    </span>
  );
};

export default memo(HeaderBetaBadge);
