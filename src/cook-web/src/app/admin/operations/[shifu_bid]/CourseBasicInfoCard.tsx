'use client';

import type { ReactNode } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';

type BasicInfoItem = {
  label: string;
  value: ReactNode;
};

type CourseBasicInfoCardProps = {
  title: string;
  items: BasicInfoItem[];
};

export default function CourseBasicInfoCard({
  title,
  items,
}: CourseBasicInfoCardProps) {
  return (
    <Card>
      <CardHeader className='pb-4'>
        <CardTitle className='text-base font-semibold tracking-normal'>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className='grid gap-4 md:grid-cols-2 xl:grid-cols-3'>
          {items.map(item => (
            <div
              key={item.label}
              className='space-y-1'
            >
              <dt className='text-sm text-muted-foreground'>{item.label}</dt>
              <dd className='text-sm text-foreground'>{item.value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
