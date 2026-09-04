import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import type { GeminiLiveServerEvent } from '@/lib/liveVoiceFollowUp';

import {
  useLiveVoiceFollowUp,
  type LiveVoiceTranscript,
} from './useLiveVoiceFollowUp';

const mockTrackEvent = jest.fn();
const mockCreateSession = jest.fn();
const mockHeartbeatSession = jest.fn();
const mockCommitTurn = jest.fn();
const mockFinalizeSession = jest.fn();
const mockEndSession = jest.fn();
const mockResolveWebSocketUrl = jest.fn();
const mockEncodeAudio = jest.fn();
const mockParseServerMessage = jest.fn();
const mockActivateAudio = jest.fn();
const mockRequestMicrophone = jest.fn();
const mockRequestExclusive = jest.fn();
const mockReleaseExclusive = jest.fn();

const mockAudio = {
  clearPlayback: jest.fn(),
  enqueueOutput: jest.fn(),
  finishOutput: jest.fn(),
  setMuted: jest.fn(),
  attachMicrophone: jest.fn(),
  stopMicrophone: jest.fn(),
  interruptPlayback: jest.fn().mockResolvedValue(undefined),
  pauseOutput: jest.fn().mockResolvedValue(undefined),
  resumeOutput: jest.fn().mockResolvedValue(undefined),
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
    requestMicrophone: (...args: unknown[]) => mockRequestMicrophone(...args),
  },
}));

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  LIVE_FOLLOW_UP_CAPACITY_ERROR_CODE: 4018,
  createLiveFollowUpSession: (...args: unknown[]) => mockCreateSession(...args),
  heartbeatLiveFollowUpSession: (...args: unknown[]) =>
    mockHeartbeatSession(...args),
  commitLiveFollowUpTurn: (...args: unknown[]) => mockCommitTurn(...args),
  finalizeLiveFollowUpSession: (...args: unknown[]) =>
    mockFinalizeSession(...args),
  endLiveFollowUpSession: (...args: unknown[]) => mockEndSession(...args),
  resolveGeminiLiveWebSocketUrl: (...args: unknown[]) =>
    mockResolveWebSocketUrl(...args),
  encodeGeminiLiveAudioMessage: (...args: unknown[]) =>
    mockEncodeAudio(...args),
  parseGeminiLiveServerMessage: (...args: unknown[]) =>
    mockParseServerMessage(...args),
  mergeLiveTranscript: (current: string, incoming: string) =>
    incoming.startsWith(current) ? incoming : current + incoming,
}));

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly url: string;
  binaryType: BinaryType = 'blob';
  bufferedAmount = 0;
  readyState = MockWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
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

  message(message: GeminiLiveServerEvent) {
    mockParseServerMessage.mockReturnValueOnce(message);
    this.onmessage?.(new MessageEvent('message', { data: '{}' }));
  }

  binaryMessage(message: GeminiLiveServerEvent) {
    mockParseServerMessage.mockReturnValueOnce(message);
    const data = new Uint8Array([123, 125]).buffer;
    this.onmessage?.(new MessageEvent('message', { data }));
    return data;
  }

  fail() {
    this.onerror?.();
  }

  serverClose(code = 1006) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close', { code }));
  }
}

const mockSockets: MockWebSocket[] = [];

const serverEvent = (
  overrides: Partial<GeminiLiveServerEvent> = {},
): GeminiLiveServerEvent => ({
  setupComplete: false,
  audioChunks: [],
  interimInputTranscripts: [],
  inputTranscripts: [],
  outputTranscripts: [],
  interrupted: false,
  turnComplete: false,
  generationComplete: false,
  usageMetadata: null,
  resumptionHandle: null,
  resumable: null,
  goAway: false,
  upstreamError: false,
  ...overrides,
});

const sessionResponse = (expiresAtMs = Date.now() + 15 * 60 * 1000) => ({
  session_bid: 'session-1',
  ephemeral_token: 'auth_tokens/browser-only',
  websocket_url:
    'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained',
  setup: {
    setup: {
      model: 'models/gemini-3.1-flash-live-preview',
      generationConfig: { responseModalities: ['AUDIO'] },
      sessionResumption: {},
      historyConfig: { initialHistoryInClientContent: true },
    },
  },
  history: {
    clientContent: {
      turns: [{ role: 'user', parts: [{ text: 'Earlier question' }] }],
      turnComplete: true as const,
    },
  },
  expires_at: new Date(expiresAtMs).toISOString(),
  new_session_expires_at: new Date(Date.now() + 30_000).toISOString(),
  heartbeat_interval_ms: 15_000,
});

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
  outlineBid = 'lesson-1',
  anchorElementBid = 'element-1',
  previewMode = false,
  learningMode = 'read',
  sessionScope = learningMode,
  onTurnCommitted,
  onTextResult,
}: {
  shifuBid?: string;
  outlineBid?: string;
  anchorElementBid?: string;
  previewMode?: boolean;
  learningMode?: 'read' | 'listen';
  sessionScope?: 'read' | 'listen' | 'classroom';
  onTurnCommitted?: Parameters<
    typeof useLiveVoiceFollowUp
  >[0]['onTurnCommitted'];
  onTextResult?: (sent: boolean) => void;
}) => {
  const [transcripts, setTranscripts] = React.useState<LiveVoiceTranscript[]>(
    [],
  );
  React.useEffect(() => setTranscripts([]), [outlineBid, sessionScope]);
  const controller = useLiveVoiceFollowUp({
    shifuBid,
    outlineBid,
    previewMode,
    learningMode,
    sessionScope,
    onTurnCommitted,
    onTranscript: update =>
      setTranscripts(previous =>
        [
          ...previous.filter(
            item =>
              item.turnIndex !== update.turnIndex || item.role !== update.role,
          ),
          {
            role: update.role,
            turnIndex: update.turnIndex,
            text: update.text,
            final: update.final,
          },
        ].sort(
          (a, b) => a.turnIndex - b.turnIndex || (a.role === 'user' ? -1 : 1),
        ),
      ),
  });
  return (
    <div>
      <button
        type='button'
        onClick={() =>
          controller.startMicrophone({
            anchorElementBid,
            surface: previewMode ? 'teacher_preview' : 'read_content',
          })
        }
      >
        microphone
      </button>
      <button
        type='button'
        onClick={() => controller.stopMicrophone()}
      >
        edit
      </button>
      <button
        type='button'
        onClick={() => {
          void controller
            .sendText(
              {
                anchorElementBid,
                surface: previewMode ? 'teacher_preview' : 'read_content',
              },
              'Typed question',
              'keyboard',
            )
            .then(sent => onTextResult?.(sent));
        }}
      >
        text
      </button>
      <button
        type='button'
        onClick={() => {
          void controller
            .sendText(
              {
                anchorElementBid,
                surface: previewMode ? 'teacher_preview' : 'read_content',
              },
              'Next question',
              'button',
            )
            .then(sent => onTextResult?.(sent));
        }}
      >
        interrupt-text
      </button>
      <button
        type='button'
        onClick={() =>
          controller.start({
            anchorElementBid,
            surface: previewMode ? 'teacher_preview' : 'read_content',
          })
        }
      >
        start
      </button>
      <button
        type='button'
        onClick={() =>
          controller.start({
            anchorElementBid: '  ',
            surface: 'read_content',
          })
        }
      >
        start-invalid
      </button>
      <button
        type='button'
        onClick={controller.retry}
      >
        retry
      </button>
      <button
        type='button'
        onClick={controller.toggleMuted}
      >
        mute
      </button>
      <button
        type='button'
        onClick={controller.end}
      >
        end
      </button>
      <button
        type='button'
        onClick={controller.close}
      >
        close
      </button>
      <span data-testid='state'>{controller.state}</span>
      <button
        type='button'
        onClick={() => controller.pause()}
      >
        pause
      </button>
      <span data-testid='paused'>{String(controller.paused)}</span>
      <span data-testid='open'>{String(controller.open)}</span>
      <span data-testid='warning'>{String(controller.warning)}</span>
      <span data-testid='muted'>{String(controller.muted)}</span>
      <span data-testid='error'>{controller.errorCode || ''}</span>
      <span data-testid='microphone-error'>
        {controller.microphoneError || ''}
      </span>
      <span data-testid='text-pending'>{String(controller.textPending)}</span>
      <span data-testid='end-reason'>{controller.endReason || ''}</span>
      <span data-testid='retryable'>{String(controller.retryable)}</span>
      <span data-testid='retry-at'>{String(controller.retryAvailableAt)}</span>
      <span data-testid='transcripts'>{JSON.stringify(transcripts)}</span>
    </div>
  );
};

const startAndOpen = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'start' }));
  await waitFor(() => expect(mockSockets).toHaveLength(1));
  act(() => mockSockets[0].open());
};

const makeReady = async (socket = mockSockets.at(-1)!) => {
  act(() => socket.message(serverEvent({ setupComplete: true })));
  await waitFor(() =>
    expect(screen.getByTestId('state')).toHaveTextContent('listening'),
  );
};

