import { isValidEmail } from '@/lib/validators';

import type { ContactMode } from '@/lib/resolve-contact-mode';

export const CONTACT_PHONE_PATTERN = /^\d{11}$/;

/**
 * Normalize an identifier the way the backend keys accounts and drafts:
 * emails are lowercased, phone numbers only lose surrounding whitespace.
 */
export const normalizeContactIdentifier = (
  contactMode: ContactMode,
  value: string,
): string => {
  const trimmed = value.trim();
  return contactMode === 'email' ? trimmed.toLowerCase() : trimmed;
};

/**
 * Validate an identifier the way the backend does: normalize first, so callers
 * never have to remember to normalize before asking.
 */
export const isValidContactIdentifier = (
  contactMode: ContactMode,
  value: string,
): boolean => {
  const normalized = normalizeContactIdentifier(contactMode, value);
  if (!normalized) {
    return false;
  }
  if (contactMode === 'email') {
    return isValidEmail(normalized);
  }
  return CONTACT_PHONE_PATTERN.test(normalized);
};
