import React from 'react';
import { render, screen } from '@testing-library/react';
import ContentBlock from '@/c-components/ChatUi/ContentBlock';

const mockContentRender = jest.fn<null, [Record<string, unknown>]>(() => null);

jest.mock('markdown-flow-ui/renderer', () => ({
  ContentRender: (props: Record<string, unknown>) => {
    mockContentRender(props);
    return null;
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'zh-CN',
      resolvedLanguage: 'zh-CN',
    },
  }),
}));

jest.mock('react-use', () => ({
  useLongPress: () => ({}),
}));

jest.mock('@/c-utils/audio-utils', () => ({
  getAudioTrackByPosition: jest.fn(() => null),
  hasAudioContentInTrack: jest.fn(() => false),
}));

jest.mock('@/c-utils/lesson-feedback-interaction', () => ({
  isLessonFeedbackInteractionContent: jest.fn(() => false),
}));

jest.mock('@/c-utils/system-interaction', () => ({
  isPaySystemInteractionContent: jest.fn((content?: string) =>
    Boolean(content?.includes('_sys_pay')),
  ),
  localizeSystemInteractionContent: (content: string) => content,
}));

describe('ContentBlock pay interaction overrides', () => {
  beforeEach(() => {
    mockContentRender.mockClear();
  });

  it('keeps sys pay interactions writable and unselected', () => {
    render(
      <ContentBlock
        item={
          {
            type: 'interaction',
            content: 'Pay interaction\n?[Pay//_sys_pay]',
            element_bid: 'pay-block',
            readonly: true,
            user_input: '_sys_pay',
          } as any
        }
        mobileStyle={false}
        blockBid='pay-block'
        onSend={jest.fn()}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledWith(
      expect.objectContaining({
        locale: 'zh-CN',
        readonly: false,
        userInput: '',
      }),
    );
  });

  it('preserves normal interaction readonly and user input state', () => {
    render(
      <ContentBlock
        item={
          {
            type: 'interaction',
            content: '请选择\n?[继续学习//continue]',
            element_bid: 'normal-block',
            readonly: true,
            user_input: 'continue',
          } as any
        }
        mobileStyle={false}
        blockBid='normal-block'
        onSend={jest.fn()}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledWith(
      expect.objectContaining({
        readonly: true,
        userInput: 'continue',
      }),
    );
  });

  it('freezes a course interaction for printing without dropping its answer', () => {
    render(
      <ContentBlock
        item={
          {
            type: 'interaction',
            content: '请选择\n?[继续学习//continue]',
            element_bid: 'print-block',
            readonly: false,
            user_input: 'continue',
          } as any
        }
        printMode={true}
        mobileStyle={false}
        blockBid='print-block'
        onSend={jest.fn()}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledWith(
      expect.objectContaining({
        readonly: true,
        userInput: 'continue',
      }),
    );
  });

  it('adapts a variable-free ellipsis interaction into a text input', () => {
    const onSend = jest.fn();
    render(
      <ContentBlock
        item={
          {
            type: 'interaction',
            content: '?[...你叫什么名字]',
            element_bid: 'anonymous-input',
            readonly: false,
            user_input: '小明',
          } as any
        }
        mobileStyle={false}
        blockBid='anonymous-input'
        onSend={onSend}
      />,
    );

    const contentRenderProps = mockContentRender.mock.calls[0]?.[0];
    expect(contentRenderProps).toEqual(
      expect.objectContaining({
        content:
          '<custom-variable placeholder="你叫什么名字"></custom-variable>',
        userInput: '小明',
      }),
    );

    const onContentRenderSend = contentRenderProps?.onSend as
      | ((content: Record<string, unknown>) => void)
      | undefined;
    onContentRenderSend?.({ variableName: '', inputText: '小红' });

    expect(onSend).toHaveBeenCalledWith(
      { variableName: '', inputText: '小红' },
      'anonymous-input',
    );
  });

  it('enables typewriter only for text elements marked as typewriter candidates', () => {
    render(
      <ContentBlock
        item={
          {
            type: 'content',
            element_type: 'text',
            content: '流式正文',
            element_bid: 'streaming-text',
            shouldUseTypewriter: true,
          } as any
        }
        mobileStyle={false}
        blockBid='streaming-text'
        enableStreamingTypewriter={true}
        onSend={jest.fn()}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledWith(
      expect.objectContaining({
        enableTypewriter: true,
        typingSpeed: 30,
      }),
    );
  });

  it('disables typewriter while preparing printable content', () => {
    render(
      <ContentBlock
        item={
          {
            type: 'content',
            element_type: 'text',
            content: '完整打印正文',
            element_bid: 'print-text',
            shouldUseTypewriter: true,
          } as any
        }
        printMode={true}
        mobileStyle={false}
        blockBid='print-text'
        enableStreamingTypewriter={true}
        onSend={jest.fn()}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledWith(
      expect.objectContaining({ enableTypewriter: false }),
    );
  });

  it('strips custom-button markup from typewriter content', () => {
    render(
      <ContentBlock
        item={
          {
            type: 'content',
            element_type: 'text',
            content:
              '流式正文<custom-button-after-content><span>Ask</span></custom-button-after-content>',
            element_bid: 'streaming-text-with-button',
            shouldUseTypewriter: true,
          } as any
        }
        mobileStyle={true}
        blockBid='streaming-text-with-button'
        enableStreamingTypewriter={true}
        onSend={jest.fn()}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledWith(
      expect.objectContaining({
        enableTypewriter: true,
        content: '流式正文',
      }),
    );
  });

  it('renders rich-content follow-up buttons outside content render with stripped inner content', () => {
    render(
      <ContentBlock
        item={
          {
            type: 'content',
            element_type: 'svg',
            content:
              '<svg viewBox="0 0 10 10"></svg><custom-button-after-content><img src="/ask.svg" alt="ask" width="14" height="14" /><span>追问</span></custom-button-after-content>',
            element_bid: 'rich-with-button',
            shouldUseTypewriter: false,
          } as any
        }
        mobileStyle={true}
        blockBid='rich-with-button'
        enableStreamingTypewriter={true}
        onSend={jest.fn()}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledWith(
      expect.objectContaining({
        content: '<svg viewBox="0 0 10 10"></svg>',
      }),
    );
    expect(
      screen.getByRole('button', {
        name: 'ask 追问',
      }),
    ).toBeInTheDocument();
  });

  it('keeps non-candidate text elements out of typewriter mode', () => {
    render(
      <ContentBlock
        item={
          {
            type: 'content',
            element_type: 'text',
            content: '历史正文',
            element_bid: 'history-text',
            shouldUseTypewriter: false,
          } as any
        }
        mobileStyle={false}
        blockBid='history-text'
        enableStreamingTypewriter={true}
        onSend={jest.fn()}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledWith(
      expect.objectContaining({
        enableTypewriter: false,
      }),
    );
  });

  it('rerenders when an item changes from content to interaction', () => {
    const onSend = jest.fn();
    const baseItem = {
      type: 'content',
      content: '?[...你叫什么名字]',
      element_bid: 'changing-type',
    } as any;
    const { rerender } = render(
      <ContentBlock
        item={baseItem}
        mobileStyle={false}
        blockBid='changing-type'
        onSend={onSend}
      />,
    );
    const initialCallCount = mockContentRender.mock.calls.length;

    rerender(
      <ContentBlock
        item={{ ...baseItem, type: 'interaction' }}
        mobileStyle={false}
        blockBid='changing-type'
        onSend={onSend}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledTimes(initialCallCount + 1);
    expect(mockContentRender).toHaveBeenLastCalledWith(
      expect.objectContaining({
        content:
          '<custom-variable placeholder="你叫什么名字"></custom-variable>',
      }),
    );
  });

  it('rerenders when an item becomes a typewriter candidate', () => {
    const onSend = jest.fn();
    const baseItem = {
      type: 'content',
      element_type: 'text',
      content: '流式正文',
      element_bid: 'changing-typewriter',
      shouldUseTypewriter: false,
    } as any;
    const { rerender } = render(
      <ContentBlock
        item={baseItem}
        mobileStyle={false}
        blockBid='changing-typewriter'
        enableStreamingTypewriter={true}
        onSend={onSend}
      />,
    );
    const initialCallCount = mockContentRender.mock.calls.length;

    rerender(
      <ContentBlock
        item={{ ...baseItem, shouldUseTypewriter: true }}
        mobileStyle={false}
        blockBid='changing-typewriter'
        enableStreamingTypewriter={true}
        onSend={onSend}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledTimes(initialCallCount + 1);
    expect(mockContentRender).toHaveBeenLastCalledWith(
      expect.objectContaining({ enableTypewriter: true }),
    );
  });

  it('rerenders when an item replaces its custom render bar', () => {
    const onSend = jest.fn();
    const firstCustomRenderBar = jest.fn(() => null);
    const nextCustomRenderBar = jest.fn(() => null);
    const baseItem = {
      type: 'content',
      content: '正文',
      element_bid: 'changing-render-bar',
      customRenderBar: firstCustomRenderBar,
    } as any;
    const { rerender } = render(
      <ContentBlock
        item={baseItem}
        mobileStyle={false}
        blockBid='changing-render-bar'
        onSend={onSend}
      />,
    );
    const initialCallCount = mockContentRender.mock.calls.length;

    rerender(
      <ContentBlock
        item={{ ...baseItem, customRenderBar: nextCustomRenderBar }}
        mobileStyle={false}
        blockBid='changing-render-bar'
        onSend={onSend}
      />,
    );

    expect(mockContentRender).toHaveBeenCalledTimes(initialCallCount + 1);
    expect(mockContentRender).toHaveBeenLastCalledWith(
      expect.objectContaining({ customRenderBar: nextCustomRenderBar }),
    );
  });
});
