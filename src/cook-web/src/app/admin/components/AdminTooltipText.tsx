'use client';

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

type AdminTooltipTextProps = {
  text?: string | null;
  className?: string;
  emptyValue?: string;
};

export default function AdminTooltipText({
  text,
  className,
  emptyValue = '--',
}: AdminTooltipTextProps) {
  const trimmedText = text?.trim() ?? '';
  const value = trimmedText.length > 0 ? trimmedText : emptyValue;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            'inline-block max-w-full overflow-hidden text-ellipsis whitespace-nowrap align-bottom',
            className,
          )}
        >
          {value}
        </span>
      </TooltipTrigger>
      <TooltipContent side='top'>{value}</TooltipContent>
    </Tooltip>
  );
}
