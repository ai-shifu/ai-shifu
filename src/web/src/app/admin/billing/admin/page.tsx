import { redirect } from 'next/navigation';

export default function LegacyAdminBillingConsolePage() {
  redirect('/admin/operations/billing');
}
