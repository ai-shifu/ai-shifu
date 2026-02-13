jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    t: (key: string) => key,
  },
}));

import { unwrapVisualCodeFence } from '@/c-utils/markdownUtils';

describe('unwrapVisualCodeFence', () => {
  it('unwraps svg fenced blocks', () => {
    const input = [
      'before',
      '```svg',
      '<svg><text>v</text></svg>',
      '```',
      'after',
    ].join('\n');

    const output = unwrapVisualCodeFence(input);

    expect(output).toContain('<svg><text>v</text></svg>');
    expect(output).not.toContain('```svg');
    expect(output).not.toContain('\n```\n');
  });

  it('unwraps html fenced blocks when content is visual markup', () => {
    const input = [
      '```html',
      '<div><table><tr><td>A</td></tr></table></div>',
      '```',
    ].join('\n');

    const output = unwrapVisualCodeFence(input);

    expect(output).toBe('<div><table><tr><td>A</td></tr></table></div>');
  });

  it('unwraps html fenced blocks with doctype and html root', () => {
    const input = [
      '```html',
      '<!DOCTYPE html>',
      '<html lang="zh-CN">',
      '<head><meta charset="UTF-8"></head>',
      '<body><div>hello</div></body>',
      '</html>',
      '```',
    ].join('\n');

    const output = unwrapVisualCodeFence(input);

    expect(output).toContain('<!DOCTYPE html>');
    expect(output).toContain('<html lang="zh-CN">');
    expect(output).not.toContain('```html');
  });

  it('normalizes escaped newlines and quotes inside visual html fences', () => {
    const input = [
      '```html',
      '\\n<!DOCTYPE html>\\n<html lang=\\"zh-CN\\">\\n<body>ok</body>\\n</html>',
      '```',
    ].join('\n');

    const output = unwrapVisualCodeFence(input);

    expect(output).toContain('<!DOCTYPE html>');
    expect(output).toContain('<html lang="zh-CN">');
    expect(output).not.toContain('\\n');
    expect(output).not.toContain('\\"');
  });

  it('unwraps no-language fenced blocks when body starts with visual root tag', () => {
    const input = [
      '```',
      '<svg><rect width="10" height="10"/></svg>',
      '```',
    ].join('\n');

    const output = unwrapVisualCodeFence(input);

    expect(output).toBe('<svg><rect width="10" height="10"/></svg>');
  });

  it('keeps regular code fences unchanged', () => {
    const input = ['```python', 'print("hello")', '```'].join('\n');

    const output = unwrapVisualCodeFence(input);

    expect(output).toBe(input);
  });

  it('keeps mermaid fences unchanged', () => {
    const input = ['```mermaid', 'graph TD', 'A-->B', '```'].join('\n');

    const output = unwrapVisualCodeFence(input);

    expect(output).toBe(input);
  });

  it('keeps html fences unchanged when not visual root markup', () => {
    const input = ['```html', '<span>inline</span>', '```'].join('\n');

    const output = unwrapVisualCodeFence(input);

    expect(output).toBe(input);
  });
});
