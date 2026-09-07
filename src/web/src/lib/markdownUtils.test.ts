jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    t: () => 'Generating',
  },
}));

import { mergeStreamingMarkdownText } from './markdownUtils';

describe('mergeStreamingMarkdownText', () => {
  it('appends delta content to the existing streamed text', () => {
    expect(mergeStreamingMarkdownText('First text', '\nSecond text')).toBe(
      'First text\nSecond text',
    );
  });

  it('accepts cumulative snapshots without duplicating the previous text', () => {
    expect(
      mergeStreamingMarkdownText('First text', 'First text\nSecond text'),
    ).toBe('First text\nSecond text');
  });

  it('keeps the previous text when the incoming chunk is empty', () => {
    expect(mergeStreamingMarkdownText('First text', '')).toBe('First text');
  });
});
