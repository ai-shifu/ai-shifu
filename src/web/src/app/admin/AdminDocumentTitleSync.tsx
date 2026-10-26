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

  // Keep route state in the dependency list so same-path query updates restore
  // the admin title after Next.js applies the root metadata title.
  useEffect(() => {
    if (document.title !== title) {
      document.title = title;
    }
  }, [pathname, searchParamsString, title]);

  return null;
};

export default AdminDocumentTitleSync;
