import localesMetadata from '../../../i18n/locales.json';

type LocalesMetadata = {
  default: string;
  locales: Record<string, { label: string; rtl?: boolean }>;
  namespaces?: string[];
};

const metadata = localesMetadata as LocalesMetadata;

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
