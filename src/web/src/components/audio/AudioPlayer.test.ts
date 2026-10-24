import { createElement } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import AudioPlayer, {
  shouldFallbackToCompleteUrlForWaitingStream,
} from './AudioPlayer';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

it('stops waiting after an audio request fails and permits another request', async () => {
  let rejectAudio: (error: Error) => void = () => {};
  const request = jest.fn(
    () =>
      new Promise((_, reject) => {
        rejectAudio = reject;
      }),
  );
  const consoleError = jest
    .spyOn(console, 'error')
    .mockImplementation(() => {});
  try {
    render(
      createElement(AudioPlayer, {
        alwaysVisible: true,
        onRequestAudio: request,
      }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'module.chat.playAudio' }),
    );
    expect(
      screen.getByRole('button', { name: 'module.chat.audioLoading' }),
    ).toBeTruthy();
    await act(async () => rejectAudio(new Error('Provider unavailable')));
    fireEvent.click(
      screen.getByRole('button', { name: 'module.chat.playAudio' }),
    );
    expect(request).toHaveBeenCalledTimes(2);
    await act(async () => rejectAudio(new Error('Provider unavailable')));
  } finally {
    consoleError.mockRestore();
  }
});

describe('shouldFallbackToCompleteUrlForWaitingStream', () => {
  it('does not use the complete URL after stream segments have been consumed', () => {
    expect(
      shouldFallbackToCompleteUrlForWaitingStream({
        audioUrl: 'https://example.com/final.mp3',
        streamingSegmentCount: 1,
        currentSegmentIndex: 1,
        playedSeconds: 1,
      }),
    ).toBe(false);
  });

  it('uses the complete URL when a stream finishes without segments', () => {
    expect(
      shouldFallbackToCompleteUrlForWaitingStream({
        audioUrl: 'https://example.com/cached.mp3',
        streamingSegmentCount: 0,
        currentSegmentIndex: 0,
        playedSeconds: 0,
      }),
    ).toBe(true);
  });

  it('does not use the complete URL when none is available', () => {
    expect(
      shouldFallbackToCompleteUrlForWaitingStream({
        audioUrl: undefined,
        streamingSegmentCount: 0,
        currentSegmentIndex: 0,
        playedSeconds: 0,
      }),
    ).toBe(false);
  });
});
