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
  const shouldRedirect = normalizedPath === '/' || normalizedPath === '/c';
  if (!shouldRedirect) {
    return false;
  }

  try {
    const currentUrl = new URL(window.location.href);
    const targetUrl = new URL(homeUrl, window.location.href);

    const currentPath = currentUrl.pathname.replace(/\/+$/, '') || '/';
    const targetPath = targetUrl.pathname.replace(/\/+$/, '') || '/';

    if (
      currentUrl.origin === targetUrl.origin &&
      (targetPath === '/c' || currentPath === targetPath)
    ) {
      return false;
    }
  } catch {
    return false;
  }

  window.location.replace(homeUrl);
  return true;
};
