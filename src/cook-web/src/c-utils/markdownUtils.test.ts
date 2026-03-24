jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    t: () => 'Generating',
  },
}));

import {
  maskIncompleteImageToken,
  maskIncompleteVisualTokens,
} from './markdownUtils';

describe('markdownUtils visual token masking', () => {
  it('masks an incomplete markdown image token', () => {
    expect(
      maskIncompleteImageToken(
        'Before image ![cover](https://example.com/assets/cover',
      ),
    ).toBe('Before image ');
  });

  it('masks an incomplete html image tag', () => {
    expect(
      maskIncompleteImageToken(
        'Before image <img src="https://example.com/assets/cover',
      ),
    ).toBe('Before image ');
  });

  it('preserves a complete image token', () => {
    const text = 'Before image ![cover](https://example.com/assets/cover.png)';

    expect(maskIncompleteImageToken(text)).toBe(text);
  });

  it('keeps mermaid masking behavior before image masking', () => {
    const text = '```mermaid\nA-->B';

    expect(maskIncompleteVisualTokens(text)).toContain('Generating');
  });
});
