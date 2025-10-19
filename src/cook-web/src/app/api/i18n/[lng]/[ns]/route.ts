import { NextResponse } from 'next/server';
import path from 'path';
import { promises as fs } from 'fs';

import { localeCodes } from '@/lib/i18n-locales';

const I18N_ROOT = path.join(process.cwd(), '../i18n');
const VALID_SEGMENT = /^[\w-]+$/;

export const dynamic = 'force-dynamic';

const isValidSegment = (value: string) => VALID_SEGMENT.test(value);

export async function GET(
  _request: Request,
  context: { params: { lng: string; ns: string } },
) {
  const { lng, ns } = context.params;

  if (!isValidSegment(lng) || !isValidSegment(ns)) {
    return NextResponse.json({ error: 'Invalid segment' }, { status: 400 });
  }

  if (!localeCodes.includes(lng)) {
    return NextResponse.json({ error: 'Language not found' }, { status: 404 });
  }

  const filePath = path.join(I18N_ROOT, lng, `${ns}.json`);

  try {
    const content = await fs.readFile(filePath, 'utf-8');
    return NextResponse.json(JSON.parse(content));
  } catch (_error) {
    void _error;
    return NextResponse.json({ error: 'Namespace not found' }, { status: 404 });
  }
}
