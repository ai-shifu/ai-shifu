import React from 'react';
import { fireEvent, render } from '@testing-library/react';

const goNextMock = jest.fn(() => 2);
const startSequenceFromPageMock = jest.fn();
const startSequenceFromIndexMock = jest.fn();
const NEXT_BUTTON_LABEL = 'next';
const sequenceState: { isAudioSequenceActive: boolean } = {
  isAudioSequenceActive: true,
};

jest.mock('@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook', () => ({
  ChatContentItemType: {
    CONTENT: 'content',
    INTERACTION: 'interaction',
    ASK: 'ask',
    LIKE_STATUS: 'likeStatus',
  },
}));

jest.mock('@/app/c/[[...id]]/Components/ChatUi/ListenPlayer', () => {
  return function MockListenPlayer(props: { onNext: () => void }) {
    return (
      <button
        data-testid='listen-next'
        onClick={props.onNext}
      >
        {NEXT_BUTTON_LABEL}
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
    audioAndInteractionList: [
      {
        type: 'content',
        generated_block_bid: 'block-with-audio',
        page: 2,
        content: 'content',
      },
    ],
    contentByBid: new Map(),
    audioContentByBid: new Map(),
    firstContentItem: null,
  }),
  useListenPpt: () => ({
    isPrevDisabled: true,
    isNextDisabled: false,
    goPrev: () => null,
    goNext: goNextMock,
  }),
  useListenAudioSequence: () => ({
    audioPlayerRef: { current: null },
    activeAudioBlockBid: null,
    activeAudioPosition: 0,
    sequenceInteraction: null,
    isAudioSequenceActive: sequenceState.isAudioSequenceActive,
    isAudioPlayerBusy: () => false,
    audioSequenceToken: 0,
    handleAudioEnded: () => undefined,
    handleAudioError: () => undefined,
    handlePlay: () => undefined,
    handlePause: () => undefined,
    continueAfterInteraction: () => undefined,
    startSequenceFromIndex: startSequenceFromIndexMock,
    startSequenceFromPage: startSequenceFromPageMock,
  }),
}));

import ListenModeRenderer from '@/app/c/[[...id]]/Components/ChatUi/ListenModeRenderer';

describe('ListenModeRenderer navigation in paused sequence', () => {
  beforeEach(() => {
    goNextMock.mockClear();
    startSequenceFromPageMock.mockClear();
    startSequenceFromIndexMock.mockClear();
    sequenceState.isAudioSequenceActive = true;
  });

  it('uses page-only navigation when sequence is active but audio is paused', () => {
    const { getByTestId } = render(
      <ListenModeRenderer
        items={[] as any}
        mobileStyle={false}
        chatRef={{ current: null }}
      />,
    );

    fireEvent.click(getByTestId('listen-next'));

    expect(goNextMock).toHaveBeenCalledTimes(1);
    expect(startSequenceFromPageMock).not.toHaveBeenCalled();
    expect(startSequenceFromIndexMock).not.toHaveBeenCalled();
  });

  it('does not auto-start sequence when sequence is inactive and user is paused', () => {
    sequenceState.isAudioSequenceActive = false;

    const { getByTestId } = render(
      <ListenModeRenderer
        items={[] as any}
        mobileStyle={false}
        chatRef={{ current: null }}
      />,
    );

    fireEvent.click(getByTestId('listen-next'));

    expect(goNextMock).toHaveBeenCalledTimes(1);
    expect(startSequenceFromPageMock).not.toHaveBeenCalled();
    expect(startSequenceFromIndexMock).not.toHaveBeenCalled();
  });
});
