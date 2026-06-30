'use client';

import { useEffect, useState } from 'react';
import type { ChangeEvent, KeyboardEvent, MouseEvent } from 'react';
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';

export type AppPaginationProps = {
  pageIndex: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  prevLabel: string;
  nextLabel: string;
  prevAriaLabel: string;
  nextAriaLabel: string;
  className?: string;
  hideWhenSinglePage?: boolean;
  jumpInputThreshold?: number;
  jumpInputAriaLabel: string;
};

const MAX_VISIBLE_PAGES = 5;
const DEFAULT_JUMP_INPUT_THRESHOLD = 20;
const JUMP_INPUT_SEPARATOR = '/';
const DISABLED_LINK_CLASS_NAME = 'pointer-events-none opacity-50';
const ACTIVE_LINK_CLASS_NAME = 'pointer-events-none';

const buildPageItems = (
  pageIndex: number,
  pageCount: number,
): Array<number | 'start-ellipsis' | 'end-ellipsis'> => {
  if (pageCount <= MAX_VISIBLE_PAGES + 2) {
    return Array.from({ length: pageCount }, (_, index) => index + 1);
  }

  const items: Array<number | 'start-ellipsis' | 'end-ellipsis'> = [1];

  if (pageIndex > 3) {
    items.push('start-ellipsis');
  }

  let rangeStart = Math.max(2, pageIndex - 1);
  let rangeEnd = Math.min(pageCount - 1, pageIndex + 1);

  if (pageIndex <= 3) {
    rangeStart = 2;
    rangeEnd = Math.min(4, pageCount - 1);
  }

  if (pageIndex >= pageCount - 2) {
    rangeStart = Math.max(2, pageCount - 3);
    rangeEnd = pageCount - 1;
  }

  for (let page = rangeStart; page <= rangeEnd; page += 1) {
    items.push(page);
  }

  if (pageIndex < pageCount - 2) {
    items.push('end-ellipsis');
  }

  items.push(pageCount);

  return items;
};

export function AppPagination({
  pageIndex,
  pageCount,
  onPageChange,
  prevLabel,
  nextLabel,
  prevAriaLabel,
  nextAriaLabel,
  className,
  hideWhenSinglePage = false,
  jumpInputThreshold = DEFAULT_JUMP_INPUT_THRESHOLD,
  jumpInputAriaLabel,
}: AppPaginationProps) {
  const safePageCount = Number.isFinite(pageCount) ? pageCount : 1;
  const normalizedPageCount = Math.max(safePageCount, 1);
  const safePageIndex = Number.isFinite(pageIndex) ? pageIndex : 1;
  const normalizedPageIndex = Math.min(
    Math.max(safePageIndex, 1),
    normalizedPageCount,
  );
  const shouldShowJumpInput =
    normalizedPageCount >= Math.max(jumpInputThreshold, 1);
  const [jumpInputValue, setJumpInputValue] = useState(
    String(normalizedPageIndex),
  );

  useEffect(() => {
    setJumpInputValue(String(normalizedPageIndex));
  }, [normalizedPageIndex]);

  if (hideWhenSinglePage && normalizedPageCount <= 1) {
    return null;
  }

  const handlePageClick =
    (targetPage: number) => (event: MouseEvent<HTMLAnchorElement>) => {
      event.preventDefault();
      if (
        targetPage < 1 ||
        targetPage > normalizedPageCount ||
        targetPage === normalizedPageIndex
      ) {
        return;
      }
      onPageChange(targetPage);
    };

  const handleJumpInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    setJumpInputValue(event.target.value.replace(/\D/g, ''));
  };

  const commitJumpInput = () => {
    const targetPage = Number.parseInt(jumpInputValue, 10);
    if (!Number.isFinite(targetPage)) {
      setJumpInputValue(String(normalizedPageIndex));
      return;
    }
    const normalizedTargetPage = Math.min(
      Math.max(targetPage, 1),
      normalizedPageCount,
    );
    setJumpInputValue(String(normalizedTargetPage));
    if (normalizedTargetPage !== normalizedPageIndex) {
      onPageChange(normalizedTargetPage);
    }
  };

  const handleJumpInputBlur = () => {
    commitJumpInput();
  };

  const handleJumpInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') {
      return;
    }
    event.preventDefault();
    event.currentTarget.blur();
  };

  return (
    <Pagination className={className}>
      <PaginationContent>
        <PaginationItem>
          <PaginationPrevious
            href='#'
            onClick={handlePageClick(normalizedPageIndex - 1)}
            aria-disabled={normalizedPageIndex <= 1}
            aria-label={prevAriaLabel}
            tabIndex={normalizedPageIndex <= 1 ? -1 : undefined}
            className={
              normalizedPageIndex <= 1 ? DISABLED_LINK_CLASS_NAME : undefined
            }
          >
            {prevLabel}
          </PaginationPrevious>
        </PaginationItem>

        {buildPageItems(normalizedPageIndex, normalizedPageCount).map(item => {
          if (item === 'start-ellipsis' || item === 'end-ellipsis') {
            return (
              <PaginationItem key={item}>
                <PaginationEllipsis />
              </PaginationItem>
            );
          }

          return (
            <PaginationItem key={item}>
              <PaginationLink
                href='#'
                isActive={normalizedPageIndex === item}
                onClick={handlePageClick(item)}
                tabIndex={normalizedPageIndex === item ? -1 : undefined}
                className={
                  normalizedPageIndex === item
                    ? ACTIVE_LINK_CLASS_NAME
                    : undefined
                }
              >
                {item}
              </PaginationLink>
            </PaginationItem>
          );
        })}

        <PaginationItem>
          <PaginationNext
            href='#'
            onClick={handlePageClick(normalizedPageIndex + 1)}
            aria-disabled={normalizedPageIndex >= normalizedPageCount}
            aria-label={nextAriaLabel}
            tabIndex={
              normalizedPageIndex >= normalizedPageCount ? -1 : undefined
            }
            className={
              normalizedPageIndex >= normalizedPageCount
                ? DISABLED_LINK_CLASS_NAME
                : undefined
            }
          >
            {nextLabel}
          </PaginationNext>
        </PaginationItem>

        {shouldShowJumpInput && (
          <PaginationItem className='ml-1 flex items-center gap-1 text-sm text-muted-foreground'>
            <input
              type='text'
              inputMode='numeric'
              pattern='[0-9]*'
              value={jumpInputValue}
              onChange={handleJumpInputChange}
              onBlur={handleJumpInputBlur}
              onKeyDown={handleJumpInputKeyDown}
              aria-label={jumpInputAriaLabel}
              className='h-9 w-14 rounded-md border border-input bg-background px-2 text-center text-sm text-foreground outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/20'
            />
            <span aria-hidden>{JUMP_INPUT_SEPARATOR}</span>
            <span>{normalizedPageCount}</span>
          </PaginationItem>
        )}
      </PaginationContent>
    </Pagination>
  );
}
