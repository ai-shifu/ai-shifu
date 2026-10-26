import { AdminBillingPageClient } from './AdminBillingPageClient';
import { resolveBillingTab, type BillingTab } from './billingTabs';

type AdminBillingPageProps = {
  searchParams: Promise<{
    tab?: string | string[] | undefined;
  }>;
};

function resolveInitialTab(tab: string | string[] | undefined): BillingTab {
  return resolveBillingTab(Array.isArray(tab) ? tab[0] : tab);
}

export default async function AdminBillingPage({
  searchParams,
}: AdminBillingPageProps) {
  const resolvedSearchParams = await searchParams;

  return (
    <AdminBillingPageClient
      initialTab={resolveInitialTab(resolvedSearchParams?.tab)}
    />
  );
}
