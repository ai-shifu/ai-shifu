import React from 'react';
import { render } from '@testing-library/react';
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
});
