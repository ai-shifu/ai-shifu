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

export const isValidContactIdentifier = (
  contactMode: ContactMode,
  value: string,
): boolean => {
  if (!value) {
    return false;
  }
  if (contactMode === 'email') {
    return isValidEmail(value);
  }
  return CONTACT_PHONE_PATTERN.test(value);
};
