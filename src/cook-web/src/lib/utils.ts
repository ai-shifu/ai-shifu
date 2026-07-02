import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const redirectToHomeUrlIfRootPath = (homeUrl?: string): boolean => {
  const trimmedHomeUrl = homeUrl?.trim();
  if (typeof window === 'undefined' || !trimmedHomeUrl) {
    return false;
  }

  const currentUrl = new URL(window.location.href);
  const normalizedPath =
    currentUrl.pathname === '/'
      ? '/'
      : currentUrl.pathname.replace(/\/+$/, '');
  const shouldRedirect = normalizedPath === '/' || normalizedPath === '/c';

  if (!shouldRedirect) {
    return false;
  }

  const targetUrl = new URL(trimmedHomeUrl, currentUrl.origin);
  const normalizedTargetPath =
    targetUrl.pathname === '/'
      ? '/'
      : targetUrl.pathname.replace(/\/+$/, '');
  const isSameUrl =
    targetUrl.origin === currentUrl.origin &&
    normalizedTargetPath === normalizedPath &&
    targetUrl.search === currentUrl.search &&
    targetUrl.hash === currentUrl.hash;

  if (isSameUrl) {
    return false;
  }

  const sameOriginTarget =
    targetUrl.origin === currentUrl.origin
      ? `${targetUrl.pathname}${targetUrl.search}${targetUrl.hash}`
      : targetUrl.toString();

  window.location.replace(sameOriginTarget);
  return true;
};
