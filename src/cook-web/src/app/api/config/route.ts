import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    siteHost: process.env.SITE_HOST || process.env.NEXT_PUBLIC_BASEURL || process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:8081',
  });
}
