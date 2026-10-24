import {
  formatPermissionContactSample,
  MAX_SHARED_PERMISSION_COUNT,
  validatePermissionContacts,
} from './permission-contacts';

const fullPermissionList = Array.from(
  { length: MAX_SHARED_PERMISSION_COUNT },
  (_, index) => ({ identifier: `existing-${index}@example.com` }),
);

describe('validatePermissionContacts', () => {
  test('normalizes email case and deduplicates in input order across separators', () => {
    expect(
      validatePermissionContacts({
        value:
          'SECOND@example.com; first@example.com\nsecond@EXAMPLE.com，third@example.com。',
        contactType: 'email',
        existingPermissions: [],
      }),
    ).toEqual({
      type: 'valid',
      contacts: [
        'second@example.com',
        'first@example.com',
        'third@example.com',
      ],
    });
  });

  test('extracts phones from labels and accepts any eleven-digit number', () => {
    expect(
      validatePermissionContacts({
        value:
          'Teacher:13800138000；other:01234567890,13800138000\n13900139000',
        contactType: 'phone',
        existingPermissions: [],
      }),
    ).toEqual({
      type: 'valid',
      contacts: ['13800138000', '01234567890', '13900139000'],
    });
  });

  test('reports invalid email candidates once and before owner, duplicate and limit checks', () => {
    expect(
      validatePermissionContacts({
        value: 'OWNER@example.com, BAD@host, bad@HOST; existing-0@example.com',
        contactType: 'email',
        existingPermissions: fullPermissionList,
        owner: { email: 'owner@example.com' },
      }),
    ).toEqual({ type: 'invalid', contacts: ['bad@host'] });
  });

  test('preserves invalid candidates even when an email substring can be extracted', () => {
    expect(
      validatePermissionContacts({
        value: '<TEACHER@example.com>',
        contactType: 'email',
        existingPermissions: [],
      }),
    ).toEqual({ type: 'invalid', contacts: ['<teacher@example.com>'] });
  });

  test('strips phone candidate formatting and deduplicates invalid values', () => {
    expect(
      validatePermissionContacts({
        value: '13800138000 short:123-45,12345; words',
        contactType: 'phone',
        existingPermissions: [],
      }),
    ).toEqual({ type: 'invalid', contacts: ['12345'] });
  });

  test.each([
    ['email', ''],
    ['email', ' \n '],
    ['email', 'no contact'],
    ['phone', ''],
    ['phone', 'no contact'],
    ['phone', '138-0013-8000'],
    ['phone', '138001380000'],
  ] as const)(
    'requires an extractable %s contact for %p',
    (contactType, value) => {
      expect(
        validatePermissionContacts({
          value,
          contactType,
          existingPermissions: fullPermissionList,
        }),
      ).toEqual({ type: 'required' });
    },
  );

  test('rejects the owner before duplicate and limit checks regardless of email case', () => {
    expect(
      validatePermissionContacts({
        value: 'EXISTING-0@example.com',
        contactType: 'email',
        existingPermissions: fullPermissionList,
        owner: { email: 'existing-0@EXAMPLE.com' },
      }),
    ).toEqual({ type: 'owner' });
  });

  test.each([
    { phone: '138-0013-8000', mobile: '13900139000' },
    { phone: null, mobile: '(138)00138000', user_mobile: '13900139000' },
    { phone: 123, mobile: undefined, user_mobile: '138 0013 8000' },
  ])('resolves the first string owner phone alias: %p', owner => {
    expect(
      validatePermissionContacts({
        value: '13800138000',
        contactType: 'phone',
        existingPermissions: [],
        owner,
      }),
    ).toEqual({ type: 'owner' });
  });

  test('does not fall back from an empty string owner phone to another alias', () => {
    expect(
      validatePermissionContacts({
        value: '13800138000',
        contactType: 'phone',
        existingPermissions: [],
        owner: { phone: '', mobile: '13800138000' },
      }),
    ).toEqual({ type: 'valid', contacts: ['13800138000'] });
  });

  test('reports existing emails in input order before checking the limit', () => {
    expect(
      validatePermissionContacts({
        value:
          'existing-2@example.com, NEW@example.com, EXISTING-0@EXAMPLE.COM',
        contactType: 'email',
        existingPermissions: fullPermissionList,
      }),
    ).toEqual({
      type: 'duplicate',
      contacts: ['existing-2@example.com', 'existing-0@example.com'],
    });
  });

  test('rejects existing phones without normalizing stored phone formatting', () => {
    expect(
      validatePermissionContacts({
        value: '13800138000,13900139000',
        contactType: 'phone',
        existingPermissions: [
          { identifier: '13800138000' },
          { identifier: '139-0013-9000' },
        ],
      }),
    ).toEqual({ type: 'duplicate', contacts: ['13800138000'] });
  });

  test('allows the last available slot and counts a repeated input only once', () => {
    expect(
      validatePermissionContacts({
        value: 'new@example.com,NEW@EXAMPLE.COM',
        contactType: 'email',
        existingPermissions: fullPermissionList.slice(1),
        owner: null,
      }),
    ).toEqual({ type: 'valid', contacts: ['new@example.com'] });
  });

  test('rejects a grant that exceeds the shared permission limit', () => {
    expect(
      validatePermissionContacts({
        value: 'new@example.com,another@example.com',
        contactType: 'email',
        existingPermissions: fullPermissionList.slice(1),
      }),
    ).toEqual({ type: 'limit' });
  });
});

describe('formatPermissionContactSample', () => {
  test('shows up to five contacts in order and marks only longer lists', () => {
    const contacts = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth'];
    expect(formatPermissionContactSample([])).toBe('');
    expect(formatPermissionContactSample(contacts.slice(0, 5))).toBe(
      'first, second, third, fourth, fifth',
    );
    expect(formatPermissionContactSample(contacts)).toBe(
      'first, second, third, fourth, fifth...',
    );
  });
});
