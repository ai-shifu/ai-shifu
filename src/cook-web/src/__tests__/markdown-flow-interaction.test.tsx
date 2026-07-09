import { adaptMarkdownFlowInteractionForRender } from '@/c-utils/markdown-flow-interaction';

describe('adaptMarkdownFlowInteractionForRender', () => {
  it('adapts a variable-free ellipsis interaction into input markup', () => {
    expect(adaptMarkdownFlowInteractionForRender('?[...你叫什么名字]')).toBe(
      '<custom-variable placeholder="你叫什么名字"></custom-variable>',
    );
  });

  it('escapes the prompt when adapting it into an HTML attribute', () => {
    expect(
      adaptMarkdownFlowInteractionForRender('?[...输入 "昵称" & <个人标签>]'),
    ).toBe(
      '<custom-variable placeholder="输入 &quot;昵称&quot; &amp; &lt;个人标签&gt;"></custom-variable>',
    );
  });

  it.each([
    '?[继续]',
    '?[%{{name}}...你叫什么名字]',
    '?[...]',
    '示例：?[...你叫什么名字]',
    '?[...你叫什么名字]\n?[继续]',
  ])('keeps non-target interaction content unchanged: %s', content => {
    expect(adaptMarkdownFlowInteractionForRender(content)).toBe(content);
  });
});
