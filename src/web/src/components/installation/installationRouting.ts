import type { InstallationStatus } from '@/api/installation';

const isLoopbackHostname = (hostname: string): boolean => {
  const lower = hostname.toLowerCase();
  if (lower.includes(':')) {
    const address =
      lower.startsWith('[') && lower.endsWith(']') ? lower.slice(1, -1) : lower;
    if (!/^[0-9a-f:.]+$/.test(address)) return false;
    try {
      // Browser hostnames canonicalize expanded IPv6 literals to this form.
      const canonical = new URL(`http://[${address}]`).hostname;
      return (
        canonical === '[::1]' ||
        // The backend also recognizes IPv4-mapped 127/8 as loopback.
        /^\[::ffff:7f[0-9a-f]{2}:[0-9a-f]{1,4}\]$/.test(canonical)
      );
    } catch {
      return false;
    }
  }
  // Match the backend's trailing-dot normalization for DNS names and IPv4.
  const normalized = lower.replace(/\.+$/, '');
  if (normalized === 'localhost') return true;
  const octets = normalized.split('.');
  return (
    octets.length === 4 &&
    octets[0] === '127' &&
    octets.every(
      octet => /^(0|[1-9][0-9]{0,2})$/.test(octet) && Number(octet) <= 255,
    )
  );
};

export const isSecureInstallationOrigin = (
  location: Pick<Location, 'protocol' | 'hostname'>,
): boolean =>
  location.protocol === 'https:' ||
  (location.protocol === 'http:' && isLoopbackHostname(location.hostname));

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
