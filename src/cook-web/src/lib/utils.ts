import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const normalizePathname = (value: string): string => {
  if (!value) {
    return '/';
  }
  return value === '/' ? '/' : value.replace(/\/+$/, '') || '/';
};

export const redirectToHomeUrlIfRootPath = (homeUrl?: string): boolean => {
  if (typeof window === 'undefined' || !homeUrl) {
    return false;
  }

  const pathname = window.location.pathname || '/';
  const normalizedPath = normalizePathname(pathname);
  const shouldRedirect = normalizedPath === '/' || normalizedPath === '/c';

  if (!shouldRedirect) {
    return false;
  }

  try {
    const targetUrl = new URL(homeUrl, window.location.origin);
    const normalizedTargetPath = normalizePathname(targetUrl.pathname);
    const currentSearch = window.location.search || '';
    const currentHash = window.location.hash || '';
    const isSameLocation =
      targetUrl.origin === window.location.origin &&
      normalizedTargetPath === normalizedPath &&
      targetUrl.search === currentSearch &&
      targetUrl.hash === currentHash;

    if (isSameLocation) {
      return false;
    }
  } catch {
    if (normalizePathname(homeUrl) === normalizedPath) {
      return false;
    }
  }

  window.location.replace(homeUrl);
  return true;
};
