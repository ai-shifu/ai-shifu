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
            content: '提交以下内容后继续学习\n?[去支付//_sys_pay]',
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
        typingSpeed: 40,
      }),
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
});
