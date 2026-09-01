import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { useLiveVoiceFollowUp } from './useLiveVoiceFollowUp';

const mockTrackEvent = jest.fn();
const mockCreateSession = jest.fn();
const mockActivateAudio = jest.fn();
const mockRequestExclusive = jest.fn();
const mockReleaseExclusive = jest.fn();
const START_LABEL = 'start';
const INVALID_START_LABEL = 'start-invalid';
const RETRY_LABEL = 'retry';
const END_LABEL = 'end';
const MUTE_LABEL = 'mute';
const CLOSE_LABEL = 'close';

const mockAudio = {
  clearPlayback: jest.fn(),
  enqueueOutput: jest.fn(),
  finishOutput: jest.fn(),
  setMuted: jest.fn(),
  stop: jest.fn().mockResolvedValue(undefined),
};

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/hooks/useExclusiveAudio', () => ({
  __esModule: true,
  default: () => ({
    requestExclusive: mockRequestExclusive,
    releaseExclusive: mockReleaseExclusive,
  }),
}));

jest.mock('./liveVoiceFollowUpAudio', () => ({
  LiveVoiceAudioUnavailableError: class extends Error {},
  LiveVoiceFollowUpAudio: {
    activate: (...args: unknown[]) => mockActivateAudio(...args),
  },
}));

jest.mock('@/lib/liveVoiceFollowUp', () => {
  return {
    createLiveFollowUpSession: (...args: unknown[]) =>
      mockCreateSession(...args),
    parseLiveFollowUpServerMessage: (payload: string) => {
      try {
        return JSON.parse(payload);
      } catch {
        return null;
      }
    },
    resolveLiveFollowUpWebSocketUrl: () =>
      'wss://example.test/api/learn/live-follow-up/ws/session-1',
  };
});

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly url: string;
  binaryType = '';
  readyState = MockWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  send = jest.fn();

  constructor(url: string) {
    this.url = url;
    mockSockets.push(this);
  }

  close = jest.fn(() => {
    this.readyState = MockWebSocket.CLOSED;
  });

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  message(payload: Record<string, unknown>) {
    this.onmessage?.(
      new MessageEvent('message', { data: JSON.stringify(payload) }),
    );
  }

  binary(payload: ArrayBuffer) {
    this.onmessage?.(new MessageEvent('message', { data: payload }));
  }
}

const mockSockets: MockWebSocket[] = [];

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, reject, resolve };
};

const Harness = ({
  shifuBid = 'course-1',
  previewMode = false,
  learningMode = 'read',
  sessionScope = learningMode,
}: {
  shifuBid?: string;
  previewMode?: boolean;
  learningMode?: 'read' | 'listen';
  sessionScope?: 'read' | 'listen' | 'classroom';
}) => {
  const controller = useLiveVoiceFollowUp({
    shifuBid,
    outlineBid: 'lesson-1',
    previewMode,
    learningMode,
    sessionScope,
  });
  return (
    <div>
      <button
        type='button'
        onClick={() =>
          controller.start({
            anchorElementBid: 'element-1',
            surface: previewMode ? 'teacher_preview' : 'read_content',
          })
        }
      >
        {START_LABEL}
      </button>
      <button
        type='button'
        onClick={() =>
          controller.start({
            anchorElementBid: '   ',
            surface: 'read_content',
          })
        }
      >
        {INVALID_START_LABEL}
      </button>
      <button
        type='button'
        onClick={controller.retry}
      >
        {RETRY_LABEL}
      </button>
      <button
        type='button'
        onClick={controller.close}
      >
        {CLOSE_LABEL}
      </button>
      <button
        type='button'
        onClick={controller.end}
      >
        {END_LABEL}
      </button>
      <button
        type='button'
        onClick={controller.toggleMuted}
      >
        {MUTE_LABEL}
      </button>
      <span data-testid='state'>{controller.state}</span>
      <span data-testid='warning'>{String(controller.warning)}</span>
      <span data-testid='transcripts'>
        {JSON.stringify(controller.transcripts)}
      </span>
    </div>
  );
};

