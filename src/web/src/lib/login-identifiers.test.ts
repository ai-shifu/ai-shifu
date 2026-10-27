import {
  resolveLoginIdentifierTypes,
  selectSingleLoginIdentifierType,
  type LoginIdentifierType,
} from './login-identifiers';

describe('resolveLoginIdentifierTypes', () => {
  it.each([
    { methods: ['phone'], expected: ['phone'] },
    { methods: ['email'], expected: ['email'] },
    { methods: ['google'], expected: ['email'] },
    { methods: ['phone', 'google'], expected: ['phone', 'email'] },
    { methods: ['email', 'phone'], expected: ['phone', 'email'] },
    {
      methods: [' EMAIL ', 'Phone', 'google', 'phone', ''],
      expected: ['phone', 'email'],
    },
    { methods: ' Google, PHONE, email, ', expected: ['phone', 'email'] },
    { methods: ['password'], expected: [] },
    { methods: ['unknown', 'email'], expected: ['email'] },
    { methods: ['  ', 'unknown'], expected: [] },
    { methods: [], expected: [] },
    { methods: '', expected: [] },
    { methods: null, expected: [] },
    { methods: undefined, expected: [] },
  ])(
    'maps configured methods $methods to $expected',
    ({ methods, expected }) => {
      expect(resolveLoginIdentifierTypes(methods)).toEqual(expected);
    },
  );

  it('does not change the configuration array', () => {
    const methods = Object.freeze([' Google ', 'PHONE', 'email']);

    expect(resolveLoginIdentifierTypes(methods)).toEqual(['phone', 'email']);
    expect(methods).toEqual([' Google ', 'PHONE', 'email']);
  });
});

describe('selectSingleLoginIdentifierType', () => {
  const defaults = ['phone', 'email', 'google', ' EMAIL ', '', null, undefined];

  it.each(defaults)(
    'keeps a sole phone field with default %s',
    defaultMethod => {
      expect(selectSingleLoginIdentifierType(['phone'], defaultMethod)).toBe(
        'phone',
      );
    },
  );

  it.each(defaults)(
    'keeps a sole email field with default %s',
    defaultMethod => {
      expect(selectSingleLoginIdentifierType(['email'], defaultMethod)).toBe(
        'email',
      );
    },
  );

  it.each(
    [
      { defaultMethod: 'phone', expected: 'phone' },
      { defaultMethod: 'email', expected: 'email' },
      { defaultMethod: 'google', expected: 'phone' },
      { defaultMethod: ' EMAIL ', expected: 'email' },
      { defaultMethod: '', expected: 'phone' },
      { defaultMethod: null, expected: 'phone' },
      { defaultMethod: undefined, expected: 'phone' },
    ].flatMap(({ defaultMethod, expected }) => [
      {
        identifierTypes: ['phone', 'email'] as LoginIdentifierType[],
        defaultMethod,
        expected,
      },
      { identifierTypes: [] as LoginIdentifierType[], defaultMethod, expected },
    ]),
  )(
    'preserves the single-field fallback for $identifierTypes with default $defaultMethod',
    ({ identifierTypes, defaultMethod, expected }) => {
      expect(
        selectSingleLoginIdentifierType(identifierTypes, defaultMethod),
      ).toBe(expected);
    },
  );

  it('allows a multi-type interface to retain both types independently of selection', () => {
    const identifierTypes = resolveLoginIdentifierTypes('phone,google');

    expect(selectSingleLoginIdentifierType(identifierTypes, 'google')).toBe(
      'phone',
    );
    expect(identifierTypes).toEqual(['phone', 'email']);
  });
});
