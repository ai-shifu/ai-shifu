import { NextResponse } from 'next/server';
import { environment } from '@/config/environment';

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
      const requestHost = (
        request.headers.get('x-forwarded-host') ||
        request.headers.get('host') ||
        ''
      )
        .split(',')[0]
        .trim()
        .toLowerCase();
      // Local development serves the frontend on localhost while pointing at a
      // remote API (e.g. dev.sh sets NEXT_PUBLIC_API_BASE_URL to a remote
      // host). There is no same-origin /api proxy on localhost, so always
      // return the configured absolute base instead of treating the host
      // mismatch as a white-label domain.
      // Parse the host as an authority so the port is stripped correctly for
      // both IPv4 and bracketed IPv6 forms (e.g. "[::1]:3000"). A bare "::1"
      // is not a valid authority, so fall back to a plain split.
      let requestHostname: string;
      try {
        requestHostname = new URL(`http://${requestHost}`).hostname.toLowerCase();
      } catch {
        requestHostname = requestHost.split(':')[0];
      }
      const isLocalhost =
        requestHostname === 'localhost' ||
        requestHostname === '127.0.0.1' ||
        requestHostname === '0.0.0.0' ||
        requestHostname === '::1' ||
        requestHostname === '[::1]';
      if (!isLocalhost && requestHost && requestHost !== configuredHost) {
        return NextResponse.json({ apiBaseUrl: '' });
      }
    } catch {
      // Fall back to the configured value if the URL cannot be parsed.
    }
  }

  return NextResponse.json({ apiBaseUrl: configured });
}
