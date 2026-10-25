import { InstallationAuth } from '@/components/installation/InstallationAuth';

export const dynamic = 'force-dynamic';

export default function InstallationSetupPage() {
  return <InstallationAuth surface='setup' />;
}