describe('useLiveVoiceFollowUp browser-direct transport', () => {
  it('pauses microphone and output immediately while retaining the socket and heartbeat', async () => {
    jest.useFakeTimers();
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'microphone' })),
    );
    expect(screen.getByTestId('muted')).toHaveTextContent('false');
    const eventCount = mockTrackEvent.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    expect(mockAudio.stopMicrophone).toHaveBeenCalled();
    expect(mockAudio.pauseOutput).toHaveBeenCalledTimes(1);
    expect(mockReleaseExclusive).toHaveBeenCalledTimes(1);
    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { audioStreamEnd: true } }),
    );
    expect(screen.getByTestId('paused')).toHaveTextContent('true');
    expect(screen.getByTestId('muted')).toHaveTextContent('true');
    expect(screen.getByTestId('open')).toHaveTextContent('false');
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    await act(async () => jest.advanceTimersByTime(15_000));

    expect(mockHeartbeatSession).toHaveBeenCalledWith('session-1');
    expect(mockSockets).toHaveLength(1);
    expect(mockSockets[0].close).not.toHaveBeenCalled();
    expect(mockAudio.stop).not.toHaveBeenCalled();
    expect(mockEndSession).not.toHaveBeenCalled();
    expect(mockFinalizeSession).not.toHaveBeenCalled();
    expect(mockTrackEvent.mock.calls.slice(eventCount)).toEqual([
      [
        'learner_voice_follow_up_pause',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          learning_mode: 'read',
          surface: 'read_content',
          reason: 'panel_closed',
        },
      ],
    ]);
  });

  it.each(['text', 'microphone'] as const)(
    'resumes on explicit %s with native playback activation and validated admission',
    async action => {
      const validation = createDeferred<object>();
      const resumedAudio = createDeferred<void>();
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      fireEvent.click(screen.getByRole('button', { name: 'pause' }));
      mockHeartbeatSession.mockReturnValueOnce(validation.promise);
      mockAudio.resumeOutput.mockReturnValueOnce(resumedAudio.promise);
      const eventCount = mockTrackEvent.mock.calls.length;
      const oldSendCount = mockSockets[0].send.mock.calls.length;

      fireEvent.click(screen.getByRole('button', { name: action }));
      expect(mockAudio.resumeOutput).toHaveBeenCalledTimes(1);
      expect(mockHeartbeatSession).toHaveBeenCalledTimes(1);
      expect(mockRequestExclusive).toHaveBeenCalledTimes(2);
      expect(mockCreateSession).toHaveBeenCalledTimes(1);
      expect(mockActivateAudio).toHaveBeenCalledTimes(1);
      expect(mockSockets[0].send).toHaveBeenCalledTimes(oldSendCount);
      expect(mockAudio.attachMicrophone).not.toHaveBeenCalled();
      expect(mockRequestMicrophone).toHaveBeenCalledTimes(
        action === 'microphone' ? 1 : 0,
      );

      await act(async () => resumedAudio.resolve());
      expect(mockSockets[0].send).toHaveBeenCalledTimes(oldSendCount);
      expect(mockAudio.attachMicrophone).not.toHaveBeenCalled();
      await act(async () => validation.resolve({}));
      expect(screen.getByTestId('paused')).toHaveTextContent('false');
      if (action === 'text') {
        expect(mockSockets[0].send).toHaveBeenCalledWith(
          JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
        );
        expect(screen.getByTestId('muted')).toHaveTextContent('true');
      } else {
        expect(mockAudio.attachMicrophone).toHaveBeenCalledTimes(1);
        expect(screen.getByTestId('muted')).toHaveTextContent('false');
      }
      expect(mockTrackEvent.mock.calls.slice(eventCount)).toContainEqual([
        'learner_voice_follow_up_resume',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          learning_mode: 'read',
          surface: 'read_content',
        },
      ]);
      for (const eventName of [
        'learner_voice_follow_up_attempt',
        'learner_voice_follow_up_result',
        'learner_voice_follow_up_session_end',
      ]) {
        expect(
          mockTrackEvent.mock.calls
            .slice(eventCount)
            .filter(([name]) => name === eventName),
        ).toEqual([]);
      }
    },
  );

  it('never replays a paused reply after resume and preserves its played watermark', async () => {
    jest.useFakeTimers();
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onPlaybackProgress: (turnIndex: number, playedBytes: number) => void;
    };
    act(() => {
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Question'],
          outputTranscripts: ['Heard.'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      );
      callbacks.onPlaybackProgress(1, 4);
    });
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    act(() =>
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['Unheard while paused.'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      ),
    );
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'start' })),
    );
    act(() =>
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['Unheard after resume.'],
          audioChunks: [new ArrayBuffer(4)],
          turnComplete: true,
        }),
      ),
    );
    expect(mockAudio.enqueueOutput).toHaveBeenCalledTimes(1);
    await act(async () => jest.advanceTimersByTime(501));
    expect(mockCommitTurn).toHaveBeenCalledWith(
      'session-1',
      expect.objectContaining({
        turn_index: 1,
        user_transcript: 'Question',
        played_answer_transcript: 'Heard.',
        interrupted: true,
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    act(() =>
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['New answer.'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      ),
    );
    expect(mockAudio.enqueueOutput).toHaveBeenCalledTimes(2);
    expect(mockAudio.enqueueOutput).toHaveBeenLastCalledWith(
      expect.any(ArrayBuffer),
      2,
    );
  });

  it('cancels an unsent draft on pause without sending or replaying it at resume', async () => {
    const onTextResult = jest.fn();
    render(<Harness onTextResult={onTextResult} />);
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'pause' })),
    );
    expect(onTextResult).toHaveBeenCalledWith(false);
    act(() => mockSockets[0].open());
    await makeReady();
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'start' })),
    );
    expect(mockSockets[0].send).not.toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
    expect(screen.getByTestId('text-pending')).toHaveTextContent('false');
    expect(mockRequestMicrophone).not.toHaveBeenCalled();
  });

  it('stops a late microphone stream after pause without implicitly re-enabling it', async () => {
    const capture = createDeferred<MediaStream>();
    const stop = jest.fn();
    mockRequestMicrophone.mockReturnValueOnce(capture.promise);
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    const signal = mockRequestMicrophone.mock.calls[0][0] as AbortSignal;
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    expect(signal.aborted).toBe(true);
    await act(async () =>
      capture.resolve({
        getTracks: () => [{ stop }],
      } as unknown as MediaStream),
    );
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'text' })),
    );
    expect(stop).toHaveBeenCalled();
    expect(mockAudio.attachMicrophone).not.toHaveBeenCalled();
    expect(mockRequestMicrophone).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('muted')).toHaveTextContent('true');
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_microphone_result',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        enabled: true,
        outcome: 'cancelled',
        error_code: 'none',
      },
    );
  });

  it('cancels a pending resume when audio ownership is replaced without later sending its draft', async () => {
    const validation = createDeferred<object>();
    const onTextResult = jest.fn();
    render(<Harness onTextResult={onTextResult} />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    mockHeartbeatSession.mockReturnValueOnce(validation.promise);
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    await act(async () => mockRequestExclusive.mock.calls[1][0]());
    expect(onTextResult).toHaveBeenCalledWith(false);
    await act(async () => validation.resolve({}));
    expect(screen.getByTestId('paused')).toHaveTextContent('true');
    expect(screen.getByTestId('muted')).toHaveTextContent('true');
    expect(mockSockets[0].send).not.toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_resume',
      expect.anything(),
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_pause',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        reason: 'audio_replaced',
      },
    );
    expect(mockAudio.pauseOutput).toHaveBeenCalledTimes(2);
    expect(mockEndSession).not.toHaveBeenCalled();
  });

  it('unlocks deliberate input once a paused typed interruption handoff has settled', async () => {
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    act(() =>
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['First answer'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'interrupt-text' }));
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    act(() => {
      mockSockets[0].message(
        serverEvent({ interrupted: true, turnComplete: true }),
      );
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['Discarded answer'],
          audioChunks: [new ArrayBuffer(4)],
          turnComplete: true,
        }),
      );
    });
    expect(screen.getByTestId('text-pending')).toHaveTextContent('false');
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'text' })),
    );
    expect(mockAudio.resumeOutput).toHaveBeenCalledTimes(1);
    expect(
      mockSockets[0].send.mock.calls.filter(
        ([payload]) =>
          payload ===
          JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
      ),
    ).toHaveLength(2);
  });

  it('waits for the final pause watermark before committing an already terminal reply', async () => {
    jest.useFakeTimers();
    const pausedAudio = createDeferred<void>();
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onPlaybackProgress: (turnIndex: number, playedBytes: number) => void;
    };
    act(() => {
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Question'],
          outputTranscripts: ['First.'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      );
      callbacks.onPlaybackProgress(1, 4);
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['Second.'],
          audioChunks: [new ArrayBuffer(4)],
          turnComplete: true,
        }),
      );
      jest.advanceTimersByTime(450);
    });
    mockAudio.pauseOutput.mockReturnValueOnce(pausedAudio.promise);
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    await act(async () => jest.advanceTimersByTime(50));
    expect(mockCommitTurn).not.toHaveBeenCalled();
    await act(async () => {
      callbacks.onPlaybackProgress(1, 8);
      pausedAudio.resolve();
    });
    expect(mockCommitTurn).toHaveBeenCalledWith(
      'session-1',
      expect.objectContaining({
        played_answer_transcript: 'First.Second.',
        interrupted: true,
      }),
    );
  });

  it('pauses on temporary backgrounding and does not resume on visibility alone', async () => {
    const visibility = jest.spyOn(document, 'hidden', 'get');
    try {
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      act(() => {
        visibility.mockReturnValue(true);
        document.dispatchEvent(new Event('visibilitychange'));
        document.dispatchEvent(new Event('visibilitychange'));
      });
      expect(screen.getByTestId('paused')).toHaveTextContent('true');
      act(() => {
        visibility.mockReturnValue(false);
        document.dispatchEvent(new Event('visibilitychange'));
      });
      expect(screen.getByTestId('paused')).toHaveTextContent('true');
      expect(mockAudio.resumeOutput).not.toHaveBeenCalled();
      expect(mockSockets[0].close).not.toHaveBeenCalled();
      expect(mockEndSession).not.toHaveBeenCalled();
      expect(
        mockTrackEvent.mock.calls.filter(
          ([name]) => name === 'learner_voice_follow_up_pause',
        ),
      ).toEqual([
        [
          'learner_voice_follow_up_pause',
          {
            shifu_bid: 'course-1',
            outline_bid: 'lesson-1',
            learning_mode: 'read',
            surface: 'read_content',
            reason: 'page_hidden',
          },
        ],
      ]);
    } finally {
      visibility.mockRestore();
    }
  });

  it.each(['end', 'close', 'pagehide', 'scope', 'unmount'] as const)(
    'fully releases a paused session on %s',
    async action => {
      const { rerender, unmount } = render(<Harness />);
      await startAndOpen();
      await makeReady();
      fireEvent.click(screen.getByRole('button', { name: 'pause' }));
      await act(async () => {
        if (action === 'pagehide') window.dispatchEvent(new Event('pagehide'));
        else if (action === 'scope')
          rerender(<Harness outlineBid='lesson-2' />);
        else if (action === 'unmount') unmount();
        else fireEvent.click(screen.getByRole('button', { name: action }));
      });
      expect(mockSockets[0].close).toHaveBeenCalledTimes(1);
      expect(mockAudio.stop).toHaveBeenCalledTimes(1);
      if (action === 'pagehide' || action === 'unmount') {
        expect(mockFinalizeSession).toHaveBeenCalledTimes(1);
        expect(mockEndSession).not.toHaveBeenCalled();
      } else {
        expect(mockEndSession).toHaveBeenCalledTimes(1);
      }
      expect(
        mockTrackEvent.mock.calls.filter(
          ([name]) => name === 'learner_voice_follow_up_session_end',
        ),
      ).toEqual([
        [
          'learner_voice_follow_up_session_end',
          {
            shifu_bid: 'course-1',
            outline_bid: 'lesson-1',
            learning_mode: 'read',
            surface: 'read_content',
            duration_ms: expect.any(Number),
            had_exchange: false,
            end_reason:
              action === 'pagehide'
                ? 'page_hidden'
                : action === 'scope' || action === 'unmount'
                  ? 'lesson_changed'
                  : `user_${action}`,
          },
        ],
      ]);
    },
  );

  it('lazily renews once after expiry only when old played history has finalized', async () => {
    jest.useFakeTimers();
    const stopAudio = createDeferred<void>();
    const expiresAt = Date.now() + 10_000;
    mockCreateSession.mockResolvedValueOnce(sessionResponse(expiresAt));
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    await makeReady();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onPlaybackProgress: (turnIndex: number, playedBytes: number) => void;
    };
    act(() => {
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['Heard answer'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      );
      callbacks.onPlaybackProgress(1, 4);
    });
    mockAudio.stop.mockReturnValueOnce(stopAudio.promise);
    await act(async () => jest.advanceTimersByTime(10_001));
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('warning')).toHaveTextContent('false');
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    expect(screen.getByTestId('transcripts')).toHaveTextContent('Heard answer');
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    mockCreateSession.mockResolvedValueOnce({
      ...sessionResponse(),
      session_bid: 'session-2',
    });

    fireEvent.click(screen.getByRole('button', { name: 'interrupt-text' }));
    fireEvent.click(screen.getByRole('button', { name: 'interrupt-text' }));
    expect(mockActivateAudio).toHaveBeenCalledTimes(2);
    expect(mockRequestMicrophone).not.toHaveBeenCalled();
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    await act(async () => stopAudio.resolve());
    expect(mockCommitTurn).toHaveBeenCalledWith(
      'session-1',
      expect.objectContaining({
        user_transcript: 'Typed question',
        played_answer_transcript: 'Heard answer',
      }),
    );
    expect(mockEndSession).toHaveBeenCalledWith('session-1', 'timeout');
    expect(mockCreateSession).toHaveBeenCalledTimes(2);
    expect(mockEndSession.mock.invocationCallOrder[0]).toBeLessThan(
      mockCreateSession.mock.invocationCallOrder[1],
    );
    expect(mockReleaseExclusive).not.toHaveBeenCalled();
    act(() => mockSockets[1].open());
    await makeReady(mockSockets[1]);
    expect(
      mockSockets[1].send.mock.calls.filter(
        ([payload]) =>
          payload ===
          JSON.stringify({ realtimeInput: { text: 'Next question' } }),
      ),
    ).toHaveLength(1);
    expect(mockSockets[1].send).not.toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_attempt',
      ),
    ).toHaveLength(2);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_session_end',
      ),
    ).toHaveLength(1);
  });

  it('allows a later explicit renewal after the old binding end request failed', async () => {
    jest.useFakeTimers();
    mockCreateSession.mockResolvedValueOnce(
      sessionResponse(Date.now() + 1_000),
    );
    mockEndSession.mockRejectedValueOnce(
      new Error('private end transport error'),
    );
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    await act(async () => jest.advanceTimersByTime(1_001));
    expect(mockEndSession).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    mockCreateSession.mockResolvedValueOnce({
      ...sessionResponse(),
      session_bid: 'session-2',
    });
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'text' })),
    );
    expect(mockCreateSession).toHaveBeenCalledTimes(2);
    expect(mockSockets).toHaveLength(2);
    act(() => mockSockets[1].open());
    await makeReady(mockSockets[1]);
    expect(mockSockets[1].send).toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
  });

  it('bounds retained-history retries and mints only after an explicit successful retry', async () => {
    jest.useFakeTimers();
    const onTextResult = jest.fn();
    mockCreateSession.mockResolvedValueOnce(
      sessionResponse(Date.now() + 1_000),
    );
    mockCommitTurn.mockReturnValue(new Promise(() => {}));
    mockFinalizeSession.mockReturnValue(new Promise(() => {}));
    render(<Harness onTextResult={onTextResult} />);
    await startAndOpen();
    await makeReady();
    act(() => {
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Previous question'],
          outputTranscripts: ['Previous answer'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      );
      mockActivateAudio.mock.calls[0][0].onPlaybackProgress(1, 4);
    });
    await act(async () => jest.advanceTimersByTime(1_001));
    // The first closing budget expires independently of any new interaction.
    for (let elapsed = 0; elapsed < 25_000; elapsed += 1_000)
      await act(async () => jest.advanceTimersByTime(1_000));
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'text' })),
    );
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    for (let elapsed = 0; elapsed < 25_000; elapsed += 1_000)
      await act(async () => jest.advanceTimersByTime(1_000));
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(onTextResult).toHaveBeenCalledWith(false);
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockRequestMicrophone).not.toHaveBeenCalled();
    expect(mockSockets).toHaveLength(1);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'Typed question',
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'auth_tokens',
    );
    mockFinalizeSession.mockResolvedValue({});
    mockCreateSession.mockResolvedValueOnce({
      ...sessionResponse(),
      session_bid: 'session-2',
    });
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'text' })),
    );
    expect(mockCreateSession).toHaveBeenCalledTimes(2);
    expect(mockFinalizeSession).toHaveBeenLastCalledWith(
      'session-1',
      [
        expect.objectContaining({
          user_transcript: 'Previous question',
          played_answer_transcript: 'Previous answer',
        }),
      ],
      'timeout',
    );
    act(() => mockSockets[1].open());
    await makeReady(mockSockets[1]);
    expect(
      mockSockets[1].send.mock.calls.filter(
        ([payload]) =>
          payload ===
          JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
      ),
    ).toHaveLength(1);
  });

  it('does not start a second closing budget when renewal was requested before finalization failed', async () => {
    jest.useFakeTimers();
    const onTextResult = jest.fn();
    mockCreateSession.mockResolvedValueOnce(
      sessionResponse(Date.now() + 1_000),
    );
    mockCommitTurn.mockReturnValue(new Promise(() => {}));
    mockFinalizeSession.mockReturnValue(new Promise(() => {}));
    render(<Harness onTextResult={onTextResult} />);
    await startAndOpen();
    await makeReady();
    act(() => {
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Previous question'],
          outputTranscripts: ['Previous answer'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      );
      mockActivateAudio.mock.calls[0][0].onPlaybackProgress(1, 4);
    });
    await act(async () => jest.advanceTimersByTime(1_001));
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'text' })),
    );
    expect(screen.getByTestId('state')).toHaveTextContent('connecting');
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    for (let elapsed = 0; elapsed < 25_000; elapsed += 1_000)
      await act(async () => jest.advanceTimersByTime(1_000));

    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(onTextResult).toHaveBeenCalledWith(false);
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockSockets).toHaveLength(1);
    const finalizationRequests = mockFinalizeSession.mock.calls.length;
    await act(async () => jest.advanceTimersByTime(1_000));
    expect(mockFinalizeSession).toHaveBeenCalledTimes(finalizationRequests);

    mockFinalizeSession.mockResolvedValue({});
    mockCreateSession.mockResolvedValueOnce({
      ...sessionResponse(),
      session_bid: 'session-2',
    });
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'text' })),
    );
    expect(mockFinalizeSession).toHaveBeenCalledTimes(finalizationRequests + 1);
    expect(mockCreateSession).toHaveBeenCalledTimes(2);
    act(() => mockSockets[1].open());
    await makeReady(mockSockets[1]);
    expect(
      mockSockets[1].send.mock.calls.filter(
        ([payload]) =>
          payload ===
          JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
      ),
    ).toHaveLength(1);
  });

  it('retires an expired paused credential on the next click even if its background timer was frozen', async () => {
    jest.useFakeTimers();
    const expiresAt = Date.now() + 1_000;
    mockCreateSession.mockResolvedValueOnce(sessionResponse(expiresAt));
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    act(() => jest.setSystemTime(expiresAt + 1));
    mockCreateSession.mockResolvedValueOnce({
      ...sessionResponse(),
      session_bid: 'session-2',
    });
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'microphone' })),
    );
    expect(mockAudio.resumeOutput).not.toHaveBeenCalled();
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(mockCreateSession).toHaveBeenCalledTimes(2);
    expect(mockRequestMicrophone).toHaveBeenCalledTimes(1);
    expect(mockSockets[0].close).toHaveBeenCalledTimes(1);
    expect(mockEndSession).toHaveBeenCalledWith('session-1', 'timeout');
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_resume',
      expect.anything(),
    );
  });

  it('does not resume or start another connection from duplicate input while validation is pending', async () => {
    const validation = createDeferred<object>();
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    mockHeartbeatSession.mockReturnValueOnce(validation.promise);
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    expect(mockAudio.resumeOutput).toHaveBeenCalledTimes(1);
    expect(mockHeartbeatSession).toHaveBeenCalledTimes(1);
    expect(mockRequestMicrophone).not.toHaveBeenCalled();
    await act(async () => validation.resolve({}));
    expect(
      mockSockets[0].send.mock.calls.filter(
        ([payload]) =>
          payload ===
          JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
      ),
    ).toHaveLength(1);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_resume',
      ),
    ).toHaveLength(1);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_text_submit',
      ),
    ).toHaveLength(1);
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
  });

  it('ignores stale resume validation failure after a second pause', async () => {
    const validation = createDeferred<object>();
    const onTextResult = jest.fn();
    render(<Harness onTextResult={onTextResult} />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    mockHeartbeatSession.mockReturnValueOnce(validation.promise);
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'pause' })),
    );
    await act(async () =>
      validation.reject(new Error('private network error')),
    );
    expect(onTextResult).toHaveBeenCalledWith(false);
    expect(screen.getByTestId('paused')).toHaveTextContent('true');
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    expect(mockAudio.stop).not.toHaveBeenCalled();
    expect(mockEndSession).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_resume',
      expect.anything(),
    );
  });

  it('tolerates transient background heartbeat failure and revalidates on deliberate resume', async () => {
    jest.useFakeTimers();
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    mockHeartbeatSession.mockRejectedValueOnce({ status: 503 });
    await act(async () => jest.advanceTimersByTime(15_000));
    expect(screen.getByTestId('paused')).toHaveTextContent('true');
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    expect(mockEndSession).not.toHaveBeenCalled();
    expect(mockSockets[0].close).not.toHaveBeenCalled();
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'text' })),
    );
    expect(mockHeartbeatSession).toHaveBeenCalledTimes(2);
    expect(mockAudio.resumeOutput).toHaveBeenCalledTimes(1);
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
  });

  it.each([{ code: 1001, status: 200 }, { status: 403 }])(
    'does not hide heartbeat authentication rejection while paused (%j)',
    async error => {
      jest.useFakeTimers();
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      fireEvent.click(screen.getByRole('button', { name: 'pause' }));
      mockHeartbeatSession.mockRejectedValueOnce(error);
      await act(async () => jest.advanceTimersByTime(15_000));
      expect(screen.getByTestId('state')).toHaveTextContent('ended');
      expect(screen.getByTestId('paused')).toHaveTextContent('false');
      expect(screen.getByTestId('error')).toHaveTextContent('server_error');
      expect(mockAudio.stop).toHaveBeenCalledTimes(1);
      expect(mockSockets[0].close).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).not.toHaveBeenCalledWith(
        'learner_voice_follow_up_resume',
        expect.anything(),
      );
    },
  );

  it('bounds resume validation failure and returns the pending draft without reconnecting', async () => {
    jest.useFakeTimers();
    const onTextResult = jest.fn();
    render(<Harness onTextResult={onTextResult} />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    mockHeartbeatSession.mockReturnValueOnce(new Promise(() => {}));
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    await act(async () => jest.advanceTimersByTime(5_000));
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(onTextResult).toHaveBeenCalledWith(false);
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockRequestMicrophone).not.toHaveBeenCalled();
    expect(mockSockets[0].send).not.toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_resume',
      expect.anything(),
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'Typed question',
    );
  });

  it.each([false, true])(
    'excludes preview pause and resume analytics (tracking throws=%s)',
    async throwing => {
      if (throwing)
        mockTrackEvent.mockImplementation(() => {
          throw new Error('private tracking error');
        });
      render(<Harness previewMode />);
      await startAndOpen();
      await makeReady();
      fireEvent.click(screen.getByRole('button', { name: 'pause' }));
      await act(async () =>
        fireEvent.click(screen.getByRole('button', { name: 'text' })),
      );
      expect(mockTrackEvent).not.toHaveBeenCalled();
      expect(mockSockets[0].send).toHaveBeenCalledWith(
        JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
      );
    },
  );

  it('keeps pause and resume operational when learner analytics fail', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('private tracking error');
    });
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'text' })),
    );
    expect(screen.getByTestId('paused')).toHaveTextContent('false');
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) =>
          name === 'learner_voice_follow_up_pause' ||
          name === 'learner_voice_follow_up_resume',
      ),
    ).toEqual([
      [
        'learner_voice_follow_up_pause',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          learning_mode: 'read',
          surface: 'read_content',
          reason: 'panel_closed',
        },
      ],
      [
        'learner_voice_follow_up_resume',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          learning_mode: 'read',
          surface: 'read_content',
        },
      ],
    ]);
  });

  it('ignores idle and classroom pause or resume operations without analytics', async () => {
    render(<Harness sessionScope='classroom' />);
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    expect(mockAudio.pauseOutput).not.toHaveBeenCalled();
    expect(mockAudio.resumeOutput).not.toHaveBeenCalled();
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  it('starts only on deliberate input and sends typed questions without microphone access', async () => {
    render(<Harness />);
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockRequestMicrophone).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    await makeReady();
    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_text_submit',
      ),
    ).toEqual([
      [
        'learner_voice_follow_up_text_submit',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          learning_mode: 'read',
          surface: 'read_content',
          submission_method: 'keyboard',
          interrupted: false,
        },
      ],
    ]);
    expect(screen.getByTestId('muted')).toHaveTextContent('true');
    expect(screen.getByTestId('transcripts')).toHaveTextContent(
      'Typed question',
    );
  });

  it.each([false, true])(
    'does not unlock a pending question on old completion (interrupted=%s)',
    async interrupted => {
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      fireEvent.click(screen.getByRole('button', { name: 'text' }));
      act(() =>
        mockSockets[0].message(
          serverEvent({ audioChunks: [new ArrayBuffer(4)] }),
        ),
      );
      fireEvent.click(screen.getByRole('button', { name: 'interrupt-text' }));
      act(() =>
        mockSockets[0].message(
          serverEvent({
            interrupted,
            turnComplete: true,
            audioChunks: [new ArrayBuffer(4)],
          }),
        ),
      );
      expect(screen.getByTestId('text-pending')).toHaveTextContent('true');
      fireEvent.click(screen.getByRole('button', { name: 'text' }));
      const submissions = () =>
        mockTrackEvent.mock.calls.filter(
          ([name]) => name === 'learner_voice_follow_up_text_submit',
        );
      expect(submissions()).toHaveLength(2);
      act(() =>
        mockSockets[0].message(
          serverEvent({ audioChunks: [new ArrayBuffer(4)] }),
        ),
      );
      expect(screen.getByTestId('text-pending')).toHaveTextContent('false');
      fireEvent.click(screen.getByRole('button', { name: 'text' }));
      expect(submissions()).toHaveLength(3);
    },
  );

  it('interrupts typed answers, drops late playback, and saves each question once', async () => {
    jest.useFakeTimers();
    const onTurnCommitted = jest.fn();
    render(<Harness onTurnCommitted={onTurnCommitted} />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    act(() =>
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['Heard'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      ),
    );
    act(() => mockActivateAudio.mock.calls[0][0].onPlaybackProgress(1, 4));
    fireEvent.click(screen.getByRole('button', { name: 'interrupt-text' }));
    expect(mockAudio.interruptPlayback).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'interrupt-text' }));
    const sentText = mockSockets[0].send.mock.calls.filter(([message]) =>
      String(message).includes('realtimeInput'),
    );
    expect(sentText).toHaveLength(2);
    act(() =>
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['Heard then unheard'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      ),
    );
    expect(mockAudio.enqueueOutput).toHaveBeenCalledTimes(1);
    act(() => mockSockets[0].message(serverEvent({ interrupted: true })));
    act(() => mockSockets[0].message(serverEvent({ turnComplete: true })));
    act(() =>
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['Next answer'],
          audioChunks: [new ArrayBuffer(4)],
          turnComplete: true,
        }),
      ),
    );
    act(() => mockActivateAudio.mock.calls[0][0].onPlaybackComplete(2));
    await act(async () => {
      jest.advanceTimersByTime(501);
    });
    expect(mockCommitTurn).toHaveBeenCalledTimes(2);
    expect(mockCommitTurn).toHaveBeenNthCalledWith(
      1,
      'session-1',
      expect.objectContaining({
        turn_index: 1,
        user_transcript: 'Typed question',
        played_answer_transcript: 'Heard',
        interrupted: true,
      }),
    );
    expect(mockCommitTurn).toHaveBeenNthCalledWith(
      2,
      'session-1',
      expect.objectContaining({
        turn_index: 2,
        user_transcript: 'Next question',
        played_answer_transcript: 'Next answer',
      }),
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_text_submit',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        submission_method: 'button',
        interrupted: true,
      },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
      /Typed question|Heard|Next answer|ephemeral/,
    );
  });

  it('keeps keyboard and playback working after optional microphone denial', async () => {
    mockRequestMicrophone.mockRejectedValue(
      new DOMException('Denied', 'NotAllowedError'),
    );
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    expect(mockRequestMicrophone).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mockSockets).toHaveLength(1));
    act(() => mockSockets[0].open());
    await makeReady();
    expect(screen.getByTestId('microphone-error')).toHaveTextContent(
      'microphone_denied',
    );
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_microphone_result',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        enabled: true,
        outcome: 'failed',
        error_code: 'microphone_denied',
      },
    );
  });

  it('cancels a pending permission on editing and releases its late stream exactly once', async () => {
    const permission = createDeferred<MediaStream>();
    const stop = jest.fn();
    mockRequestMicrophone.mockReturnValue(permission.promise);
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    expect(mockRequestMicrophone).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'edit' }));
    await act(async () =>
      permission.resolve({
        getTracks: () => [{ stop }],
      } as unknown as MediaStream),
    );
    expect(stop).toHaveBeenCalledTimes(1);
    expect(mockAudio.attachMicrophone).not.toHaveBeenCalled();
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_microphone_result',
      ),
    ).toEqual([
      [
        'learner_voice_follow_up_microphone_result',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          learning_mode: 'read',
          surface: 'read_content',
          enabled: true,
          outcome: 'cancelled',
          error_code: 'none',
        },
      ],
    ]);
  });

  it.each([false, true])(
    'new input tracking is fail-open (reject=%s)',
    async rejected => {
      mockTrackEvent.mockImplementation(() => {
        if (rejected) return Promise.reject(new Error('analytics blocked'));
        throw new Error('analytics blocked');
      });
      render(<Harness />);
      fireEvent.click(screen.getByRole('button', { name: 'text' }));
      await waitFor(() => expect(mockSockets).toHaveLength(1));
      act(() => mockSockets[0].open());
      await makeReady();
      expect(mockSockets[0].send).toHaveBeenCalledWith(
        JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
      );
      act(() => mockSockets[0].message(serverEvent({ turnComplete: true })));
      fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
      await waitFor(() =>
        expect(mockAudio.attachMicrophone).toHaveBeenCalledTimes(1),
      );
    },
  );

  beforeAll(() => {
    Object.defineProperty(global, 'WebSocket', {
      configurable: true,
      value: MockWebSocket,
    });
  });

  beforeEach(() => {
    jest.useRealTimers();
    jest.clearAllMocks();
    mockTrackEvent.mockReset();
    mockParseServerMessage.mockReset();
    mockSockets.length = 0;
    mockActivateAudio.mockReset().mockResolvedValue(mockAudio);
    mockRequestMicrophone
      .mockReset()
      .mockResolvedValue({ getTracks: () => [{ stop: jest.fn() }] });
    mockCreateSession.mockReset().mockResolvedValue(sessionResponse());
    mockHeartbeatSession.mockReset().mockResolvedValue({});
    mockCommitTurn.mockReset().mockResolvedValue({});
    mockFinalizeSession.mockReset().mockResolvedValue({});
    mockAudio.pauseOutput.mockReset().mockResolvedValue(undefined);
    mockAudio.resumeOutput.mockReset().mockResolvedValue(undefined);
    mockAudio.stop.mockReset().mockResolvedValue(undefined);
    mockAudio.interruptPlayback.mockReset().mockResolvedValue(undefined);
    mockEndSession.mockReset().mockResolvedValue({});
    mockResolveWebSocketUrl.mockReturnValue(
      'wss://generativelanguage.googleapis.com/constrained?access_token=ephemeral',
    );
    mockEncodeAudio.mockImplementation(
      (frame: ArrayBuffer) => `encoded-audio-${frame.byteLength}`,
    );
    mockParseServerMessage.mockReturnValue(null);
  });

  it('starts microphone and token provisioning in the real click stack', async () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'start' }));

    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockCreateSession).toHaveBeenCalledWith('course-1', 'lesson-1', {
      anchor_element_bid: 'element-1',
      preview_mode: false,
      learning_mode: 'read',
      surface: 'read_content',
    });
    expect(mockRequestExclusive).toHaveBeenCalledTimes(1);
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
    expect(mockResolveWebSocketUrl).toHaveBeenCalledWith(
      sessionResponse().websocket_url,
      'auth_tokens/browser-only',
    );
    expect(mockSockets[0].url).toContain('generativelanguage.googleapis.com');
    expect(mockSockets[0].binaryType).toBe('arraybuffer');
  });

  it('accepts binary setup and interruption in order without timing out or duplicating success', async () => {
    jest.useFakeTimers();
    render(<Harness />);
    await startAndOpen();

    let setupFrame!: ArrayBuffer;
    act(() => {
      setupFrame = mockSockets[0].binaryMessage(
        serverEvent({ setupComplete: true }),
      );
    });
    expect(mockParseServerMessage).toHaveBeenCalledWith(setupFrame);
    expect(screen.getByTestId('state')).toHaveTextContent('listening');

    const pcm = new Uint8Array([1, 2, 3, 4]).buffer;
    act(() => {
      mockSockets[0].binaryMessage(
        serverEvent({ audioChunks: [pcm], outputTranscripts: ['Answer'] }),
      );
      mockSockets[0].binaryMessage(serverEvent({ interrupted: true }));
    });
    expect(mockAudio.enqueueOutput).toHaveBeenCalledWith(pcm, 1);
    expect(mockAudio.clearPlayback).toHaveBeenCalledTimes(1);
    expect(mockAudio.enqueueOutput.mock.invocationCallOrder[0]).toBeLessThan(
      mockAudio.clearPlayback.mock.invocationCallOrder[0],
    );
    act(() => jest.advanceTimersByTime(20_000));
    expect(screen.getByTestId('state')).toHaveTextContent('listening');
    expect(mockSockets[0].close).not.toHaveBeenCalled();
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_result',
      ),
    ).toEqual([
      [
        'learner_voice_follow_up_result',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          learning_mode: 'read',
          surface: 'read_content',
          outcome: 'success',
          error_code: 'none',
        },
      ],
    ]);
  });

  it('sends setup first, then history, and reports success only when audio is ready', async () => {
    const pendingAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
    render(<Harness />);
    await startAndOpen();

    expect(JSON.parse(mockSockets[0].send.mock.calls[0][0])).toEqual(
      sessionResponse().setup,
    );
    act(() => mockSockets[0].message(serverEvent({ setupComplete: true })));
    expect(JSON.parse(mockSockets[0].send.mock.calls[1][0])).toEqual(
      sessionResponse().history,
    );
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

  it('rejects invalid local starts without creating an attempt', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start-invalid' }));

    expect(mockActivateAudio).not.toHaveBeenCalled();
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  it('times out stalled audio activation even after Gemini setup completes', async () => {
    jest.useFakeTimers();
    const pendingAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
    render(<Harness />);
    await startAndOpen();
    act(() => mockSockets[0].message(serverEvent({ setupComplete: true })));
    expect(screen.getByTestId('state')).toHaveTextContent('connecting');

    await act(async () => jest.advanceTimersByTime(20_000));

    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect((mockActivateAudio.mock.calls[0][1] as AbortSignal).aborted).toBe(
      true,
    );
    expect(screen.getByTestId('error')).toHaveTextContent('network_error');
    expect(mockSockets[0].close).toHaveBeenCalled();
    expect(mockEndSession).toHaveBeenCalledWith(
      'session-1',
      'connection_error',
    );
    expect(mockReleaseExclusive).toHaveBeenCalled();
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        outcome: 'failed',
        error_code: 'network_error',
      },
    );
    const events = [...mockTrackEvent.mock.calls];
    await act(async () => {
      pendingAudio.resolve(mockAudio);
      await pendingAudio.promise;
    });
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(mockTrackEvent.mock.calls).toEqual(events);
  });

  it.each(['audio', 'gemini'] as const)(
    'clears the connection timeout only after both sides are ready (%s first)',
    async first => {
      jest.useFakeTimers();
      const pendingAudio = createDeferred<typeof mockAudio>();
      mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
      render(<Harness />);
      await startAndOpen();
      const activate = async () => {
        pendingAudio.resolve(mockAudio);
        await pendingAudio.promise;
      };
      await act(async () => {
        if (first === 'audio') await activate();
        else mockSockets[0].message(serverEvent({ setupComplete: true }));
      });
      expect(screen.getByTestId('state')).toHaveTextContent('connecting');
      act(() => jest.advanceTimersByTime(19_000));
      await act(async () => {
        if (first === 'gemini') await activate();
        else mockSockets[0].message(serverEvent({ setupComplete: true }));
      });
      act(() => jest.advanceTimersByTime(20_000));
      expect(screen.getByTestId('state')).toHaveTextContent('listening');
      expect(mockSockets[0].close).not.toHaveBeenCalled();
      expect(
        mockTrackEvent.mock.calls.filter(
          ([name]) => name === 'learner_voice_follow_up_result',
        ),
      ).toEqual([
        [
          'learner_voice_follow_up_result',
          {
            shifu_bid: 'course-1',
            outline_bid: 'lesson-1',
            learning_mode: 'read',
            surface: 'read_content',
            outcome: 'success',
            error_code: 'none',
          },
        ],
      ]);
    },
  );

  it('encodes bounded microphone frames only after setup completes', async () => {
    render(<Harness />);
    await startAndOpen();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onInputFrame: (frame: ArrayBuffer) => void;
    };

    act(() => callbacks.onInputFrame(new ArrayBuffer(1280)));
    expect(mockEncodeAudio).not.toHaveBeenCalled();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    await waitFor(() =>
      expect(mockAudio.attachMicrophone).toHaveBeenCalledTimes(1),
    );
    mockSockets[0].send.mockClear();

    act(() => callbacks.onInputFrame(new ArrayBuffer(1280)));
    expect(mockSockets[0].send).toHaveBeenCalledWith('encoded-audio-1280');

    mockSockets[0].send.mockClear();
    act(() => callbacks.onInputFrame(new ArrayBuffer(8193)));
    expect(mockSockets[0].send).not.toHaveBeenCalled();

    mockSockets[0].bufferedAmount = 7000;
    act(() => callbacks.onInputFrame(new ArrayBuffer(1280)));
    expect(mockSockets[0].send).not.toHaveBeenCalled();
  });

  it('renders transcripts, schedules audio, and clears playback on interruption', async () => {
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    const audio = new ArrayBuffer(4);

    act(() =>
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Question'],
          outputTranscripts: ['Answer'],
          audioChunks: [audio],
        }),
      ),
    );

    expect(screen.getByTestId('transcripts')).toHaveTextContent('Question');
    expect(screen.getByTestId('transcripts')).toHaveTextContent('Answer');
    expect(mockAudio.enqueueOutput).toHaveBeenCalledWith(audio, 1);
    expect(screen.getByTestId('state')).toHaveTextContent('speaking');

    act(() => mockSockets[0].message(serverEvent({ interrupted: true })));
    expect(mockAudio.clearPlayback).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('state')).toHaveTextContent('listening');
  });

  it('silently retires the issued credential without warning or automatic renewal', async () => {
    jest.useFakeTimers();
    const issuedAt = Date.now();
    mockCreateSession.mockResolvedValueOnce(sessionResponse(issuedAt + 60_000));
    render(<Harness />);
    await startAndOpen();
    act(() => jest.advanceTimersByTime(10_000));
    await makeReady();

    act(() => jest.advanceTimersByTime(issuedAt + 29_999 - Date.now()));
    expect(screen.getByTestId('warning')).toHaveTextContent('false');

    act(() => jest.advanceTimersByTime(1));
    expect(screen.getByTestId('warning')).toHaveTextContent('false');

    await act(async () => jest.advanceTimersByTime(30_001));
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('warning')).toHaveTextContent('false');
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    expect(screen.getByTestId('open')).toHaveTextContent('true');
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
  });

  it('commits final client transcripts and usage through authenticated HTTP', async () => {
    const onTurnCommitted = jest.fn();
    render(<Harness onTurnCommitted={onTurnCommitted} />);
    await startAndOpen();
    await makeReady();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onPlaybackComplete: (turnIndex: number) => void;
    };

    act(() =>
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Question'],
          outputTranscripts: ['Answer'],
          audioChunks: [new ArrayBuffer(12)],
          usageMetadata: { totalTokenCount: 7 },
          turnComplete: true,
        }),
      ),
    );
    act(() => callbacks.onPlaybackComplete(1));

    await waitFor(
      () =>
        expect(mockCommitTurn).toHaveBeenCalledWith('session-1', {
          turn_index: 1,
          user_transcript: 'Question',
          played_answer_transcript: 'Answer',
          interrupted: false,
          usage_metadata: { totalTokenCount: 7 },
          latency_ms: expect.any(Number),
        }),
      { timeout: 1500 },
    );
    expect(onTurnCommitted).toHaveBeenCalledWith(
      expect.objectContaining({
        outlineBid: 'lesson-1',
        anchorElementBid: 'element-1',
        turnIndex: 1,
        userTranscript: 'Question',
        assistantTranscript: 'Answer',
      }),
    );
  });

  it.each([true, false])(
    'keeps the original lesson on a delayed commit (started before navigation: %s)',
    async startedBeforeNavigation => {
      jest.useFakeTimers();
      const pendingCommit = createDeferred<object>();
      mockCommitTurn.mockReturnValueOnce(pendingCommit.promise);
      const onTurnCommitted = jest.fn();
      const { rerender } = render(
        <Harness onTurnCommitted={onTurnCommitted} />,
      );
      await startAndOpen();
      await makeReady();
      act(() =>
        mockSockets[0].message(
          serverEvent({
            inputTranscripts: ['Question from the old lesson'],
            turnComplete: true,
          }),
        ),
      );
      if (startedBeforeNavigation) {
        act(() => jest.advanceTimersByTime(500));
        expect(mockCommitTurn).toHaveBeenCalledTimes(1);
      }

      rerender(
        <Harness
          outlineBid='lesson-2'
          onTurnCommitted={onTurnCommitted}
        />,
      );
      await waitFor(() => expect(mockCommitTurn).toHaveBeenCalledTimes(1));
      expect(onTurnCommitted).not.toHaveBeenCalled();

      await act(async () => pendingCommit.resolve({}));

      expect(onTurnCommitted).toHaveBeenCalledWith(
        expect.objectContaining({
          outlineBid: 'lesson-1',
          anchorElementBid: 'element-1',
          turnIndex: 1,
          userTranscript: 'Question from the old lesson',
          assistantTranscript: '',
        }),
      );
    },
  );

  it.each([true, false])(
    'commits confirmed speech before ending the session (turnComplete=%s)',
    async turnComplete => {
      const onTurnCommitted = jest.fn();
      render(<Harness onTurnCommitted={onTurnCommitted} />);
      await startAndOpen();
      await makeReady();
      const callbacks = mockActivateAudio.mock.calls[0][0] as {
        onPlaybackComplete: (turnIndex: number) => void;
      };

      act(() =>
        mockSockets[0].message(
          serverEvent({
            inputTranscripts: ['Question before close'],
            outputTranscripts: ['Answer before close'],
            audioChunks: [new ArrayBuffer(4)],
            turnComplete,
          }),
        ),
      );
      act(() => callbacks.onPlaybackComplete(1));
      fireEvent.click(screen.getByRole('button', { name: 'end' }));

      await waitFor(() =>
        expect(mockCommitTurn).toHaveBeenCalledWith(
          'session-1',
          expect.objectContaining({
            user_transcript: 'Question before close',
            played_answer_transcript: 'Answer before close',
          }),
        ),
      );
      expect(onTurnCommitted).toHaveBeenCalledWith(
        expect.objectContaining({
          outlineBid: 'lesson-1',
          anchorElementBid: 'element-1',
          turnIndex: 1,
          userTranscript: 'Question before close',
          assistantTranscript: 'Answer before close',
        }),
      );
      await waitFor(() =>
        expect(mockEndSession).toHaveBeenCalledWith(
          'session-1',
          'ended_by_user',
        ),
      );
      expect(mockCommitTurn.mock.invocationCallOrder[0]).toBeLessThan(
        mockEndSession.mock.invocationCallOrder[0],
      );
    },
  );

  it.each([true, false])(
    'starts the final batch in the pagehide call stack (turnComplete=%s)',
    async turnComplete => {
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      act(() =>
        mockSockets[0].message(
          serverEvent({
            inputTranscripts: ['Question before leaving'],
          }),
        ),
      );
      act(() =>
        mockSockets[0].message(
          serverEvent({
            outputTranscripts: ['Partial answer before leaving'],
            audioChunks: [new ArrayBuffer(4)],
            turnComplete,
          }),
        ),
      );
      expect(screen.getByTestId('transcripts')).toHaveTextContent(
        'Question before leaving',
      );

      act(() => window.dispatchEvent(new Event('pagehide')));

      expect(mockFinalizeSession).toHaveBeenCalledWith(
        'session-1',
        [
          expect.objectContaining({
            user_transcript: 'Question before leaving',
          }),
        ],
        'page_hidden',
      );
      expect(mockAudio.stop).toHaveBeenCalled();
      expect(mockEndSession).not.toHaveBeenCalled();
    },
  );

  it.each([true, false])(
    'flushes the last playback watermark before saving (turnComplete=%s)',
    async turnComplete => {
      const stoppedAudio = createDeferred<void>();
      mockAudio.stop.mockReturnValueOnce(stoppedAudio.promise);
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      const callbacks = mockActivateAudio.mock.calls[0][0] as {
        onPlaybackProgress: (turnIndex: number, playedBytes: number) => void;
      };
      act(() =>
        mockSockets[0].message(
          serverEvent({
            inputTranscripts: ['Question'],
            outputTranscripts: ['Actually heard answer'],
            audioChunks: [new ArrayBuffer(4)],
            turnComplete,
          }),
        ),
      );
      fireEvent.click(screen.getByRole('button', { name: 'end' }));
      expect(mockCommitTurn).not.toHaveBeenCalled();
      expect(mockReleaseExclusive).not.toHaveBeenCalled();
      expect(mockTrackEvent).not.toHaveBeenCalledWith(
        'learner_voice_follow_up_session_end',
        expect.anything(),
      );
      act(() => callbacks.onPlaybackProgress(1, 4));
      await act(async () => stoppedAudio.resolve());

      expect(mockCommitTurn).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({
          user_transcript: 'Question',
          played_answer_transcript: 'Actually heard answer',
        }),
      );
      expect(mockReleaseExclusive).toHaveBeenCalled();
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'learner_voice_follow_up_session_end',
        expect.objectContaining({ had_exchange: true, end_reason: 'user_end' }),
      );
    },
  );

  it('initiates all unacknowledged turns before the document is discarded', async () => {
    jest.useFakeTimers();
    const firstCommit = createDeferred<object>();
    mockCommitTurn.mockReturnValueOnce(firstCommit.promise);
    const { unmount } = render(<Harness />);
    await startAndOpen();
    await makeReady();
    for (const question of ['First question', 'Second question']) {
      act(() =>
        mockSockets[0].message(
          serverEvent({ inputTranscripts: [question], turnComplete: true }),
        ),
      );
      act(() => jest.advanceTimersByTime(500));
    }
    expect(mockCommitTurn).toHaveBeenCalledTimes(1);
    act(() => window.dispatchEvent(new Event('pagehide')));
    expect(mockFinalizeSession).toHaveBeenCalledWith(
      'session-1',
      [
        expect.objectContaining({
          turn_index: 1,
          user_transcript: 'First question',
        }),
        expect.objectContaining({
          turn_index: 2,
          user_transcript: 'Second question',
        }),
      ],
      'page_hidden',
    );
    unmount();
    expect(mockFinalizeSession).toHaveBeenCalledTimes(1);
    await act(async () => firstCommit.resolve({}));
    expect(mockCommitTurn).toHaveBeenCalledTimes(1);
  });

  it.each(['retry', 'pagehide'])(
    'owns history recovery after transport teardown (%s)',
    async recoveryPath => {
      jest.useFakeTimers();
      mockCommitTurn
        .mockReturnValueOnce(new Promise(() => {}))
        .mockImplementationOnce(() =>
          recoveryPath === 'retry'
            ? Promise.reject(new Error('temporary history failure'))
            : new Promise(() => {}),
        );
      mockFinalizeSession
        .mockRejectedValueOnce(new Error('temporary finalizer failure'))
        .mockRejectedValueOnce(new Error('temporary finalizer failure'))
        .mockRejectedValueOnce(new Error('temporary finalizer failure'));
      const onTurnCommitted = jest.fn();
      const { unmount } = render(<Harness onTurnCommitted={onTurnCommitted} />);
      await startAndOpen();
      await makeReady();
      for (const question of ['First question', 'Second question']) {
        act(() =>
          mockSockets[0].message(
            serverEvent({ inputTranscripts: [question], turnComplete: true }),
          ),
        );
        await act(async () => jest.advanceTimersByTimeAsync(500));
      }
      expect(mockCommitTurn).toHaveBeenCalledTimes(1);
      await act(async () =>
        fireEvent.click(screen.getByRole('button', { name: 'end' })),
      );
      expect(screen.getByTestId('state')).toHaveTextContent('ended');
      expect(mockAudio.stop).toHaveBeenCalled();
      expect(mockSockets[0].close).toHaveBeenCalledTimes(1);
      const heartbeats = mockHeartbeatSession.mock.calls.length;
      await act(async () => jest.advanceTimersByTimeAsync(7000));
      expect(mockFinalizeSession).toHaveBeenCalledTimes(3);
      expect(onTurnCommitted).not.toHaveBeenCalled();

      if (recoveryPath === 'pagehide') {
        act(() => window.dispatchEvent(new Event('pagehide')));
        expect(mockFinalizeSession).toHaveBeenCalledTimes(4);
        await act(async () => jest.advanceTimersByTimeAsync(10_000));
        expect(mockEndSession).not.toHaveBeenCalled();
      } else {
        await act(async () => jest.advanceTimersByTimeAsync(1000));
        expect(
          mockCommitTurn.mock.calls.map(([, report]) => report.turn_index),
        ).toEqual([1, 1, 1, 2]);
        expect(mockEndSession).toHaveBeenCalledTimes(1);
      }
      expect(
        onTurnCommitted.mock.calls.map(([saved]) => saved.turnIndex),
      ).toEqual([1, 2]);
      expect(mockHeartbeatSession).toHaveBeenCalledTimes(heartbeats);
      expect(
        mockTrackEvent.mock.calls.filter(
          ([name]) => name === 'learner_voice_follow_up_session_end',
        ),
      ).toHaveLength(1);
      unmount();
    },
  );

  it('publishes only the played answer checkpoint after interruption', async () => {
    const onTurnCommitted = jest.fn();
    render(<Harness onTurnCommitted={onTurnCommitted} />);
    await startAndOpen();
    await makeReady();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onPlaybackProgress: (turnIndex: number, playedBytes: number) => void;
      onPlaybackComplete: (turnIndex: number) => void;
    };

    act(() =>
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Please explain'],
          outputTranscripts: ['Played portion'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      ),
    );
    act(() => callbacks.onPlaybackProgress(1, 4));
    act(() =>
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['Played portion and unheard continuation'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      ),
    );
    act(() => mockSockets[0].message(serverEvent({ interrupted: true })));
    expect(mockAudio.clearPlayback).toHaveBeenCalled();
    expect(mockAudio.finishOutput).not.toHaveBeenCalled();
    // A stale completion already in the MessagePort queue must not advance
    // the interrupted turn beyond the actual consumed-byte checkpoint.
    act(() => callbacks.onPlaybackComplete(1));

    await waitFor(
      () =>
        expect(mockCommitTurn).toHaveBeenCalledWith(
          'session-1',
          expect.objectContaining({
            user_transcript: 'Please explain',
            played_answer_transcript: 'Played portion',
            interrupted: true,
          }),
        ),
      { timeout: 1_500 },
    );
    expect(onTurnCommitted).toHaveBeenCalledWith(
      expect.objectContaining({
        outlineBid: 'lesson-1',
        anchorElementBid: 'element-1',
        turnIndex: 1,
        userTranscript: 'Please explain',
        assistantTranscript: 'Played portion',
      }),
    );
  });

  it('rechecks the reconciliation deadline when a timer fires before the wall clock reaches it', async () => {
    jest.useFakeTimers();
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    act(() =>
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Question'],
          outputTranscripts: ['Answer'],
        }),
      ),
    );
    act(() => mockSockets[0].message(serverEvent({ interrupted: true })));
    const clock = jest.spyOn(Date, 'now').mockReturnValue(Date.now() + 499);
    act(() => jest.advanceTimersByTime(500));
    clock.mockRestore();
    expect(mockCommitTurn).not.toHaveBeenCalled();
    await act(async () => jest.advanceTimersByTime(1));
    expect(mockCommitTurn).toHaveBeenCalledWith(
      'session-1',
      expect.objectContaining({
        user_transcript: 'Question',
        interrupted: true,
      }),
    );
    expect(mockCommitTurn).toHaveBeenCalledTimes(1);
  });

  it('submits consecutive history only after earlier playback has settled', async () => {
    jest.useFakeTimers();
    let nextIndex = 1;
    mockCommitTurn.mockImplementation(async (_session, report) => {
      if (report.turn_index !== nextIndex) {
        throw new Error('Nonconsecutive history report');
      }
      nextIndex += 1;
      return {};
    });
    const onTurnCommitted = jest.fn();
    render(<Harness onTurnCommitted={onTurnCommitted} />);
    await startAndOpen();
    await makeReady();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onPlaybackComplete: (turnIndex: number) => void;
    };
    act(() =>
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['First question'],
          outputTranscripts: ['First answer'],
          audioChunks: [new ArrayBuffer(8)],
          turnComplete: true,
        }),
      ),
    );
    await act(async () => jest.advanceTimersByTime(600));
    act(() =>
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Second question'],
          outputTranscripts: ['Second answer'],
          turnComplete: true,
        }),
      ),
    );
    await act(async () => jest.advanceTimersByTime(500));
    expect(mockCommitTurn).not.toHaveBeenCalled();
    expect(mockAudio.stop).not.toHaveBeenCalled();

    await act(async () => callbacks.onPlaybackComplete(1));
    expect(
      mockCommitTurn.mock.calls.map(([, turn]) => turn.turn_index),
    ).toEqual([1, 2]);
    expect(onTurnCommitted.mock.calls.map(([turn]) => turn.turnIndex)).toEqual([
      1, 2,
    ]);
    expect(screen.getByTestId('state')).not.toHaveTextContent('ended');
    expect(mockTrackEvent.mock.calls.map(([name]) => name)).toEqual([
      'learner_voice_follow_up_attempt',
      'learner_voice_follow_up_result',
    ]);
  });

  it('keeps a failed history commit in the retry-only voice UI', async () => {
    mockCommitTurn.mockRejectedValueOnce(new Error('storage unavailable'));
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onPlaybackComplete: (turnIndex: number) => void;
    };
    act(() =>
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Question'],
          outputTranscripts: ['Answer'],
          audioChunks: [new ArrayBuffer(4)],
          turnComplete: true,
        }),
      ),
    );
    act(() => callbacks.onPlaybackComplete(1));

    await waitFor(
      () => expect(screen.getByTestId('state')).toHaveTextContent('ended'),
      { timeout: 1500 },
    );
    expect(screen.getByTestId('error')).toHaveTextContent('server_error');
    expect(screen.getByTestId('retryable')).toHaveTextContent('false');
  });

  it('stops on transcript backpressure without losing the newest completed turn', async () => {
    jest.useFakeTimers();
    const firstCommit = createDeferred<object>();
    mockCommitTurn.mockReturnValueOnce(firstCommit.promise);
    const onTurnCommitted = jest.fn();
    render(<Harness onTurnCommitted={onTurnCommitted} />);
    await startAndOpen();
    await makeReady();
    const callbacks = mockActivateAudio.mock.calls[0][0];
    for (const turnIndex of [1, 2, 3]) {
      await act(async () => {
        mockSockets[0].message(
          serverEvent({
            inputTranscripts: [`Question ${turnIndex} ${'x'.repeat(25_000)}`],
            outputTranscripts: [`Answer ${turnIndex}`],
            audioChunks: [new ArrayBuffer(4)],
            turnComplete: true,
          }),
        );
        callbacks.onPlaybackComplete(turnIndex);
        jest.advanceTimersByTime(500);
      });
    }
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('error')).toHaveTextContent('server_error');
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(mockCommitTurn).toHaveBeenCalledTimes(1);
    await act(async () => firstCommit.resolve({}));
    expect(
      mockCommitTurn.mock.calls.map(([, report]) => report.turn_index),
    ).toEqual([1, 2, 3]);
    expect(
      onTurnCommitted.mock.calls.map(([report]) => report.turnIndex),
    ).toEqual([1, 2, 3]);
    expect(mockFinalizeSession).not.toHaveBeenCalled();
    expect(mockEndSession).toHaveBeenCalledWith(
      'session-1',
      'connection_error',
    );
  });

  it('ends the input stream when muted without opening a text fallback', async () => {
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    await waitFor(() =>
      expect(mockAudio.attachMicrophone).toHaveBeenCalledTimes(1),
    );
    mockSockets[0].send.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'mute' }));

    expect(mockAudio.stopMicrophone).toHaveBeenCalledTimes(1);
    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { audioStreamEnd: true } }),
    );
    expect(screen.getByTestId('muted')).toHaveTextContent('true');
  });

  it('resumes GoAway on a second Google socket with the same constrained token', async () => {
    jest.useFakeTimers();
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    act(() =>
      mockSockets[0].message(
        serverEvent({ resumptionHandle: 'resume-handle', resumable: true }),
      ),
    );
    act(() => mockSockets[0].message(serverEvent({ goAway: true })));

    expect(mockSockets).toHaveLength(2);
    expect(mockSockets[1].binaryType).toBe('arraybuffer');
    expect(mockResolveWebSocketUrl).toHaveBeenLastCalledWith(
      sessionResponse().websocket_url,
      'auth_tokens/browser-only',
    );
    act(() => mockSockets[1].open());
    const resumedSetup = JSON.parse(mockSockets[1].send.mock.calls[0][0]);
    expect(resumedSetup.setup.sessionResumption).toEqual({
      handle: 'resume-handle',
    });
    expect(resumedSetup.setup).not.toHaveProperty('historyConfig');
    act(() =>
      mockSockets[1].binaryMessage(serverEvent({ setupComplete: true })),
    );
    expect(mockSockets[1].send).toHaveBeenCalledTimes(1);
    act(() => jest.advanceTimersByTime(20_000));
    expect(screen.getByTestId('state')).toHaveTextContent('listening');
    expect(mockSockets[1].close).not.toHaveBeenCalled();
  });

  it('resumes one unexpected close after a typed answer without restarting the session', async () => {
    jest.useFakeTimers();
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    await act(async () => {
      mockSockets[0].message(
        serverEvent({
          outputTranscripts: ['First answer'],
          audioChunks: [new ArrayBuffer(4)],
          turnComplete: true,
        }),
      );
      mockActivateAudio.mock.calls[0][0].onPlaybackComplete(1);
      jest.advanceTimersByTime(500);
    });
    act(() =>
      mockSockets[0].message(
        serverEvent({ resumptionHandle: 'safe-handle', resumable: true }),
      ),
    );
    const staleMessage = mockSockets[0].onmessage!;
    act(() => mockSockets[0].fail());
    expect(mockAudio.stop).not.toHaveBeenCalled();
    act(() => mockSockets[0].serverClose());
    expect(screen.getByTestId('state')).toHaveTextContent('reconnecting');
    expect(mockSockets).toHaveLength(2);
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockRequestMicrophone).not.toHaveBeenCalled();
    const parsedMessages = mockParseServerMessage.mock.calls.length;
    act(() => staleMessage(new MessageEvent('message', { data: '{}' })));
    expect(mockParseServerMessage).toHaveBeenCalledTimes(parsedMessages);
    act(() => mockSockets[1].open());
    expect(JSON.parse(mockSockets[1].send.mock.calls[0][0]).setup).toEqual(
      expect.objectContaining({ sessionResumption: { handle: 'safe-handle' } }),
    );
    await makeReady(mockSockets[1]);
    fireEvent.click(screen.getByRole('button', { name: 'interrupt-text' }));
    await act(async () => {
      mockSockets[1].message(
        serverEvent({
          outputTranscripts: ['Second answer'],
          audioChunks: [new ArrayBuffer(4)],
          turnComplete: true,
        }),
      );
      mockActivateAudio.mock.calls[0][0].onPlaybackComplete(2);
      jest.advanceTimersByTime(500);
    });
    expect(
      mockCommitTurn.mock.calls.map(([, turn]) => turn.turn_index),
    ).toEqual([1, 2]);
    act(() => mockSockets[1].serverClose());
    expect(mockSockets).toHaveLength(2);
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    await act(async () => {});
    for (const event of ['attempt', 'result', 'session_end']) {
      expect(
        mockTrackEvent.mock.calls.filter(
          ([name]) => name === `learner_voice_follow_up_${event}`,
        ),
      ).toHaveLength(1);
    }
  });

  it.each([1000, 1002, 1007, 1008, 1009])(
    'does not resume terminal or policy close code %s',
    async code => {
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      act(() =>
        mockSockets[0].message(
          serverEvent({ resumptionHandle: 'safe-handle', resumable: true }),
        ),
      );
      act(() => mockSockets[0].serverClose(code));
      expect(mockSockets).toHaveLength(1);
      expect(screen.getByTestId('state')).toHaveTextContent('ended');
    },
  );

  it('keeps the original expiry and manual microphone state while resuming', async () => {
    jest.useFakeTimers();
    const issuedAt = Date.now();
    mockCreateSession.mockResolvedValueOnce(sessionResponse(issuedAt + 60_000));
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    await act(async () => {});
    expect(screen.getByTestId('muted')).toHaveTextContent('false');
    act(() =>
      mockSockets[0].message(
        serverEvent({ resumptionHandle: 'safe-handle', resumable: true }),
      ),
    );
    await act(async () => jest.advanceTimersByTime(10_000));
    act(() => mockSockets[0].serverClose());
    act(() =>
      mockActivateAudio.mock.calls[0][0].onInputFrame(new ArrayBuffer(1280)),
    );
    expect(mockSockets[1].send).not.toHaveBeenCalled();
    act(() => mockSockets[1].open());
    await makeReady(mockSockets[1]);
    expect(screen.getByTestId('muted')).toHaveTextContent('false');
    expect(mockRequestMicrophone).toHaveBeenCalledTimes(1);
    act(() =>
      mockActivateAudio.mock.calls[0][0].onInputFrame(new ArrayBuffer(1280)),
    );
    expect(mockEncodeAudio).toHaveBeenCalledTimes(1);
    await act(async () =>
      jest.advanceTimersByTime(issuedAt + 30_000 - Date.now()),
    );
    expect(screen.getByTestId('warning')).toHaveTextContent('false');
    await act(async () =>
      jest.advanceTimersByTime(issuedAt + 60_001 - Date.now()),
    );
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('end-reason')).toHaveTextContent('timeout');
  });

  it.each(['invalidated', 'awaiting_response'])(
    'does not resume a stale handle while %s',
    async scenario => {
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      act(() =>
        mockSockets[0].message(
          serverEvent({ resumptionHandle: 'old-handle', resumable: true }),
        ),
      );
      if (scenario === 'invalidated') {
        act(() => mockSockets[0].message(serverEvent({ resumable: false })));
      } else {
        fireEvent.click(screen.getByRole('button', { name: 'text' }));
      }
      act(() => mockSockets[0].serverClose());
      expect(mockSockets).toHaveLength(1);
      expect(screen.getByTestId('state')).toHaveTextContent('ended');
    },
  );

  it.each(['network', 'unavailable', 'stalled'])(
    'keeps the conversation through one transient heartbeat failure: %s',
    async failure => {
      jest.useFakeTimers();
      mockHeartbeatSession.mockImplementationOnce(() =>
        failure === 'stalled'
          ? new Promise(() => {})
          : Promise.reject(
              failure === 'unavailable'
                ? Object.assign(new Error('Unavailable'), {
                    status: 503,
                    code: 503,
                  })
                : new TypeError('Network unavailable'),
            ),
      );
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      await act(async () => jest.advanceTimersByTime(15_000));
      if (failure === 'stalled') {
        await act(async () => jest.advanceTimersByTime(5_000));
      }
      expect(screen.getByTestId('state')).toHaveTextContent('listening');
      expect(mockAudio.stop).not.toHaveBeenCalled();
      await act(async () => jest.advanceTimersByTime(1_000));
      expect(mockHeartbeatSession).toHaveBeenCalledTimes(2);
      expect(screen.getByTestId('state')).toHaveTextContent('listening');
      await act(async () => jest.advanceTimersByTime(15_000));
      expect(mockHeartbeatSession).toHaveBeenCalledTimes(3);
      expect(mockCreateSession).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent.mock.calls.map(([name]) => name)).toEqual([
        'learner_voice_follow_up_attempt',
        'learner_voice_follow_up_result',
      ]);
      fireEvent.click(screen.getByRole('button', { name: 'end' }));
      await act(async () => jest.advanceTimersByTime(30_000));
      expect(mockHeartbeatSession).toHaveBeenCalledTimes(3);
    },
  );

  it('ends before the lease expires when both heartbeat requests stall', async () => {
    jest.useFakeTimers();
    mockCreateSession.mockResolvedValueOnce({
      ...sessionResponse(),
      heartbeat_interval_ms: 30_000,
    });
    mockHeartbeatSession.mockImplementation(() => new Promise(() => {}));
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    await act(async () => jest.advanceTimersByTime(30_000));
    await act(async () => jest.advanceTimersByTime(5_000));
    await act(async () => jest.advanceTimersByTime(1_000));
    await act(async () => jest.advanceTimersByTime(5_000));
    expect(mockHeartbeatSession).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_session_end',
      expect.objectContaining({ duration_ms: 41_000 }),
    );
  });

  it('cancels a scheduled heartbeat retry when the panel closes', async () => {
    jest.useFakeTimers();
    mockHeartbeatSession.mockRejectedValueOnce(
      new TypeError('Network unavailable'),
    );
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    await act(async () => jest.advanceTimersByTime(15_000));
    fireEvent.click(screen.getByRole('button', { name: 'close' }));
    await act(async () => jest.advanceTimersByTime(30_000));
    expect(mockHeartbeatSession).toHaveBeenCalledTimes(1);
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
  });

  it('does not spend the lease retry budget waiting for a slow successful heartbeat response', async () => {
    jest.useFakeTimers();
    const response = createDeferred<object>();
    mockCreateSession.mockResolvedValueOnce({
      ...sessionResponse(),
      heartbeat_interval_ms: 30_000,
    });
    mockHeartbeatSession
      .mockReturnValueOnce(response.promise)
      .mockImplementation(() => new Promise(() => {}));
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    await act(async () => jest.advanceTimersByTime(30_000));
    await act(async () => jest.advanceTimersByTime(4_500));
    await act(async () => response.resolve({}));
    await act(async () => jest.advanceTimersByTime(25_500));
    expect(mockHeartbeatSession).toHaveBeenCalledTimes(2);
    await act(async () => jest.advanceTimersByTime(5_000));
    await act(async () => jest.advanceTimersByTime(1_000));
    await act(async () => jest.advanceTimersByTime(5_000));
    expect(mockHeartbeatSession).toHaveBeenCalledTimes(3);
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_session_end',
      expect.objectContaining({ duration_ms: 71_000 }),
    );
  });

  it.each([
    { code: 1001, status: 200 },
    { code: 1004, status: 200 },
    { code: 1005, status: 200 },
    { code: 4000, status: 200 },
    { status: 403 },
  ])('stops immediately on a rejected heartbeat: %j', async failure => {
    jest.useFakeTimers();
    mockHeartbeatSession.mockRejectedValueOnce(failure);
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    await act(async () => jest.advanceTimersByTime(15_000));
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    await act(async () => jest.advanceTimersByTime(5_000));
    expect(mockHeartbeatSession).toHaveBeenCalledTimes(1);
  });

  it('preserves the connection failure when sending again during credential cooldown', async () => {
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    act(() => mockSockets[0].serverClose());
    expect(screen.getByTestId('error')).toHaveTextContent('network_error');
    const eventCount = mockTrackEvent.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    expect(screen.getByTestId('error')).toHaveTextContent('network_error');
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledTimes(eventCount);
  });

  it('sends a question queued during GoAway only after resumed setup is ready', async () => {
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    act(() =>
      mockSockets[0].message(
        serverEvent({
          resumptionHandle: 'resume-handle',
          resumable: true,
          goAway: true,
        }),
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'text' }));
    expect(mockSockets[1].send).not.toHaveBeenCalled();
    act(() => mockSockets[1].open());
    expect(mockSockets[1].send).toHaveBeenCalledTimes(1);
    await act(async () =>
      mockSockets[1].message(serverEvent({ setupComplete: true })),
    );
    expect(mockSockets[1].send).toHaveBeenLastCalledWith(
      JSON.stringify({ realtimeInput: { text: 'Typed question' } }),
    );
    expect(mockRequestMicrophone).not.toHaveBeenCalled();
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_attempt',
      ),
    ).toHaveLength(1);
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_text_submit',
      ),
    ).toHaveLength(1);
  });

  it('tracks each explicit microphone operation once and drops capture after editing', async () => {
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    fireEvent.click(screen.getByRole('button', { name: 'microphone' }));
    await waitFor(() =>
      expect(mockAudio.attachMicrophone).toHaveBeenCalledTimes(1),
    );
    fireEvent.click(screen.getByRole('button', { name: 'mute' }));
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_microphone_result',
      ),
    ).toEqual([
      [
        'learner_voice_follow_up_microphone_result',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          learning_mode: 'read',
          surface: 'read_content',
          enabled: true,
          outcome: 'success',
          error_code: 'none',
        },
      ],
      [
        'learner_voice_follow_up_microphone_result',
        {
          shifu_bid: 'course-1',
          outline_bid: 'lesson-1',
          learning_mode: 'read',
          surface: 'read_content',
          enabled: false,
          outcome: 'success',
          error_code: 'none',
        },
      ],
    ]);
    mockSockets[0].send.mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'edit' }));
    act(() =>
      mockActivateAudio.mock.calls[0][0].onInputFrame(new ArrayBuffer(1280)),
    );
    expect(mockSockets[0].send).not.toHaveBeenCalled();
  });

  it('still times out a resumed socket that never acknowledges setup', async () => {
    jest.useFakeTimers();
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    act(() =>
      mockSockets[0].message(
        serverEvent({
          resumptionHandle: 'resume-handle',
          resumable: true,
          goAway: true,
        }),
      ),
    );
    act(() => mockSockets[1].open());
    await act(async () => jest.advanceTimersByTime(20_000));
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(mockSockets[1].close).toHaveBeenCalled();
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_result',
      ),
    ).toHaveLength(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_session_end',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        duration_ms: 20_000,
        had_exchange: false,
        end_reason: 'connection_error',
      },
    );
  });

  it('fails the attempt if the replacement socket closes before setup', async () => {
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    act(() =>
      mockSockets[0].message(
        serverEvent({ resumptionHandle: 'resume-handle', resumable: true }),
      ),
    );
    act(() => mockSockets[0].message(serverEvent({ goAway: true })));
    act(() => mockSockets[1].serverClose());

    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('error')).toHaveTextContent('network_error');
    expect(screen.getByTestId('retryable')).toHaveTextContent('false');
  });

  it('stops the microphone when provisioning stalls and safely retires a late credential', async () => {
    jest.useFakeTimers();
    const deferredSession =
      createDeferred<ReturnType<typeof sessionResponse>>();
    mockCreateSession.mockReturnValueOnce(deferredSession.promise);
    const expiresAt = Date.now() + 60_000;
    render(<Harness />);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'start' }));
    });
    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockAudio.stop).not.toHaveBeenCalled();

    await act(async () => jest.advanceTimersByTime(20_000));
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('error')).toHaveTextContent('network_error');
    expect(screen.getByTestId('retryable')).toHaveTextContent('false');
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(mockReleaseExclusive).toHaveBeenCalled();
    expect(mockSockets).toHaveLength(0);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        outcome: 'failed',
        error_code: 'network_error',
      },
    );
    const eventCount = mockTrackEvent.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    expect(mockCreateSession).toHaveBeenCalledTimes(1);

    await act(async () => deferredSession.resolve(sessionResponse(expiresAt)));
    expect(mockSockets).toHaveLength(0);
    expect(mockEndSession).toHaveBeenCalledWith(
      'session-1',
      'client_disconnected',
    );
    expect(screen.getByTestId('retry-at')).toHaveTextContent(
      String(expiresAt + 1),
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(eventCount);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'auth_tokens',
    );
    act(() => jest.advanceTimersByTime(expiresAt + 1 - Date.now()));
    expect(screen.getByTestId('retryable')).toHaveTextContent('true');
  });

  it('clears the provisioning timeout on close and stops audio that activates late', async () => {
    jest.useFakeTimers();
    const deferredAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(deferredAudio.promise);
    mockCreateSession.mockReturnValueOnce(new Promise(() => {}));
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    fireEvent.click(screen.getByRole('button', { name: 'close' }));
    const eventCount = mockTrackEvent.mock.calls.length;
    await act(async () => {
      deferredAudio.resolve(mockAudio);
      jest.advanceTimersByTime(20_000);
    });
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('open')).toHaveTextContent('false');
    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledTimes(eventCount);
    expect(mockSockets).toHaveLength(0);
  });

  it('defers retry until the credential reservation expires after setup stalls', async () => {
    jest.useFakeTimers();
    const expiresAt = Date.now() + 60_000;
    mockCreateSession.mockResolvedValueOnce(sessionResponse(expiresAt));
    render(<Harness />);
    await startAndOpen();

    act(() => {
      jest.advanceTimersByTime(20_000);
    });

    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('error')).toHaveTextContent('network_error');
    expect(screen.getByTestId('retryable')).toHaveTextContent('false');
    expect(screen.getByTestId('retry-at')).toHaveTextContent(
      String(expiresAt + 1),
    );
    const eventCount = mockTrackEvent.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledTimes(eventCount);
    await act(async () => {
      await Promise.resolve();
    });
    expect(mockAudio.stop).toHaveBeenCalled();
    expect(mockEndSession).toHaveBeenCalledWith(
      'session-1',
      'connection_error',
    );
    act(() => jest.advanceTimersByTime(expiresAt + 1 - Date.now()));
    expect(screen.getByTestId('retryable')).toHaveTextContent('true');
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    await act(async () =>
      fireEvent.click(screen.getByRole('button', { name: 'retry' })),
    );
    expect(mockCreateSession).toHaveBeenCalledTimes(2);
  });

  it('surfaces microphone denial and allows an explicit retry', async () => {
    mockCreateSession.mockRejectedValueOnce(new Error('no credential issued'));
    mockActivateAudio.mockRejectedValueOnce(
      new DOMException('denied', 'NotAllowedError'),
    );
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));

    await waitFor(() =>
      expect(screen.getByTestId('error')).toHaveTextContent(
        'microphone_denied',
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    await waitFor(() => expect(mockActivateAudio).toHaveBeenCalledTimes(2));
    expect(
      mockTrackEvent.mock.calls.filter(
        ([eventName]) => eventName === 'learner_voice_follow_up_attempt',
      ),
    ).toHaveLength(2);
  });

  it('classifies capacity rejection and backs off explicit retries without another microphone request', async () => {
    jest.useFakeTimers();
    const rejectedAt = Date.now();
    mockCreateSession.mockRejectedValueOnce(
      Object.assign(new Error('private server message'), { code: 4018 }),
    );
    render(<Harness />);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'start' }));
    });

    expect(screen.getByTestId('error')).toHaveTextContent('capacity_exceeded');
    expect(screen.getByTestId('retryable')).toHaveTextContent('false');
    expect(screen.getByTestId('retry-at')).toHaveTextContent(
      String(rejectedAt + 30_000),
    );
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        outcome: 'failed',
        error_code: 'capacity_exceeded',
      },
    );
    expect(mockAudio.stop).toHaveBeenCalled();
    const eventCount = mockTrackEvent.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledTimes(eventCount);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      'private server message',
    );
    act(() => jest.advanceTimersByTime(30_000));
    expect(screen.getByTestId('retryable')).toHaveTextContent('true');
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    });
    expect(mockCreateSession).toHaveBeenCalledTimes(2);
    expect(mockActivateAudio).toHaveBeenCalledTimes(2);
  });

  it.each([2001, '4018', undefined])(
    'does not infer capacity from raw error text or an unknown code %s',
    async code => {
      mockCreateSession.mockRejectedValueOnce(
        Object.assign(new Error('live_follow_up_capacity private error'), {
          code,
        }),
      );
      render(<Harness />);
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: 'start' }));
      });
      expect(screen.getByTestId('error')).toHaveTextContent(
        'session_create_failed',
      );
      expect(screen.getByTestId('retryable')).toHaveTextContent('true');
      expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
        'private error',
      );
    },
  );

  it('releases audio and ends the direct control-plane session on lesson changes', async () => {
    const { rerender } = render(<Harness learningMode='read' />);
    await startAndOpen();
    await makeReady();

    rerender(
      <Harness
        learningMode='listen'
        sessionScope='listen'
      />,
    );

    await waitFor(() => expect(mockAudio.stop).toHaveBeenCalled());
    expect(mockEndSession).toHaveBeenCalledWith('session-1', 'lesson_changed');
    expect(mockReleaseExclusive).toHaveBeenCalled();
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('end-reason')).toHaveTextContent(
      'lesson_changed',
    );
  });

  it.each([
    { outlineBid: 'lesson-2' },
    { shifuBid: 'course-2' },
    { learningMode: 'listen' as const },
    { previewMode: true },
    { sessionScope: 'classroom' as const },
  ])(
    'clears a failed attempt and its retry target after %j',
    async destination => {
      mockCreateSession.mockRejectedValueOnce(
        new Error('no credential issued'),
      );
      mockActivateAudio.mockRejectedValueOnce(
        new DOMException('denied', 'NotAllowedError'),
      );
      const { rerender } = render(<Harness />);
      fireEvent.click(screen.getByRole('button', { name: 'start' }));
      await waitFor(() =>
        expect(screen.getByTestId('error')).toHaveTextContent(
          'microphone_denied',
        ),
      );
      expect(screen.getByTestId('open')).toHaveTextContent('true');
      expect(screen.getByTestId('retryable')).toHaveTextContent('true');
      const events = [...mockTrackEvent.mock.calls];

      rerender(
        <Harness
          {...destination}
          anchorElementBid='element-2'
        />,
      );

      expect(screen.getByTestId('open')).toHaveTextContent('false');
      expect(screen.getByTestId('error')).toBeEmptyDOMElement();
      expect(screen.getByTestId('transcripts')).toHaveTextContent('[]');
      expect(screen.getByTestId('retryable')).toHaveTextContent('false');
      expect(screen.getByTestId('retry-at')).toHaveTextContent('null');
      fireEvent.click(screen.getByRole('button', { name: 'retry' }));
      expect(mockActivateAudio).toHaveBeenCalledTimes(1);
      expect(mockCreateSession).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent.mock.calls).toEqual(events);
    },
  );

  it('clears failed conversation state on navigation without bypassing credential admission', async () => {
    jest.useFakeTimers();
    const expiresAt = Date.now() + 15 * 60_000;
    mockCreateSession.mockResolvedValueOnce(sessionResponse(expiresAt));
    const { rerender } = render(<Harness />);
    await startAndOpen();
    await makeReady();
    act(() => {
      mockSockets[0].message(
        serverEvent({
          inputTranscripts: ['Private question'],
          outputTranscripts: ['Private answer'],
          audioChunks: [new ArrayBuffer(4)],
        }),
      );
    });
    fireEvent.click(screen.getByRole('button', { name: 'mute' }));
    await act(async () => mockSockets[0].fail());
    expect(screen.getByTestId('transcripts')).toHaveTextContent(
      'Private question',
    );
    expect(screen.getByTestId('error')).toHaveTextContent('websocket_failed');

    rerender(
      <Harness
        outlineBid='lesson-2'
        anchorElementBid='element-2'
      />,
    );

    expect(screen.getByTestId('open')).toHaveTextContent('false');
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    expect(screen.getByTestId('transcripts')).toHaveTextContent('[]');
    expect(screen.getByTestId('muted')).toHaveTextContent('true');
    expect(screen.getByTestId('retryable')).toHaveTextContent('false');
    expect(screen.getByTestId('retry-at')).toHaveTextContent('null');
    const events = [...mockTrackEvent.mock.calls];
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    expect(screen.getByTestId('error')).toBeEmptyDOMElement();
    expect(screen.getByTestId('transcripts')).toHaveTextContent('[]');
    expect(screen.getByTestId('retry-at')).toHaveTextContent(
      String(expiresAt + 1),
    );
    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent.mock.calls).toEqual(events);

    act(() => jest.advanceTimersByTime(expiresAt + 1 - Date.now()));
    mockCreateSession.mockResolvedValueOnce(sessionResponse());
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    });
    expect(mockCreateSession).toHaveBeenNthCalledWith(
      2,
      'course-1',
      'lesson-2',
      {
        anchor_element_bid: 'element-2',
        preview_mode: false,
        learning_mode: 'read',
        surface: 'read_content',
      },
    );
    expect(mockTrackEvent).toHaveBeenLastCalledWith(
      'learner_voice_follow_up_attempt',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-2',
        learning_mode: 'read',
        surface: 'read_content',
      },
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_session_end',
      ),
    ).toHaveLength(1);
  });

  it('does not revive a failed retry timer after navigating away', async () => {
    jest.useFakeTimers();
    mockCreateSession.mockRejectedValueOnce(
      Object.assign(new Error('capacity'), { code: 4018 }),
    );
    const { rerender } = render(<Harness />);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'start' }));
    });
    expect(screen.getByTestId('error')).toHaveTextContent('capacity_exceeded');
    rerender(<Harness outlineBid='lesson-2' />);
    act(() => jest.advanceTimersByTime(30_000));
    expect(screen.getByTestId('open')).toHaveTextContent('false');
    expect(screen.getByTestId('retryable')).toHaveTextContent('false');
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    expect(mockCreateSession).toHaveBeenCalledTimes(1);
    expect(mockActivateAudio).toHaveBeenCalledTimes(1);
  });

  it.each([{ previewMode: true }, { sessionScope: 'classroom' as const }])(
    'does not emit learner analytics for excluded scope %j',
    async options => {
      render(<Harness {...options} />);
      if ('sessionScope' in options && options.sessionScope === 'classroom') {
        fireEvent.click(screen.getByRole('button', { name: 'start' }));
        expect(mockCreateSession).not.toHaveBeenCalled();
        expect(mockTrackEvent).not.toHaveBeenCalled();
        return;
      }
      await startAndOpen();
      await makeReady();
      fireEvent.click(screen.getByRole('button', { name: 'end' }));

      expect(mockTrackEvent).not.toHaveBeenCalled();
      await waitFor(() =>
        expect(mockEndSession).toHaveBeenCalledWith(
          'session-1',
          'ended_by_user',
        ),
      );
    },
  );

  it.each([
    {
      shifuBid: 'course-2',
      outlineBid: 'lesson-2',
      learningMode: 'listen' as const,
    },
    { previewMode: true },
    { sessionScope: 'classroom' as const },
  ])(
    'keeps connected analytics bound to the originating attempt after %j',
    async destination => {
      jest.useFakeTimers();
      const { rerender, unmount } = render(<Harness />);
      await startAndOpen();
      await makeReady();
      act(() => jest.advanceTimersByTime(1250));

      rerender(<Harness {...destination} />);
      expect(screen.getByTestId('end-reason')).toHaveTextContent(
        'lesson_changed',
      );
      await waitFor(() =>
        expect(mockTrackEvent).toHaveBeenCalledWith(
          'learner_voice_follow_up_session_end',
          {
            shifu_bid: 'course-1',
            outline_bid: 'lesson-1',
            learning_mode: 'read',
            surface: 'read_content',
            duration_ms: 1250,
            had_exchange: false,
            end_reason: 'lesson_changed',
          },
        ),
      );
      unmount();
      expect(
        mockTrackEvent.mock.calls.filter(
          ([name]) => name === 'learner_voice_follow_up_session_end',
        ),
      ).toHaveLength(1);
    },
  );

  it('attributes cancellation before connection to the original learner attempt', async () => {
    const { rerender } = render(<Harness />);
    await startAndOpen();
    rerender(
      <Harness
        shifuBid='course-2'
        outlineBid='lesson-2'
        learningMode='listen'
        previewMode
      />,
    );

    expect(mockTrackEvent).toHaveBeenCalledWith(
      'learner_voice_follow_up_result',
      {
        shifu_bid: 'course-1',
        outline_bid: 'lesson-1',
        learning_mode: 'read',
        surface: 'read_content',
        outcome: 'cancelled',
        error_code: 'none',
      },
    );
    expect(
      mockTrackEvent.mock.calls.filter(
        ([name]) => name === 'learner_voice_follow_up_result',
      ),
    ).toHaveLength(1);
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'learner_voice_follow_up_session_end',
      expect.anything(),
    );
  });

  it('does not turn a preview attempt into learner analytics after navigation', async () => {
    const { rerender } = render(<Harness previewMode />);
    await startAndOpen();
    await makeReady();
    rerender(<Harness />);
    await waitFor(() => expect(mockEndSession).toHaveBeenCalled());
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  it.each(['end', 'close', 'pagehide'] as const)(
    'counts a completed exchange before a pending HTTP acknowledgement on %s',
    async action => {
      jest.useFakeTimers();
      const pendingCommit = createDeferred<object>();
      mockCommitTurn.mockReturnValueOnce(pendingCommit.promise);
      const { unmount } = render(<Harness />);
      await startAndOpen();
      await makeReady();
      const callbacks = mockActivateAudio.mock.calls[0][0] as {
        onPlaybackComplete: (turnIndex: number) => void;
      };
      act(() =>
        mockSockets[0].message(
          serverEvent({
            inputTranscripts: ['Private question'],
            outputTranscripts: ['Private answer'],
            audioChunks: [new ArrayBuffer(4)],
            turnComplete: true,
          }),
        ),
      );
      act(() => callbacks.onPlaybackComplete(1));
      act(() => jest.advanceTimersByTime(500));
      expect(mockCommitTurn).toHaveBeenCalledTimes(1);
      if (action === 'pagehide') {
        act(() => window.dispatchEvent(new Event('pagehide')));
      } else {
        fireEvent.click(screen.getByRole('button', { name: action }));
      }
      await waitFor(() =>
        expect(mockTrackEvent).toHaveBeenCalledWith(
          'learner_voice_follow_up_session_end',
          {
            shifu_bid: 'course-1',
            outline_bid: 'lesson-1',
            learning_mode: 'read',
            surface: 'read_content',
            duration_ms: 500,
            had_exchange: true,
            end_reason:
              action === 'pagehide' ? 'page_hidden' : `user_${action}`,
          },
        ),
      );
      unmount();
      await act(async () => pendingCommit.resolve({}));
      expect(
        mockTrackEvent.mock.calls.filter(
          ([name]) => name === 'learner_voice_follow_up_session_end',
        ),
      ).toHaveLength(1);
      expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
        'Private',
      );
    },
  );

  it.each([false, true])(
    'does not count a usage-only or unheard turn as an exchange (has input: %s)',
    async hasInput => {
      const onTurnCommitted = jest.fn();
      render(<Harness onTurnCommitted={onTurnCommitted} />);
      await startAndOpen();
      await makeReady();
      act(() =>
        mockSockets[0].message(
          serverEvent({
            inputTranscripts: hasInput ? ['Question'] : [],
            outputTranscripts: hasInput ? ['Unheard answer'] : [],
            audioChunks: hasInput ? [new ArrayBuffer(4)] : [],
            usageMetadata: { totalTokenCount: 5 },
            turnComplete: true,
          }),
        ),
      );
      fireEvent.click(screen.getByRole('button', { name: 'end' }));
      await waitFor(() =>
        expect(mockTrackEvent).toHaveBeenCalledWith(
          'learner_voice_follow_up_session_end',
          expect.objectContaining({ had_exchange: false }),
        ),
      );
      await waitFor(() => expect(mockEndSession).toHaveBeenCalled());
      if (hasInput) {
        expect(onTurnCommitted).toHaveBeenCalledWith(
          expect.objectContaining({
            userTranscript: 'Question',
            assistantTranscript: '',
          }),
        );
      } else {
        expect(onTurnCommitted).not.toHaveBeenCalled();
      }
    },
  );

  it.each(['sync', 'async'])(
    'keeps conversation and cleanup working when analytics fail %s',
    async failure => {
      mockTrackEvent.mockImplementation(() => {
        if (failure === 'sync') {
          throw new Error('tracking unavailable');
        }
        return Promise.reject(new Error('tracking unavailable'));
      });
      render(<Harness />);
      await startAndOpen();
      await makeReady();
      fireEvent.click(screen.getByRole('button', { name: 'end' }));
      await waitFor(() =>
        expect(mockEndSession).toHaveBeenCalledWith(
          'session-1',
          'ended_by_user',
        ),
      );
      expect(mockAudio.stop).toHaveBeenCalled();
      expect(mockReleaseExclusive).toHaveBeenCalled();
      expect(screen.getByTestId('state')).toHaveTextContent('ended');
    },
  );

  it('fails closed when Gemini rejects the constrained setup', async () => {
    render(<Harness />);
    await startAndOpen();
    act(() => mockSockets[0].message(serverEvent({ upstreamError: true })));

    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('error')).toHaveTextContent('server_error');
    expect(screen.getByTestId('retryable')).toHaveTextContent('false');
  });

  it('stops stale audio that resolves after the dialog closes', async () => {
    const pendingAudio = createDeferred<typeof mockAudio>();
    mockActivateAudio.mockReturnValueOnce(pendingAudio.promise);
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    fireEvent.click(screen.getByRole('button', { name: 'close' }));

    await act(async () => {
      pendingAudio.resolve(mockAudio);
      await pendingAudio.promise;
    });

    expect(mockAudio.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('state')).toHaveTextContent('ended');
  });

  it('releases a server session that resolves after the attempt was closed', async () => {
    const pendingSession = createDeferred<ReturnType<typeof sessionResponse>>();
    mockCreateSession.mockReturnValueOnce(pendingSession.promise);
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    fireEvent.click(screen.getByRole('button', { name: 'close' }));

    await act(async () => {
      pendingSession.resolve(sessionResponse());
      await pendingSession.promise;
    });

    expect(mockSockets).toHaveLength(0);
    expect(mockEndSession).toHaveBeenCalledWith(
      'session-1',
      'client_disconnected',
    );
  });
});
