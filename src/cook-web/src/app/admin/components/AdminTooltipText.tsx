'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

type AdminTooltipTextProps = {
  text?: string | null;
  className?: string;
  emptyValue: string;
};

export default function AdminTooltipText({
  text,
  className,
  emptyValue,
}: AdminTooltipTextProps) {
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const [isOverflowing, setIsOverflowing] = useState(false);
  const trimmedText = text?.trim() ?? '';
  const value = trimmedText.length > 0 ? trimmedText : emptyValue;

  useEffect(() => {
    const element = triggerRef.current;
    if (!element) {
      setIsOverflowing(false);
      return;
    }

    const updateOverflowState = () => {
      setIsOverflowing(
        element.scrollWidth > element.clientWidth ||
          element.scrollHeight > element.clientHeight,
      );
    };

    updateOverflowState();

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(() => {
        updateOverflowState();
      });
      observer.observe(element);
      return () => observer.disconnect();
    }

    window.addEventListener('resize', updateOverflowState);
    return () => window.removeEventListener('resize', updateOverflowState);
  }, [isOverflowing, value]);

  const content = (
    <span
      ref={triggerRef}
      className={cn(
        'inline-block max-w-full overflow-hidden text-ellipsis whitespace-nowrap align-bottom',
        className,
      )}
    >
      {value}
    </span>
  );

  if (!isOverflowing) {
    return content;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side='top'>{value}</TooltipContent>
    </Tooltip>
  );
}
