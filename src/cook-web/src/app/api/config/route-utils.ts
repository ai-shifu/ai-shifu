const LOCAL_HOSTNAMES = new Set([
  'localhost',
  '127.0.0.1',
  '0.0.0.0',
  '::1',
  '[::1]',
]);

export const normalizeHost = (value: string): string => {
  return value.split(',')[0].trim().toLowerCase();
};

const getHostname = (host: string): string => {
  if (!host) {
    return '';
  }

  try {
    return new URL(`http://${host}`).hostname
      .toLowerCase()
      .replace(/^\[|\]$/g, '');
  } catch {
    if (host === '::1' || host.startsWith('::1:')) {
      return '::1';
    }
    return host.split(':')[0]?.toLowerCase() || '';
  }
};

export const shouldUseSameOriginApiBase = (
  configuredHost: string,
  requestHost: string,
): boolean => {
  const configuredHostname = getHostname(configuredHost);
  const requestHostname = getHostname(requestHost);

  if (
    LOCAL_HOSTNAMES.has(configuredHostname) ||
    LOCAL_HOSTNAMES.has(requestHostname)
  ) {
    return false;
  }

  return Boolean(requestHost && requestHost !== configuredHost);
};
