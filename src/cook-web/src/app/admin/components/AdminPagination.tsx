'use client';

import {
  AppPagination,
  type AppPaginationProps,
} from '@/components/pagination/AppPagination';
import { cn } from '@/lib/utils';

export type { AppPaginationProps as AdminPaginationProps } from '@/components/pagination/AppPagination';

const ADMIN_PAGINATION_CLASS = '[&_li:last-child_a]:pr-0';

export function AdminPagination({ className, ...props }: AppPaginationProps) {
  return (
    <AppPagination
      {...props}
      className={cn(ADMIN_PAGINATION_CLASS, className)}
    />
  );
}
