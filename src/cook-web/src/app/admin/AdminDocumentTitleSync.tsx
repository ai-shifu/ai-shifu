'use client';

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';

type AdminDocumentTitleSyncProps = {
  title: string;
};

const AdminDocumentTitleSync = ({ title }: AdminDocumentTitleSyncProps) => {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchParamsString = searchParams?.toString() || '';

  useEffect(() => {
    document.title = title;
  }, [pathname, searchParamsString, title]);

  return null;
};

export default AdminDocumentTitleSync;
