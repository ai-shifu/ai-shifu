import React from 'react';
import { cn } from '@/lib/utils';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';

export type ChartCardProps = {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  contentClassName?: string;
  children: React.ReactNode;
};

export default function ChartCard({
  title,
  description,
  actions,
  className,
  contentClassName,
  children,
}: ChartCardProps) {
  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardHeader className='flex flex-row items-start justify-between gap-3 pb-3'>
        <div className='min-w-0'>
          <CardTitle className='text-base font-semibold leading-6'>
            {title}
          </CardTitle>
          {description ? (
            <CardDescription className='mt-1'>{description}</CardDescription>
          ) : null}
        </div>
        {actions ? <div className='shrink-0'>{actions}</div> : null}
      </CardHeader>
      <CardContent className={cn('pt-0', contentClassName)}>
        {children}
      </CardContent>
    </Card>
  );
}