describe('useLiveVoiceFollowUp', () => {
  beforeAll(() => {
    Object.defineProperty(global, 'WebSocket', {
      configurable: true,
      value: MockWebSocket,
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockTrackEvent.mockImplementation(() => undefined);
    mockSockets.length = 0;
    mockActivateAudio.mockResolvedValue(mockAudio);
    mockCreateSession.mockResolvedValue({
      session_bid: 'session-1',
      ws_path: '/api/learn/live-follow-up/ws/session-1',
      expires_at: '2030-01-01T00:00:00Z',
    });
  });

  it('starts microphone activation and session creation directly from click', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));

    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockCreateSession).toHaveBeenCalledWith('course-1', 'lesson-1', {
      anchor_element_bid: 'element-1',
      preview_mode: false,
      learning_mode: 'read',
      surface: 'read_content',
    });
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_attempt',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
      },
    );

    await waitFor(() => expect(mockSockets).toHaveLength(1));
  });

  it('consumes the session ticket while microphone activation is still pending', async () => {
    const pendingAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'start' }));

    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => {
      mockSockets[0].open();
      mockSockets[0].message({ type: 'state', state: 'listening' });
    });
    expect(screen.getByTestId('state')).toHaveTextContent('connecting');
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      expect.anything(),
    );

    await act(async () => {
      pendingAudio.resolve(mockAudio);
      await pendingAudio.promise;
    });

    expect(screen.getByTestId('state')).toHaveTextContent('listening');
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      expect.objectContaining({ outcome: 'success', error_code: 'none' }),
    );
  });

  it('does not create an attempt for an invalid local anchor', () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'start-invalid' }));

    expect(mockActivateAudio).not.toHaveBeenCalled();
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  it('stops activated microphone immediately while session creation is pending', async () => {
    const pendingSession = createDeferred<{
      session_bid: string;
      ws_path: string;
      expires_at: string;
    }>();
    mockCreateSession.mockReturnValueOnce(pendingSession.promise);
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(mockAudio.stop).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'close' }));

    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    pendingSession.resolve({
      session_bid: 'session-1',
      ws_path: '/api/learn/live-follow-up/ws/session-1',
      expires_at: '2030-01-01T00:00:00Z',
    });
    await act(async () => {
      await pendingSession.promise;
    });
    expect(mockSockets).toHaveLength(0);
  });

  it('stops stale audio that resolves after the attempt is closed', async () => {
    const pendingAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    fireEvent.click(screen.getByRole('button', { name: 'close' }));
    pendingAudio.resolve(mockAudio);
    await act(async () => {
      await pendingAudio.promise;
    });

    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(mockSockets).toHaveLength(0);
  });

  it.each(['end', 'close'] as const)(
    'reports one cancelled result when the learner chooses %s before connection',
    async action => {
      render(<Harness />);
      fireEvent.click(screen.getByRole('button', { name: 'start' }));
      await waitFor(() => expect(mockSockets).toHaveLength(1));

      fireEvent.click(screen.getByRole('button', { name: action }));

      const resultCalls = mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'learner_voice_follow_up_result',
      );
      expect(resultCalls).toEqual([
        [
          'learner_voice_follow_up_result',
          {
            shifu_bid: 'course-1',
            outline_bid: 'lesson-1',
            learning_mode: 'read',
            surface: 'read_content',
            outcome: 'cancelled',
            error_code: 'none',
          },
        ],
      ]);
      expect(mockTrackEvent).not.toHaveBeenCalledWith(
        'learner_voice_follow_up_session_end',
        expect.anything(),
      );
    },
  );

  it('reports success only after the server enters a connected voice state', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));

    act(() => mockSockets[0].open());
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      expect.anything(),
    );

    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        outcome: 'success',
        error_code: 'none',
      },
    );

    act(() => mockSockets[0].message({ type: 'state', state: 'speaking' }));
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'learner_voice_follow_up_result',
      ),
    ).toHaveLength(1);
  });

  it('reports failure when transport opens but the server rejects the session', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() =>
      mockSockets[0].message({
        type: 'error',
        code: 'capacity_exceeded',
        retryable: true,
      }),
    );

    const failedResult = mockTrackEvent.mock.calls.find(
      ([eventName]) => eventName === 'learner_voice_follow_up_result',
    );
    expect(failedResult).toEqual([
      'learner_voice_follow_up_result',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        outcome: 'failed',
        error_code: 'capacity_exceeded',
      },
    ]);
    expect(failedResult?.[1]).not.toHaveProperty('model');
    expect(failedResult?.[1]).not.toHaveProperty('voice');
    expect(failedResult?.[1]).not.toHaveProperty('transcript');
    expect(failedResult?.[1]).not.toHaveProperty('prompt');
    expect(failedResult?.[1]).not.toHaveProperty('url');
    expect(failedResult?.[1]).not.toHaveProperty('error');
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_session_end',
      expect.anything(),
    );
  });

  it('counts an explicit retry as a new attempt', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() =>
      mockSockets[0].message({
        type: 'error',
        code: 'capacity_reached',
        retryable: true,
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'retry' }));

    await waitFor(() => expect(mockSockets).toHaveLength(2));
    act(() => mockSockets[1].open());
    act(() => mockSockets[1].message({ type: 'state', state: 'listening' }));
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'learner_voice_follow_up_attempt',
      ),
    ).toHaveLength(2);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'learner_voice_follow_up_result',
      ),
    ).toHaveLength(2);
    expect(mockActivateAudio).toHaveBeenCalledTimes(2);
  });

  it('keeps microphone denial in the retry-only voice flow', async () => {
    mockActivateAudio.mockRejectedValueOnce(
      new DOMException('denied', 'NotAllowedError'),
    );
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'start' }));

    await waitFor(() => {
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_voice_follow_up_result',
        expect.objectContaining({
          outcome: 'failed',
          error_code: 'microphone_denied',
        }),
      );
    });
    expect(mockSockets).toHaveLength(1);
    expect(mockSockets[0].close).toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      expect.objectContaining({ outcome: 'success' }),
    );
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByRole('button', { name: 'retry' })).toBeEnabled();
  });

  it('fails a server-ready attempt when pending microphone permission is denied', async () => {
    const pendingAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => {
      mockSockets[0].open();
      mockSockets[0].message({ type: 'state', state: 'listening' });
    });

    await act(async () => {
      pendingAudio.reject(new DOMException('denied', 'NotAllowedError'));
      await pendingAudio.promise.catch(() => undefined);
    });

    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      expect.objectContaining({
        outcome: 'failed',
        error_code: 'microphone_denied',
      }),
    );
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      expect.objectContaining({ outcome: 'success' }),
    );
    expect(mockSockets[0].close).toHaveBeenCalled();
  });

  it.each(['service_error', 'server_timeout'])(
    'reports server session_end %s before connection as a failed result',
    async reason => {
      render(<Harness />);
      fireEvent.click(screen.getByRole('button', { name: 'start' }));
      await waitFor(() => expect(mockSockets).toHaveLength(1));
      act(() => mockSockets[0].open());

      act(() => mockSockets[0].message({ type: 'session_end', reason }));

      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_voice_follow_up_result',
        expect.objectContaining({
          outcome: 'failed',
          error_code: 'server_error',
        }),
      );
      expect(mockTrackEvent).not.toHaveBeenCalledWith(
        'learner_voice_follow_up_result',
        expect.objectContaining({ outcome: 'success' }),
      );
    },
  );

  it('flushes the current upstream audio stream when muted', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));

    fireEvent.click(screen.getByRole('button', { name: 'mute' }));

    expect(mockAudio.setMuted).toHaveBeenCalledWith(true);
    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'audio_stream_end' }),
    );
  });

  it('keeps audio muted when permission resolves after the mute action', async () => {
    const pendingAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());

    fireEvent.click(screen.getByRole('button', { name: 'mute' }));
    await act(async () => {
      pendingAudio.resolve(mockAudio);
      await pendingAudio.promise;
    });

    expect(mockAudio.setMuted).toHaveBeenLastCalledWith(true);
    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'audio_stream_end' }),
    );
  });

  it('forwards final playback progress before playback completion', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onPlaybackProgress: (turnIndex: number, playedBytes: number) => void;
      onPlaybackComplete: (turnIndex: number) => void;
    };

    act(() => {
      callbacks.onPlaybackProgress(4, 2048);
      callbacks.onPlaybackComplete(4);
    });

    expect(mockSockets[0].send.mock.calls.slice(-2)).toEqual([
      [
        JSON.stringify({
          type: 'playback_progress',
          turn_index: 4,
          played_bytes: 2048,
        }),
      ],
      [JSON.stringify({ type: 'playback_complete', turn_index: 4 })],
    ]);
  });

  it('clears queued playback immediately when the server reports interruption', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());

    act(() => mockSockets[0].message({ type: 'interrupted', turn_index: 2 }));

    expect(mockAudio.clearPlayback).toHaveBeenCalledTimes(1);
  });

  it('does not finish an output turn on the listening state used for resumption', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => {
      mockSockets[0].open();
      mockSockets[0].message({
        type: 'state',
        state: 'speaking',
        turn_index: 6,
      });
      mockSockets[0].message({ type: 'state', state: 'reconnecting' });
      mockSockets[0].message({ type: 'state', state: 'listening' });
    });

    expect(mockAudio.finishOutput).not.toHaveBeenCalled();

    act(() => {
      mockSockets[0].message({
        type: 'state',
        state: 'speaking',
        turn_index: 6,
      });
      mockSockets[0].message({ type: 'state', state: 'listening' });
    });
    expect(mockAudio.finishOutput).toHaveBeenCalledTimes(1);
    expect(mockAudio.finishOutput).toHaveBeenCalledWith(6);
  });

  it('reconciles partial transcripts and routes binary output to its turn', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => {
      mockSockets[0].message({
        type: 'transcript',
        role: 'user',
        turn_index: 2,
        text: 'Hel',
        final: false,
      });
      mockSockets[0].message({
        type: 'transcript',
        role: 'user',
        turn_index: 2,
        text: 'Hello',
        final: true,
      });
      mockSockets[0].message({
        type: 'state',
        state: 'speaking',
        turn_index: 2,
      });
      mockSockets[0].message({
        type: 'transcript',
        role: 'assistant',
        turn_index: 2,
        text: 'Hi',
        final: false,
      });
    });
    const audioBuffer = new ArrayBuffer(8);
    act(() => mockSockets[0].binary(audioBuffer));
    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));

    expect(screen.getByTestId('transcripts')).toHaveTextContent(
      JSON.stringify([
        { role: 'user', turnIndex: 2, text: 'Hello', final: true },
        { role: 'assistant', turnIndex: 2, text: 'Hi', final: false },
      ]),
    );
    expect(mockAudio.enqueueOutput).toHaveBeenCalledWith(audioBuffer, 2);
    expect(mockAudio.finishOutput).toHaveBeenCalledWith(2);
  });

  it('tracks the connected session end with allowlisted fields only', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => {
      mockSockets[0].message({ type: 'state', state: 'listening' });
      mockSockets[0].message({ type: 'turn_committed', turn_index: 0 });
    });
    fireEvent.click(screen.getByRole('button', { name: 'end' }));

    await waitFor(() =>
      expect(mockSockets[0].send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'end' }),
      ),
    );

    const endCall = mockTrackEvent.mock.calls.find(
      ([eventName]) => eventName === 'learner_voice_follow_up_session_end',
    );
    expect(endCall?.[1]).toEqual({
      shifu_bid: 'course-1',
      outline_bid: 'lesson-1',
      learning_mode: 'read',
      surface: 'read_content',
      duration_ms: expect.any(Number),
      had_exchange: true,
      end_reason: 'user_end',
    });
    expect(endCall?.[1]).not.toHaveProperty('model');
    expect(endCall?.[1]).not.toHaveProperty('voice');
    expect(endCall?.[1]).not.toHaveProperty('transcript');
    expect(endCall?.[1]).not.toHaveProperty('url');
  });

  it('sends the end control only after the final audio flush completes', async () => {
    const pendingStop = createDeferred<void>();
    mockAudio.stop.mockReturnValueOnce(pendingStop.promise);
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => {
      mockSockets[0].open();
      mockSockets[0].message({ type: 'state', state: 'listening' });
    });

    fireEvent.click(screen.getByRole('button', { name: 'end' }));
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(mockSockets[0].send).not.toHaveBeenCalledWith(
      JSON.stringify({ type: 'end' }),
    );
    expect(mockSockets[0].close).not.toHaveBeenCalled();

    await act(async () => {
      pendingStop.resolve();
      await pendingStop.promise;
    });

    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'end' }),
    );
    expect(mockSockets[0].close).toHaveBeenCalled();
    expect(mockSockets[0].send.mock.invocationCallOrder.at(-1)).toBeLessThan(
      mockSockets[0].close.mock.invocationCallOrder[0],
    );
  });

  it('warns at 14:30 and ends the connected session at 15 minutes', async () => {
    jest.useFakeTimers();
    try {
      render(<Harness />);
      fireEvent.click(screen.getByRole('button', { name: 'start' }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(mockSockets).toHaveLength(1);
      act(() => mockSockets[0].open());
      act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));

      act(() => jest.advanceTimersByTime(14 * 60 * 1000 + 30 * 1000));
      expect(screen.getByTestId('warning')).toHaveTextContent('true');

      act(() => jest.advanceTimersByTime(30 * 1000));
      expect(screen.getByTestId('state')).toHaveTextContent('ended');
      expect(mockAudio.stop).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_voice_follow_up_session_end',
        expect.objectContaining({ end_reason: 'timeout' }),
      );
    } finally {
      jest.useRealTimers();
    }
  });

  it('uses the server-ready deadline while microphone permission is pending', async () => {
    jest.useFakeTimers();
    const pendingAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
    try {
      render(<Harness />);
      fireEvent.click(screen.getByRole('button', { name: 'start' }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(mockSockets).toHaveLength(1);
      act(() => {
        mockSockets[0].open();
        mockSockets[0].message({ type: 'state', state: 'listening' });
      });

      act(() => jest.advanceTimersByTime(14 * 60 * 1000 + 30 * 1000));
      expect(screen.getByTestId('warning')).toHaveTextContent('true');
      expect(mockTrackEvent).not.toHaveBeenCalledWith(
        'learner_voice_follow_up_result',
        expect.objectContaining({ outcome: 'success' }),
      );

      act(() => jest.advanceTimersByTime(30 * 1000));
      expect(screen.getByTestId('state')).toHaveTextContent('ended');
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_voice_follow_up_result',
        expect.objectContaining({
          outcome: 'failed',
          error_code: 'server_error',
        }),
      );

      await act(async () => {
        pendingAudio.resolve(mockAudio);
        await pendingAudio.promise;
      });
      expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    } finally {
      jest.useRealTimers();
    }
  });

  it('clears the server deadline when pending microphone permission is denied', async () => {
    jest.useFakeTimers();
    const pendingAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
    try {
      render(<Harness />);
      fireEvent.click(screen.getByRole('button', { name: 'start' }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(mockSockets).toHaveLength(1);
      act(() => {
        mockSockets[0].open();
        mockSockets[0].message({ type: 'state', state: 'listening' });
      });
      expect(jest.getTimerCount()).toBe(2);

      await act(async () => {
        pendingAudio.reject(new DOMException('denied', 'NotAllowedError'));
        await pendingAudio.promise.catch(() => undefined);
      });

      expect(jest.getTimerCount()).toBe(0);
      expect(screen.getByTestId('warning')).toHaveTextContent('false');
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_voice_follow_up_result',
        expect.objectContaining({
          outcome: 'failed',
          error_code: 'microphone_denied',
        }),
      );
    } finally {
      jest.useRealTimers();
    }
  });

  it('remains usable when tracking throws', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('analytics unavailable');
    });
    render(<Harness />);

    expect(() =>
      fireEvent.click(screen.getByRole('button', { name: 'start' })),
    ).not.toThrow();
    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));
    fireEvent.click(screen.getByRole('button', { name: 'end' }));
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
  });

  it('remains usable when tracking rejects asynchronously', async () => {
    mockTrackEvent.mockRejectedValue(new Error('analytics unavailable'));
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));
    fireEvent.click(screen.getByRole('button', { name: 'end' }));

    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
  });

  it('excludes teacher preview from learner analytics', async () => {
    render(<Harness previewMode />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).not.toHaveBeenCalled();
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));
    fireEvent.click(screen.getByRole('button', { name: 'end' }));
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  it('deduplicates terminal server messages for a connected session', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));

    act(() =>
      mockSockets[0].message({ type: 'session_end', reason: 'timeout' }),
    );
    act(() =>
      mockSockets[0].message({ type: 'session_end', reason: 'timeout' }),
    );

    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'learner_voice_follow_up_session_end',
      ),
    ).toHaveLength(1);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'learner_voice_follow_up_result',
      ),
    ).toHaveLength(1);
  });

  it('releases microphone and transport when the learning scope changes', async () => {
    const { rerender } = render(<Harness learningMode='read' />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));

    rerender(<Harness learningMode='listen' />);

    await waitFor(() => expect(mockAudio.stop).toHaveBeenCalledTimes(1));
    expect(mockSockets[0].close).toHaveBeenCalled();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_session_end',
      expect.objectContaining({ end_reason: 'lesson_changed' }),
    );
  });

  it('releases an active read session when entering classroom scope', async () => {
    const { rerender } = render(
      <Harness
        learningMode='read'
        sessionScope='read'
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));

    rerender(
      <Harness
        learningMode='read'
        sessionScope='classroom'
      />,
    );

    await waitFor(() => expect(mockAudio.stop).toHaveBeenCalledTimes(1));
    expect(mockSockets[0].close).toHaveBeenCalled();
  });

  it('releases an active session when the course changes', async () => {
    const { rerender } = render(<Harness shifuBid='course-1' />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    act(() => mockSockets[0].message({ type: 'state', state: 'listening' }));

    rerender(<Harness shifuBid='course-2' />);

    await waitFor(() => expect(mockAudio.stop).toHaveBeenCalledTimes(1));
    expect(mockSockets[0].close).toHaveBeenCalled();
  });
});
