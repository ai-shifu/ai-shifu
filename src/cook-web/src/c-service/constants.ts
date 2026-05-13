import { localeEntries } from '@/lib/i18n-locales';

export const languages = localeEntries.map(([value, { label }]) => ({
  value,
  label,
}));
