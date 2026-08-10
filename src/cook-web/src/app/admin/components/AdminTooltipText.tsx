'use client';

import type { ReactNode } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
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
  alwaysShowTooltip?: boolean;
  forceTooltip?: boolean;
};

export default function AdminTooltipText({
  text,
  displayText,
  className,
  emptyValue,
  alwaysShowTooltip = false,
  forceTooltip = false,
}: AdminTooltipTextProps) {
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const [isOverflowing, setIsOverflowing] = useState(false);
  const trimmedText = text?.trim() ?? '';
  const value = trimmedText.length > 0 ? trimmedText : emptyValue;

  const updateOverflowState = useCallback(() => {
    const element = triggerRef.current;
    if (!element) {
      setIsOverflowing(false);
      return;
    }

    const tableCell = element.closest('td,th') as HTMLElement | null;
    const isClippedByOwnBounds =
      element.scrollWidth > element.clientWidth ||
      element.scrollHeight > element.clientHeight;
    const isClippedByTableCell =
      tableCell && tableCell !== element
        ? element.scrollWidth > tableCell.clientWidth ||
          tableCell.scrollWidth > tableCell.clientWidth
        : false;

    setIsOverflowing(Boolean(isClippedByOwnBounds || isClippedByTableCell));
  }, []);

  useEffect(() => {
    const element = triggerRef.current;
    if (!element) {
      setIsOverflowing(false);
      return;
    }

    updateOverflowState();

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => {
        updateOverflowState();
      });
      resizeObserver.observe(element);
      const tableCell = element.closest('td,th');
      if (tableCell && tableCell !== element) {
        resizeObserver.observe(tableCell);
      }
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
  }, [updateOverflowState, value]);

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

  const shouldShowTooltip =
    isOverflowing ||
    ((alwaysShowTooltip || forceTooltip) && trimmedText.length > 0);

  if (!shouldShowTooltip) {
    return content;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side='top'>{value}</TooltipContent>
    </Tooltip>
  );
}
