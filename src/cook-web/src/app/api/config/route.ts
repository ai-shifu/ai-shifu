import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    siteHost: process.env.SITE_HOST || 'http://localhost',
  });
}
