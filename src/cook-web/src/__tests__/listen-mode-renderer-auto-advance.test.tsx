import React from 'react';
import { render, waitFor } from '@testing-library/react';

const continueAfterInteractionMock = jest.fn();
const sequenceInteractionState: { current: any } = { current: null };

jest.mock('@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook', () => ({
  ChatContentItemType: {
    CONTENT: 'content',
    INTERACTION: 'interaction',
    ASK: 'ask',
    LIKE_STATUS: 'likeStatus',
  },
}));

jest.mock('@/app/c/[[...id]]/Components/ChatUi/ListenPlayer', () => {
  return function MockListenPlayer() {
    return <div data-testid='listen-player' />;
  };
});

jest.mock('@/app/c/[[...id]]/Components/ChatUi/ContentIframe', () => {
  return function MockContentIframe() {
    return <section />;
  };
});

jest.mock('@/components/audio/AudioPlayer', () => {
  const MockAudioPlayer = React.forwardRef(() => null);
  MockAudioPlayer.displayName = 'MockAudioPlayer';
  return { AudioPlayer: MockAudioPlayer };
});

jest.mock('@/app/c/[[...id]]/Components/ChatUi/useListenMode', () => ({
  useListenContentData: () => ({
    orderedContentBlockBids: [],
    slideItems: [],
    audioAndInteractionList: [],
    contentByBid: new Map(),
    audioContentByBid: new Map(),
    firstContentItem: null,
  }),
  useListenPpt: () => ({
    isPrevDisabled: true,
    isNextDisabled: true,
    goPrev: () => null,
    goNext: () => null,
  }),
  useListenAudioSequence: () => ({
    audioPlayerRef: { current: null },
    activeContentItem: undefined,
    activeAudioBlockBid: null,
    activeAudioPosition: 0,
    activeSequencePage: -1,
    sequenceInteraction: sequenceInteractionState.current,
    isAudioSequenceActive: true,
    isAudioPlayerBusy: () => false,
    audioSequenceToken: 0,
    handleAudioEnded: () => undefined,
    handleAudioError: () => undefined,
    handlePlay: () => undefined,
    handlePause: () => undefined,
    continueAfterInteraction: continueAfterInteractionMock,
    startSequenceFromIndex: () => undefined,
    startSequenceFromPage: () => undefined,
  }),
}));

import ListenModeRenderer from '@/app/c/[[...id]]/Components/ChatUi/ListenModeRenderer';

describe('ListenModeRenderer interaction auto-advance', () => {
  beforeEach(() => {
    continueAfterInteractionMock.mockClear();
    sequenceInteractionState.current = null;
  });

  it('auto-continues when sequence interaction already has response', async () => {
    sequenceInteractionState.current = {
      type: 'interaction',
      generated_block_bid: 'interaction-answered',
      defaultSelectedValues: ['A'],
      customRenderBar: () => null,
    };

    render(
      <ListenModeRenderer
        items={[] as any}
        mobileStyle={false}
        chatRef={{ current: null }}
      />,
    );

    await waitFor(() => {
      expect(continueAfterInteractionMock).toHaveBeenCalledTimes(1);
    });
  });

  it('does not auto-continue when sequence interaction is unanswered', async () => {
    sequenceInteractionState.current = {
      type: 'interaction',
      generated_block_bid: 'interaction-pending',
      defaultSelectedValues: [],
      defaultButtonText: '',
      defaultInputText: '',
      customRenderBar: () => null,
    };

    render(
      <ListenModeRenderer
        items={[] as any}
        mobileStyle={false}
        chatRef={{ current: null }}
      />,
    );

    await waitFor(() => {
      expect(continueAfterInteractionMock).not.toHaveBeenCalled();
    });
  });
});
