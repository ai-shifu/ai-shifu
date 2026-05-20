'use client';

import type { ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

type AdminTooltipTextProps = {
  text?: string | null;
  displayText?: ReactNode;
  className?: string;
  emptyValue: string;
};

export default function AdminTooltipText({
  text,
  displayText,
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

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => {
        updateOverflowState();
      });
      resizeObserver.observe(element);
    }

    let mutationObserver: MutationObserver | null = null;
    if (typeof MutationObserver !== 'undefined') {
      mutationObserver = new MutationObserver(() => {
        updateOverflowState();
      });
      mutationObserver.observe(element, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }

    window.addEventListener('resize', updateOverflowState);
    return () => {
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
      window.removeEventListener('resize', updateOverflowState);
    };
  }, [value]);

  const content = (
    <span
      ref={triggerRef}
      className={cn(
        'inline-block max-w-full overflow-hidden text-ellipsis whitespace-nowrap align-bottom',
        className,
      )}
    >
      {displayText ?? value}
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
