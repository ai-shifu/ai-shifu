type LocalesMetadata = {
  default: string;
  locales: Record<string, { label: string; rtl?: boolean }>;
  namespaces?: string[];
};

const rawMetadata = process.env.NEXT_PUBLIC_I18N_META;

const metadata: LocalesMetadata = rawMetadata
  ? (JSON.parse(rawMetadata) as LocalesMetadata)
  : { default: 'en-US', locales: {} };

// Hide pseudo-locale from any UI language lists by default
const hiddenLocales = new Set(['qps-ploc']);
export const localeEntries = Object.entries(metadata.locales).filter(
  ([code]) => !hiddenLocales.has(code),
) as [string, { label: string; rtl?: boolean }][];

export const localeCodes = localeEntries.map(([code]) => code);

export const defaultLocale = metadata.default;

export const getLocaleLabel = (code: string) =>
  metadata.locales[code]?.label ?? code;

export const namespaces = metadata.namespaces ?? [];

export default metadata;
