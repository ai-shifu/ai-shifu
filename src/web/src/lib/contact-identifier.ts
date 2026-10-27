import { isValidEmail } from '@/lib/validators';

import type { LoginIdentifierType } from '@/lib/resolve-preferred-login-identifier-type';

export const CONTACT_PHONE_PATTERN = /^\d{11}$/;

/**
 * Normalize an identifier the way the backend keys accounts and drafts:
 * emails are lowercased, phone numbers only lose surrounding whitespace.
 */
export const normalizeContactIdentifier = (
  identifierType: LoginIdentifierType,
  value: string,
): string => {
  const trimmed = value.trim();
  return identifierType === 'email' ? trimmed.toLowerCase() : trimmed;
};

/**
 * Validate an identifier the way the backend does: normalize first, so callers
 * never have to remember to normalize before asking.
 */
export const isValidContactIdentifier = (
  identifierType: LoginIdentifierType,
  value: string,
): boolean => {
  const normalized = normalizeContactIdentifier(identifierType, value);
  if (!normalized) {
    return false;
  }
  if (identifierType === 'email') {
    return isValidEmail(normalized);
  }
  return CONTACT_PHONE_PATTERN.test(normalized);
};
