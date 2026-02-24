import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const continueAfterInteractionMock = jest.fn();
const handlePlayMock = jest.fn();
const sequenceInteractionState: { current: any } = { current: null };
const isAudioSequenceActiveState: { current: boolean } = { current: true };

jest.mock('@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook', () => ({
  ChatContentItemType: {
    CONTENT: 'content',
    INTERACTION: 'interaction',
    ASK: 'ask',
    LIKE_STATUS: 'likeStatus',
  },
}));

jest.mock('@/app/c/[[...id]]/Components/ChatUi/ListenPlayer', () => {
  return function MockListenPlayer(props: any) {
    return (
      <button
        data-testid='listen-player-send'
        onClick={() => props.onSend?.({} as any, 'interaction-pending')}
      >
        send
      </button>
    );
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
    activeAudioBlockBid: null,
    activeAudioPosition: 0,
    sequenceInteraction: sequenceInteractionState.current,
    isAudioSequenceActive: isAudioSequenceActiveState.current,
    isAudioPlayerBusy: () => false,
    audioSequenceToken: 0,
    handleAudioEnded: () => undefined,
    handleAudioError: () => undefined,
    handlePlay: handlePlayMock,
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
    handlePlayMock.mockClear();
    sequenceInteractionState.current = null;
    isAudioSequenceActiveState.current = true;
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

  it('resumes playback when submitting a pending non-sequence interaction', async () => {
    isAudioSequenceActiveState.current = false;

    render(
      <ListenModeRenderer
        items={
          [
            {
              type: 'interaction',
              generated_block_bid: 'interaction-pending',
              defaultSelectedValues: [],
              defaultButtonText: '',
              defaultInputText: '',
              customRenderBar: () => null,
            },
          ] as any
        }
        mobileStyle={false}
        chatRef={{ current: null }}
      />,
    );

    fireEvent.click(screen.getByTestId('listen-player-send'));

    await waitFor(() => {
      expect(handlePlayMock).toHaveBeenCalledTimes(1);
    });
    expect(continueAfterInteractionMock).not.toHaveBeenCalled();
  });
});
