import { adaptMarkdownFlowInteractionForRender } from '@/c-utils/markdown-flow-interaction';

describe('adaptMarkdownFlowInteractionForRender', () => {
  it('adapts a variable-free ellipsis interaction into input markup', () => {
    expect(adaptMarkdownFlowInteractionForRender('?[...你叫什么名字]')).toBe(
      '<custom-variable placeholder="你叫什么名字"></custom-variable>',
    );
  });

  it('keeps anonymous multi-select options separate from the text input', () => {
    expect(
      adaptMarkdownFlowInteractionForRender(
        '?[搜索工具 || 效率助手 || 数字员工 || 组织重构力量 || ...其他角色（请简要补充）]',
      ),
    ).toBe(
      '<custom-variable placeholder="其他角色（请简要补充）" data-button-texts="[&quot;搜索工具&quot;,&quot;效率助手&quot;,&quot;数字员工&quot;,&quot;组织重构力量&quot;]" data-button-values="[&quot;搜索工具&quot;,&quot;效率助手&quot;,&quot;数字员工&quot;,&quot;组织重构力量&quot;]" data-is-multi-select="true"></custom-variable>',
    );
  });

  it('adapts a variable-free multi-select into selectable options', () => {
    expect(
      adaptMarkdownFlowInteractionForRender(
        '?[ 搜索工具 || 效率助手 || 数字员工 || 组织重构力量 ]',
      ),
    ).toBe(
      '<custom-variable data-button-texts="[&quot;搜索工具&quot;,&quot;效率助手&quot;,&quot;数字员工&quot;,&quot;组织重构力量&quot;]" data-button-values="[&quot;搜索工具&quot;,&quot;效率助手&quot;,&quot;数字员工&quot;,&quot;组织重构力量&quot;]" data-is-multi-select="true"></custom-variable>',
    );
  });

  it('keeps anonymous single-select options separate from the text input', () => {
    expect(adaptMarkdownFlowInteractionForRender('?[选项 | ...输入]')).toBe(
      '<custom-variable placeholder="输入" data-button-texts="[&quot;选项&quot;]" data-button-values="[&quot;选项&quot;]"></custom-variable>',
    );
  });

  it('preserves custom values for anonymous mixed options', () => {
    expect(
      adaptMarkdownFlowInteractionForRender(
        '?[Small//S | Medium//M | ...custom size]',
      ),
    ).toBe(
      '<custom-variable placeholder="custom size" data-button-texts="[&quot;Small&quot;,&quot;Medium&quot;]" data-button-values="[&quot;S&quot;,&quot;M&quot;]"></custom-variable>',
    );
  });

  it('uses a leading single separator without splitting double pipes in an option', () => {
    expect(
      adaptMarkdownFlowInteractionForRender('?[A | B||C | ...Other]'),
    ).toBe(
      '<custom-variable placeholder="Other" data-button-texts="[&quot;A&quot;,&quot;B||C&quot;]" data-button-values="[&quot;A&quot;,&quot;B||C&quot;]"></custom-variable>',
    );
  });

  it('uses a leading double separator even when a single pipe precedes the prompt', () => {
    expect(
      adaptMarkdownFlowInteractionForRender('?[A||B | C | ...Other]'),
    ).toBe(
      '<custom-variable placeholder="Other" data-button-texts="[&quot;A&quot;,&quot;B | C |&quot;]" data-button-values="[&quot;A&quot;,&quot;B | C |&quot;]" data-is-multi-select="true"></custom-variable>',
    );
  });

  it('escapes the prompt when adapting it into an HTML attribute', () => {
    expect(
      adaptMarkdownFlowInteractionForRender(
        '?[...输入 "昵称"、\'代号\' & <个人标签>]',
      ),
    ).toBe(
      '<custom-variable placeholder="输入 &quot;昵称&quot;、&#39;代号&#39; &amp; &lt;个人标签&gt;"></custom-variable>',
    );
  });

  it.each([
    '?[继续]',
    '?[%{{name}}...你叫什么名字]',
    '?[%{{role}} 搜索工具 || ...其他角色]',
    '?[搜索工具 | 效率助手]',
    '?[搜索工具 | 效率助手||数字员工]',
    '?[处理中...请稍候]',
    '?[...]',
    '示例：?[...你叫什么名字]',
    '?[...你叫什么名字]\n?[继续]',
  ])('keeps non-target interaction content unchanged: %s', content => {
    expect(adaptMarkdownFlowInteractionForRender(content)).toBe(content);
  });
});
