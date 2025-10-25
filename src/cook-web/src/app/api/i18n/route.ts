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
const VALID_SEGMENT = /^[\w.-]+$/;
const MULTI_SEPARATOR = /[+,]/;

const isValidSegment = (value: string | null): value is string =>
  typeof value === 'string' && VALID_SEGMENT.test(value);

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

const collectJsonFiles = async (root: string): Promise<string[]> => {
  try {
    const entries = await fs.readdir(root, { withFileTypes: true });
    const files: string[] = [];
    for (const entry of entries) {
      if (entry.name.startsWith('.')) {
        continue;
      }
      const entryPath = path.join(root, entry.name);
      if (entry.isDirectory()) {
        files.push(...(await collectJsonFiles(entryPath)));
      } else if (entry.isFile() && entry.name.endsWith('.json')) {
        files.push(entryPath);
      }
    }
    return files;
  } catch {
    return [];
  }
};

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const setNestedValue = (
  target: Record<string, unknown>,
  keyPath: string,
  value: unknown,
) => {
  if (!keyPath) {
    return;
  }

  const segments = keyPath.split('.');
  let current: Record<string, unknown> = target;

  segments.forEach((segment, index) => {
    if (!segment) {
      return;
    }

    if (index === segments.length - 1) {
      current[segment] = value;
      return;
    }

    const next = current[segment];
    if (!isPlainObject(next)) {
      current[segment] = {};
    }

    current = current[segment] as Record<string, unknown>;
  });
};

const extractTranslationPayload = (
  raw: Record<string, unknown>,
): Record<string, unknown> => {
  const payload: Record<string, unknown> = {};

  Object.entries(raw).forEach(([key, value]) => {
    if (key === '__namespace__' || key === '__flat__') {
      return;
    }

    payload[key] = value;
  });

  const flatSection = raw.__flat__;
  if (isPlainObject(flatSection)) {
    Object.entries(flatSection).forEach(([key, value]) => {
      if (typeof key === 'string') {
        setNestedValue(payload, key, value);
      }
    });
  }

  return payload;
};

const loadNamespaceResources = async (
  langDir: string,
): Promise<Map<string, Record<string, unknown>>> => {
  const files = await collectJsonFiles(langDir);
  const resources = new Map<string, Record<string, unknown>>();

  await Promise.all(
    files.map(async filePath => {
      const content = await readJsonIfExists<Record<string, unknown> | null>(
        filePath,
        null,
      );

      if (!content) {
        return;
      }

      const declaredNamespace = content.__namespace__;
      const namespace =
        typeof declaredNamespace === 'string' && declaredNamespace
          ? declaredNamespace
          : path
              .relative(langDir, filePath)
              .replace(/\\/g, '/')
              .replace(/\.json$/, '')
              .replace(/\//g, '.');

      resources.set(namespace, extractTranslationPayload(content));
    }),
  );

  return resources;
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
  const namespaceResources = await loadNamespaceResources(langDir);
  const availableNamespaces = metadata.namespaces?.length
    ? metadata.namespaces
    : Array.from(namespaceResources.keys()).sort();

  const namespacesParam =
    searchParams.get('ns') || searchParams.get('namespaces');
  const namespaces = parseNamespaces(namespacesParam, availableNamespaces);

  const includeMetadata = searchParams.get('meta') !== 'false';

  const translations: Record<string, unknown> = {};
  const missingNamespaces: string[] = [];

  namespaces.forEach(namespace => {
    if (!isValidSegment(namespace)) {
      return;
    }

    const resource = namespaceResources.get(namespace);
    if (resource) {
      translations[namespace] = resource;
      return;
    }

    missingNamespaces.push(namespace);
  });

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
