'use client';

import Link from 'next/link';
import { Fragment, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/Breadcrumb';
import { cn } from '@/lib/utils';

export type AdminBreadcrumbItem = {
  label: ReactNode;
  href?: string;
};

type AdminBreadcrumbProps = {
  items: AdminBreadcrumbItem[];
  className?: string;
};

export default function AdminBreadcrumb({
  items,
  className,
}: AdminBreadcrumbProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return null;
  }

  const normalizedItems =
    items[0]?.href === '/admin'
      ? items
      : [{ label: t('common.core.home'), href: '/admin' }, ...items];

  return (
    <Breadcrumb className={cn('mb-[22px]', className)}>
      <BreadcrumbList>
        {normalizedItems.map((item, index) => {
          const isLastItem = index === normalizedItems.length - 1;
          const isSingleItem = normalizedItems.length === 1;
          const key = `${item.href || 'current'}-${index}`;

          return (
            <Fragment key={key}>
              <BreadcrumbItem>
                {item.href && !isLastItem ? (
                  <BreadcrumbLink asChild>
                    <Link href={item.href}>{item.label}</Link>
                  </BreadcrumbLink>
                ) : !isLastItem ? (
                  <span className='text-sm font-normal text-muted-foreground'>
                    {item.label}
                  </span>
                ) : (
                  <BreadcrumbPage
                    className={isSingleItem ? 'text-muted-foreground' : ''}
                  >
                    {item.label}
                  </BreadcrumbPage>
                )}
              </BreadcrumbItem>
              {!isLastItem ? <BreadcrumbSeparator /> : null}
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
