import { NextResponse } from 'next/server';
import { environment } from '@/config/environment';
import { normalizeHost, shouldUseSameOriginApiBase } from './route-utils';

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
      if (shouldUseSameOriginApiBase(configuredHost, requestHost)) {
        return NextResponse.json({ apiBaseUrl: '' });
      }
    } catch {
      // Fall back to the configured value if the URL cannot be parsed.
    }
  }

  return NextResponse.json({ apiBaseUrl: configured });
}
