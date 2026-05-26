'use client';

import type { ReactNode } from 'react';
import UserDetailInfoCard from './UserDetailInfoCard';

type DetailInfoItem = {
  key: string;
  label: ReactNode;
  value?: string;
  onClick?: () => void;
  valueClassName?: string;
  valueAriaLabel?: string;
};

type UserDetailSummarySectionProps = {
  emptyValue: string;
  basicInfoTitle: string;
  basicInfoItems: DetailInfoItem[];
  overviewTitle: string;
  overviewItems: DetailInfoItem[];
};

export default function UserDetailSummarySection({
  emptyValue,
  basicInfoTitle,
  basicInfoItems,
  overviewTitle,
  overviewItems,
}: UserDetailSummarySectionProps) {
  return (
    <>
      <UserDetailInfoCard
        title={basicInfoTitle}
        items={basicInfoItems}
        emptyValue={emptyValue}
      />

      <UserDetailInfoCard
        title={overviewTitle}
        items={overviewItems}
        emptyValue={emptyValue}
      />
    </>
  );
}
