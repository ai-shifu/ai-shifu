import type { InstallationStatus } from '@/api/installation';

export const isSecureInstallationOrigin = (
  location: Pick<Location, 'protocol' | 'hostname'>,
): boolean =>
  location.protocol === 'https:' ||
  (location.protocol === 'http:' &&
    ['localhost', '127.0.0.1', '[::1]', '::1'].includes(
      location.hostname.toLowerCase(),
    ));

export const getAdminEntryPath = (
  status: InstallationStatus,
  currentPath: string,
): string => {
  if (status.setup_required) return '/setup';
  const loginPath = status.local_admin_login_enabled
    ? '/admin-login'
    : '/login';
  return `${loginPath}?redirect=${encodeURIComponent(currentPath)}`;
};

export const getLocalAdminRedirect = (search: string): string => {
  const redirect = new URLSearchParams(search).get('redirect');
  return redirect && /^\/admin(?:[/?#]|$)/.test(redirect) ? redirect : '/admin';
};
