'use client';

import Loading from '@/components/loading';
import useOperatorGuard from '../useOperatorGuard';
import { AdminBillingOperationsConsole } from './AdminBillingOperationsConsole';

export default function AdminBillingOperationsPage() {
  const { isReady } = useOperatorGuard();

  if (!isReady) {
    return <Loading />;
  }

  return <AdminBillingOperationsConsole />;
}
