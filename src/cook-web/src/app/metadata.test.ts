import { metadata } from './metadata';

describe('app metadata', () => {
  test('uses a neutral loading title before route title resolves', () => {
    expect(metadata.title).toBe('Loading...');
  });
});
