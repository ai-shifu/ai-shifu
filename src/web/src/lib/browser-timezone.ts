export const getBrowserTimeZone = (): string => {
  if (
    typeof window === 'undefined' ||
    typeof Intl === 'undefined' ||
    !Intl.DateTimeFormat
  ) {
    return '';
  }

  return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
};
