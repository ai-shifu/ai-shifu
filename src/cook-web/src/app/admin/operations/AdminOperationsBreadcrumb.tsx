'use client';

import AdminBreadcrumb, {
  type AdminBreadcrumbItem,
} from '@/app/admin/components/AdminBreadcrumb';

type AdminOperationsBreadcrumbItem = AdminBreadcrumbItem;

type AdminOperationsBreadcrumbProps = {
  items: AdminOperationsBreadcrumbItem[];
  className?: string;
};

export default function AdminOperationsBreadcrumb({
  items,
  className,
}: AdminOperationsBreadcrumbProps) {
  return (
    <AdminBreadcrumb
      items={items}
      className={className}
    />
  );
}
