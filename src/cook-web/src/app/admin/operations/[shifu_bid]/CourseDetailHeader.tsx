'use client';

import AdminTitle from '@/app/admin/components/AdminTitle';
import AdminOperationsBreadcrumb from '../AdminOperationsBreadcrumb';

type CourseDetailHeaderProps = {
  operationsLabel: string;
  detailLabel: string;
};

export default function CourseDetailHeader({
  operationsLabel,
  detailLabel,
}: CourseDetailHeaderProps) {
  return (
    <>
      <AdminOperationsBreadcrumb
        items={[
          {
            label: operationsLabel,
            href: '/admin/operations',
          },
          { label: detailLabel },
        ]}
      />
      <AdminTitle title={detailLabel} />
    </>
  );
}
