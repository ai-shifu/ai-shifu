import React, { useContext } from 'react';
import defaultLocales from './locales';

type ILocales = {
  [k: string]: any;
};

type ILocaleContext = {
  locale?: string;
  locales?: ILocales;
};

const LocaleContext = React.createContext<ILocaleContext>(undefined!);
const DEFAULT_LOCALE = 'en-US';

const LocaleProvider: React.FC<ILocaleContext> = ({
  locale,
  locales,
  // @ts-expect-error EXPECT
  children,
}) => (
  <LocaleContext.Provider value={{ locale, locales }}>
    {children}
  </LocaleContext.Provider>
);

// @ts-expect-error EXPECT
LocaleProvider.defaultProps = {
  locale: DEFAULT_LOCALE,
};

const useLocale = (comp?: string, fallback?: any) => {
  const localeContext = useContext(LocaleContext);
  const { locale, locales } = localeContext || {};
  const defaultStrings =
    (locale && (defaultLocales as ILocales)[locale]) ||
    defaultLocales[DEFAULT_LOCALE];
  let strings = locales ? { ...defaultStrings, ...locales } : defaultStrings;

  if (!localeContext && fallback) {
    strings = fallback;
  } else if (comp) {
    strings = strings[comp] || {};
  }

  return {
    locale,
    trans: (key?: string) => (key ? strings[key] : strings),
  };
};

export { LocaleProvider, LocaleContext, useLocale };
