import { NextResponse } from 'next/server';
import path from 'path';
import { promises as fs } from 'fs';

const resolveI18nRoot = async (): Promise<string> => {
  const envRoot = process.env.I18N_ROOT;
  const candidates = [
    envRoot ? path.resolve(envRoot) : undefined,
    path.join(process.cwd(), 'src/i18n'),
    path.join(process.cwd(), '../i18n'),
    path.join(process.cwd(), '../../i18n'),
    '/app/src/i18n',
    '/i18n',
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch {
      // continue
    }
  }

  throw new Error(
    `Unable to locate shared i18n directory. Checked: ${candidates.join(', ')}`,
  );
};
const VALID_SEGMENT = /^[\w-]+$/;
const MULTI_SEPARATOR = /[+,]/;

const isValidSegment = (value: string | null): value is string =>
  Boolean(value) && VALID_SEGMENT.test(value);

const parseNamespaces = (raw: string | null, fallback: string[]) => {
  if (!raw) {
    return fallback;
  }

  return raw
    .split(MULTI_SEPARATOR)
    .map(segment => segment.trim())
    .filter(Boolean);
};

const readJsonIfExists = async <T>(
  filePath: string,
  fallback: T,
): Promise<T> => {
  try {
    const content = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(content) as T;
  } catch {
    return fallback;
  }
};

const listDirectories = async (root: string): Promise<string[]> => {
  try {
    const entries = await fs.readdir(root, { withFileTypes: true });
    return entries
      .filter(entry => entry.isDirectory() && !entry.name.startsWith('.'))
      .map(entry => entry.name);
  } catch {
    return [];
  }
};

const listNamespaces = async (langDir: string): Promise<string[]> => {
  try {
    const entries = await fs.readdir(langDir, { withFileTypes: true });
    return entries
      .filter(
        entry =>
          entry.isFile() &&
          entry.name.endsWith('.json') &&
          entry.name !== 'langName.json',
      )
      .map(entry => entry.name.replace(/\.json$/, ''))
      .sort();
  } catch {
    return [];
  }
};

export async function GET(request: Request) {
  const url = new URL(request.url);
  const searchParams = url.searchParams;

  let i18nRoot: string;
  try {
    i18nRoot = await resolveI18nRoot();
  } catch (error) {
    return NextResponse.json(
      { error: 'Translation root not found', details: String(error) },
      { status: 500 },
    );
  }

  const metadataPath = path.join(i18nRoot, 'locales.json');
  const metadata = await readJsonIfExists(metadataPath, {
    default: 'en-US',
    locales: {},
    namespaces: [],
  });

  const localeDirs = await listDirectories(i18nRoot);

  const requestedLanguage = searchParams.get('lng');
  const language = isValidSegment(requestedLanguage)
    ? requestedLanguage
    : metadata.default || localeDirs[0];

  if (!language || !localeDirs.includes(language)) {
    return NextResponse.json({ error: 'Language not found' }, { status: 404 });
  }

  const langDir = path.join(i18nRoot, language);
  const availableNamespaces = metadata.namespaces?.length
    ? metadata.namespaces
    : await listNamespaces(langDir);

  const namespacesParam =
    searchParams.get('ns') || searchParams.get('namespaces');
  const namespaces = parseNamespaces(namespacesParam, availableNamespaces);

  const includeMetadata = searchParams.get('meta') !== 'false';

  const translations: Record<string, unknown> = {};
  const missingNamespaces: string[] = [];

  await Promise.all(
    namespaces.map(async namespace => {
      if (!isValidSegment(namespace)) {
        return;
      }

      const filePath = path.join(langDir, `${namespace}.json`);
      try {
        const content = await fs.readFile(filePath, 'utf-8');
        translations[namespace] = JSON.parse(content);
      } catch {
        missingNamespaces.push(namespace);
      }
    }),
  );

  if (!includeMetadata) {
    return NextResponse.json(translations);
  }

  return NextResponse.json({
    metadata,
    language,
    namespaces,
    translations,
    missingNamespaces,
  });
}
