'use client';

import { useTranslation } from 'react-i18next';
import {
  AppPagination,
  type AppPaginationProps,
} from '@/components/pagination/AppPagination';
import { cn } from '@/lib/utils';

export type AdminPaginationProps = Omit<
  AppPaginationProps,
  'jumpInputAriaLabel'
> & {
  jumpInputAriaLabel?: AppPaginationProps['jumpInputAriaLabel'];
};

const ADMIN_PAGINATION_CLASS = '[&_li:last-child_a]:pr-0';

export function AdminPagination({
  className,
  jumpInputAriaLabel,
  ...props
}: AdminPaginationProps) {
  const { t } = useTranslation();

  return (
    <AppPagination
      {...props}
      jumpInputAriaLabel={
        jumpInputAriaLabel ?? t('module.order.paginationJumpInputAriaLabel')
      }
      className={cn(ADMIN_PAGINATION_CLASS, className)}
    />
  );
}
