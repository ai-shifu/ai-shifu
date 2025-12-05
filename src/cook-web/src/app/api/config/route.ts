import { NextResponse } from 'next/server';
import { environment } from '@/config/environment';

export async function GET() {
  return NextResponse.json({
    apiBaseUrl: environment.apiBaseUrl,
  });
}
