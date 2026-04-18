'use client';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

type AdminOverflowTooltipTextProps = {
  text?: string | null;
  className?: string;
  emptyValue?: string;
};

export default function AdminOverflowTooltipText({
  text,
  className,
  emptyValue = '--',
}: AdminOverflowTooltipTextProps) {
  const value = text && text.trim().length > 0 ? text : emptyValue;

  return (
    <TooltipProvider delayDuration={150}>
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
    </TooltipProvider>
  );
}
