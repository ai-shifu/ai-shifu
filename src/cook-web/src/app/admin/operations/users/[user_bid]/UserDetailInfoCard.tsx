'use client';

import type { ReactNode } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import UserInfoItem from './UserInfoItem';

type UserDetailInfoCardItem = {
  key: string;
  label: ReactNode;
  value?: string;
  onClick?: () => void;
  valueClassName?: string;
  valueAriaLabel?: string;
};

type UserDetailInfoCardProps = {
  title: string;
  items: UserDetailInfoCardItem[];
  emptyValue: string;
  columnsClassName?: string;
};

export default function UserDetailInfoCard({
  title,
  items,
  emptyValue,
  columnsClassName = 'grid gap-4 md:grid-cols-2 xl:grid-cols-4',
}: UserDetailInfoCardProps) {
  return (
    <Card className='shadow-sm'>
      <CardHeader className='pb-3'>
        <CardTitle className='text-base font-semibold'>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className={columnsClassName}>
          {items.map(item => (
            <UserInfoItem
              key={item.key}
              label={item.label}
              value={item.value}
              emptyValue={emptyValue}
              onClick={item.onClick}
              valueClassName={item.valueClassName}
              valueAriaLabel={item.valueAriaLabel}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
