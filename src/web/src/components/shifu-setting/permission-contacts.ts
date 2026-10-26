import type { ContactMode } from '@/lib/resolve-contact-mode';
import { isValidEmail } from '@/lib/validators';

export const MAX_SHARED_PERMISSION_COUNT = 10;
const INVALID_CONTACT_SAMPLE_LIMIT = 5;
const PERMISSION_PHONE_PATTERN = /^\d{11}$/;
const PHONE_EXTRACT_PATTERN = /(?:^|\D)(\d{11})(?!\d)/g;
const PHONE_TOKEN_PATTERN = /\d{11}/;
const PHONE_TOKEN_SPLIT_PATTERN = /[\s,;\n\uFF0C\uFF1B]+/;
const EMAIL_EXTRACT_PATTERN = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const EMAIL_CANDIDATE_PATTERN = /[^\s,\uFF0C;\uFF1B]+@[^\s,\uFF0C;\uFF1B]+/g;

type PermissionContactOwner = {
  email?: unknown;
  phone?: unknown;
  mobile?: unknown;
  user_mobile?: unknown;
};

type PermissionContactsInput = {
  value: string;
  contactType: ContactMode;
  existingPermissions: ReadonlyArray<{ identifier: string }>;
  owner?: PermissionContactOwner | null;
};

type PermissionContactsResult =
  | { type: 'valid'; contacts: string[] }
  | { type: 'invalid' | 'duplicate'; contacts: string[] }
  | { type: 'required' | 'owner' | 'limit' };

const unique = (items: string[]): string[] => Array.from(new Set(items));

const normalizeEmailCandidate = (value: string): string =>
  value.replace(/^[,\uFF0C;\uFF1B.\u3002]+|[,\uFF0C;\uFF1B.\u3002]+$/g, '');

const parseContacts = (value: string, contactType: ContactMode) => {
  if (!value.trim()) {
    return { contacts: [], invalidContacts: [] };
  }

  if (contactType === 'phone') {
    const matches = Array.from(value.matchAll(PHONE_EXTRACT_PATTERN)).map(
      match => match[1],
    );
    const contacts = unique(matches).filter(phone =>
      PERMISSION_PHONE_PATTERN.test(phone),
    );
    const tokens = value
      .split(PHONE_TOKEN_SPLIT_PATTERN)
      .filter(token => token.length > 0);
    const invalidContacts = unique(
      tokens
        .filter(token => /\d/.test(token) && !PHONE_TOKEN_PATTERN.test(token))
        .map(token => token.replace(/\D/g, ''))
        .filter(
          candidate =>
            candidate.length > 0 && !PERMISSION_PHONE_PATTERN.test(candidate),
        ),
    );
    return { contacts, invalidContacts };
  }

  const emailMatches = Array.from(value.matchAll(EMAIL_EXTRACT_PATTERN)).map(
    match => match[0].toLowerCase(),
  );
  const contacts = unique(emailMatches);
  const candidateMatches = Array.from(
    value.matchAll(EMAIL_CANDIDATE_PATTERN),
  ).map(match => normalizeEmailCandidate(match[0]).toLowerCase());
  const invalidContacts = unique(candidateMatches).filter(
    candidate => candidate && !isValidEmail(candidate),
  );
  return { contacts, invalidContacts };
};

export const formatPermissionContactSample = (contacts: string[]): string => {
  const sample = contacts.slice(0, INVALID_CONTACT_SAMPLE_LIMIT).join(', ');
  return contacts.length > INVALID_CONTACT_SAMPLE_LIMIT
    ? `${sample}...`
    : sample;
};

export const validatePermissionContacts = ({
  value,
  contactType,
  existingPermissions,
  owner,
}: PermissionContactsInput): PermissionContactsResult => {
  const { contacts, invalidContacts } = parseContacts(value, contactType);
  // Preserve the first reported problem when several validation rules fail.
  if (invalidContacts.length > 0) {
    return { type: 'invalid', contacts: invalidContacts };
  }
  if (contacts.length === 0) {
    return { type: 'required' };
  }

  const normalizedExisting = new Set(
    existingPermissions.map(item =>
      contactType === 'email'
        ? (item.identifier || '').toLowerCase()
        : item.identifier || '',
    ),
  );
  const normalizedContacts = contacts.map(contact =>
    contactType === 'email' ? contact.toLowerCase() : contact,
  );
  const ownerEmail =
    typeof owner?.email === 'string' ? owner.email.toLowerCase() : '';
  const ownerPhoneCandidate =
    typeof owner?.phone === 'string'
      ? owner.phone
      : typeof owner?.mobile === 'string'
        ? owner.mobile
        : typeof owner?.user_mobile === 'string'
          ? owner.user_mobile
          : '';
  const ownerPhone = ownerPhoneCandidate.replace(/\D/g, '');
  const ownerContact = contactType === 'email' ? ownerEmail : ownerPhone;
  if (ownerContact && normalizedContacts.includes(ownerContact)) {
    return { type: 'owner' };
  }

  const existingContacts = contacts.filter((contact, index) =>
    normalizedExisting.has(normalizedContacts[index]),
  );
  const newContacts = contacts.filter(
    (_contact, index) => !normalizedExisting.has(normalizedContacts[index]),
  );
  if (existingContacts.length > 0) {
    return { type: 'duplicate', contacts: existingContacts };
  }
  if (
    existingPermissions.length + newContacts.length >
    MAX_SHARED_PERMISSION_COUNT
  ) {
    return { type: 'limit' };
  }
  return { type: 'valid', contacts: newContacts };
};
