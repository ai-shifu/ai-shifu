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
  context: { params: { lng: string } },
) {
  const { lng } = context.params;

  if (!isValidSegment(lng)) {
    return NextResponse.json(
      { error: 'Invalid language code' },
      { status: 400 },
    );
  }

  if (!localeCodes.includes(lng)) {
    return NextResponse.json({ error: 'Language not found' }, { status: 404 });
  }

  const langDir = path.join(I18N_ROOT, lng);

  let files: string[];
  try {
    files = await fs.readdir(langDir);
  } catch (_error) {
    void _error;
    return NextResponse.json({ error: 'Language not found' }, { status: 404 });
  }

  const translations: Record<string, unknown> = {};

  try {
    await Promise.all(
      files
        .filter(file => file.endsWith('.json'))
        .map(async file => {
          const namespace = path.basename(file, '.json');
          const filePath = path.join(langDir, file);

          const content = await fs.readFile(filePath, 'utf-8');
          translations[namespace] = JSON.parse(content);
        }),
    );
  } catch (_error) {
    void _error;
    return NextResponse.json(
      { error: 'Failed to load translations' },
      { status: 500 },
    );
  }

  return NextResponse.json(translations);
}
