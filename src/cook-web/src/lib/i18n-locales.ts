type LocalesMetadata = {
  default: string;
  locales: Record<string, { label: string; rtl?: boolean }>;
  namespaces?: string[];
};

const rawMetadata = process.env.NEXT_PUBLIC_I18N_META;

const fallbackMetadata: LocalesMetadata = {
  default: 'en-US',
  locales: {},
  namespaces: [],
};

const parseMetadata = (raw: string | undefined): LocalesMetadata => {
  if (!raw) {
    return fallbackMetadata;
  }

  try {
    return JSON.parse(raw) as LocalesMetadata;
  } catch {
    return fallbackMetadata;
  }
};

const metadata = parseMetadata(rawMetadata);

export const localeEntries = Object.entries(metadata.locales) as [
  string,
  { label: string; rtl?: boolean },
][];

export const localeCodes = localeEntries.map(([code]) => code);

export const defaultLocale = metadata.default;

export const getLocaleLabel = (code: string) =>
  metadata.locales[code]?.label ?? code;

export const namespaces = metadata.namespaces ?? [];

export default metadata;
