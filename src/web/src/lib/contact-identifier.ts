import { isValidEmail } from '@/lib/validators';

import type { LoginMethodDisplayMode } from '@/lib/resolve-login-method-display-mode';

export const CONTACT_PHONE_PATTERN = /^\d{11}$/;

/**
 * Normalize an identifier the way the backend keys accounts and drafts:
 * emails are lowercased, phone numbers only lose surrounding whitespace.
 */
export const normalizeContactIdentifier = (
  loginMethodDisplayMode: LoginMethodDisplayMode,
  value: string,
): string => {
  const trimmed = value.trim();
  return loginMethodDisplayMode === 'email' ? trimmed.toLowerCase() : trimmed;
};

/**
 * Validate an identifier the way the backend does: normalize first, so callers
 * never have to remember to normalize before asking.
 */
export const isValidContactIdentifier = (
  loginMethodDisplayMode: LoginMethodDisplayMode,
  value: string,
): boolean => {
  const normalized = normalizeContactIdentifier(loginMethodDisplayMode, value);
  if (!normalized) {
    return false;
  }
  if (loginMethodDisplayMode === 'email') {
    return isValidEmail(normalized);
  }
  return CONTACT_PHONE_PATTERN.test(normalized);
};
