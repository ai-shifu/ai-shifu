import { InstallationAuth } from '@/components/installation/InstallationAuth';

export const dynamic = 'force-dynamic';

export default function LocalAdministratorLoginPage() {
  return <InstallationAuth surface='local_login' />;
}
