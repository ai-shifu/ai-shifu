'use client';

import Link from 'next/link';
import { Fragment } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/Breadcrumb';

type AdminOperationsBreadcrumbItem = {
  label: string;
  href?: string;
};

type AdminOperationsBreadcrumbProps = {
  items: AdminOperationsBreadcrumbItem[];
  className?: string;
};

export default function AdminOperationsBreadcrumb({
  items,
  className,
}: AdminOperationsBreadcrumbProps) {
  if (items.length <= 1) {
    return null;
  }

  return (
    <Breadcrumb className={className}>
      <BreadcrumbList>
        {items.map((item, index) => {
          const isLastItem = index === items.length - 1;
          const key = `${item.label}-${item.href || 'current'}-${index}`;

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
                  <BreadcrumbPage>{item.label}</BreadcrumbPage>
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
