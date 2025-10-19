import { NextResponse } from 'next/server';

import localesMetadata from '@/lib/i18n-locales';

export const dynamic = 'force-static';

export async function GET() {
  return NextResponse.json(localesMetadata);
}
