import { NextResponse } from 'next/server';
import { environment } from '@/config/environment';
import { normalizeHost, shouldUseSameOriginApiBase } from './route-utils';

const LOCALHOST_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

const normalizeHostname = (host: string) => {
  const trimmed = host.trim().toLowerCase();
  if (!trimmed) {
    return '';
  }
  if (trimmed.startsWith('[')) {
    const closingBracket = trimmed.indexOf(']');
    return closingBracket >= 0 ? trimmed.slice(0, closingBracket + 1) : trimmed;
  }
  return trimmed.split(':')[0] || '';
};

const isLocalDevHost = (host: string) => {
  return LOCALHOST_HOSTS.has(normalizeHostname(host));
};

export async function GET(request: Request) {
  const configured = environment.apiBaseUrl || '';

  // On a custom (white-label) domain the request host differs from the
  // configured API origin. Returning the absolute main-domain URL would make
  // the browser issue cross-origin API calls that are blocked by CORS, so
  // return an empty base and let the client use same-origin relative requests
  // (the custom-domain ingress already routes /api to the backend). The main
  // domain keeps its configured absolute base unchanged.
  if (configured) {
    try {
      const configuredHost = new URL(configured).host.toLowerCase();
      const requestHost = normalizeHost(
        request.headers.get('x-forwarded-host') ||
          request.headers.get('host') ||
          '',
      );
      // Local frontend dev commonly runs on :3000 while the API runs on :8080.
      // Treat localhost-to-localhost as the same environment so the browser can
      // still target the explicit backend origin instead of falling back to the
      // Next app's own /api namespace, which does not proxy every backend route.
      if (isLocalDevHost(requestHost) && isLocalDevHost(configuredHost)) {
        return NextResponse.json({ apiBaseUrl: configured });
      }
      if (shouldUseSameOriginApiBase(configuredHost, requestHost)) {
        return NextResponse.json({ apiBaseUrl: '' });
      }
    } catch {
      // Fall back to the configured value if the URL cannot be parsed.
    }
  }

  return NextResponse.json({ apiBaseUrl: configured });
}
