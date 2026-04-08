import * as billingTypes from './billing';

describe('billing type module', () => {
  test('stays importable for downstream billing pages and components', () => {
    expect(billingTypes).toEqual({});
  });
});
