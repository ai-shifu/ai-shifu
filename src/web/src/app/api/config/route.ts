import { NextResponse } from 'next/server';
import { environment } from '@/config/environment';
import { resolveApiBaseUrlForHost } from './route-utils';

export async function GET(request: Request) {
  return NextResponse.json({
    apiBaseUrl: resolveApiBaseUrlForHost(
      environment.apiBaseUrl || '',
      request.headers.get('x-forwarded-host') ||
        request.headers.get('host') ||
        '',
    ),
  });
}
