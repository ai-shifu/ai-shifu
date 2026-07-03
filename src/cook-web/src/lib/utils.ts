import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const redirectToHomeUrlIfRootPath = (homeUrl?: string): boolean => {
  if (typeof window === 'undefined' || !homeUrl) {
    return false;
  }

  const pathname = window.location.pathname || '/';
  const normalizedPath = pathname === '/' ? '/' : pathname.replace(/\/+$/, '');

  const normalizedHome = homeUrl.replace(/\/+$/, '');
  if (normalizedHome === '' || normalizedHome === '/c') {
    return false;
  }

  if (
    normalizedHome ===
    (window.location.origin + (pathname === '/' ? '' : pathname)).replace(
      /\/+$/,
      '',
    )
  ) {
    return false;
  }

  const shouldRedirect = normalizedPath === '/' || normalizedPath === '/c';
  if (shouldRedirect) {
    window.location.replace(homeUrl);
    return true;
  }

  return false;
};
