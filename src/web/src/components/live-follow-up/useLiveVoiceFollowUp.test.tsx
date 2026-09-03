import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import type { GeminiLiveServerEvent } from '@/lib/liveVoiceFollowUp';

import { useLiveVoiceFollowUp } from './useLiveVoiceFollowUp';

const mockTrackEvent = jest.fn();
const mockCreateSession = jest.fn();
const mockHeartbeatSession = jest.fn();
const mockCommitTurn = jest.fn();
const mockEndSession = jest.fn();
const mockResolveWebSocketUrl = jest.fn();
const mockEncodeAudio = jest.fn();
const mockParseServerMessage = jest.fn();
const mockActivateAudio = jest.fn();
const mockRequestExclusive = jest.fn();
const mockReleaseExclusive = jest.fn();

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

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  createLiveFollowUpSession: (...args: unknown[]) => mockCreateSession(...args),
  heartbeatLiveFollowUpSession: (...args: unknown[]) =>
    mockHeartbeatSession(...args),
  commitLiveFollowUpTurn: (...args: unknown[]) => mockCommitTurn(...args),
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
  bufferedAmount = 0;
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

  message(message: GeminiLiveServerEvent) {
    mockParseServerMessage.mockReturnValueOnce(message);
    this.onmessage?.(new MessageEvent('message', { data: '{}' }));
  }

  fail() {
    this.onerror?.();
  }

  serverClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
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

const sessionResponse = () => ({
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
  expires_at: '2030-01-01T00:15:00Z',
  new_session_expires_at: '2030-01-01T00:00:30Z',
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
  previewMode = false,
  learningMode = 'read',
  sessionScope = learningMode,
  onTurnCommitted,
}: {
  shifuBid?: string;
  previewMode?: boolean;
  learningMode?: 'read' | 'listen';
  sessionScope?: 'read' | 'listen' | 'classroom';
  onTurnCommitted?: Parameters<
    typeof useLiveVoiceFollowUp
  >[0]['onTurnCommitted'];
}) => {
  const controller = useLiveVoiceFollowUp({
    shifuBid,
    outlineBid: 'lesson-1',
    previewMode,
    learningMode,
    sessionScope,
    onTurnCommitted,
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
      <span data-testid='warning'>{String(controller.warning)}</span>
      <span data-testid='muted'>{String(controller.muted)}</span>
      <span data-testid='error'>{controller.errorCode || ''}</span>
      <span data-testid='retryable'>{String(controller.retryable)}</span>
      <span data-testid='transcripts'>
        {JSON.stringify(controller.transcripts)}
      </span>
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
  beforeAll(() => {
    Object.defineProperty(global, 'WebSocket', {
      configurable: true,
      value: MockWebSocket,
    });
  });

  beforeEach(() => {
    jest.useRealTimers();
    jest.clearAllMocks();
    mockSockets.length = 0;
    mockActivateAudio.mockResolvedValue(mockAudio);
    mockCreateSession.mockResolvedValue(sessionResponse());
    mockHeartbeatSession.mockResolvedValue({});
    mockCommitTurn.mockResolvedValue({});
    mockEndSession.mockResolvedValue({});
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

  it('encodes bounded microphone frames only after setup completes', async () => {
    render(<Harness />);
    await startAndOpen();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onInputFrame: (frame: ArrayBuffer) => void;
    };

    act(() => callbacks.onInputFrame(new ArrayBuffer(1280)));
    expect(mockEncodeAudio).not.toHaveBeenCalled();
    await makeReady();
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
    expect(onTurnCommitted).toHaveBeenCalledWith({
      anchorElementBid: 'element-1',
      turnIndex: 1,
      userTranscript: 'Question',
      assistantTranscript: 'Answer',
    });
  });

  it('commits a completed reconciliation-window turn before ending the session', async () => {
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
          turnComplete: true,
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
    expect(onTurnCommitted).toHaveBeenCalledWith({
      anchorElementBid: 'element-1',
      turnIndex: 1,
      userTranscript: 'Question before close',
      assistantTranscript: 'Answer before close',
    });
    await waitFor(() =>
      expect(mockEndSession).toHaveBeenCalledWith('session-1', 'ended_by_user'),
    );
    expect(mockCommitTurn.mock.invocationCallOrder[0]).toBeLessThan(
      mockEndSession.mock.invocationCallOrder[0],
    );
  });

  it('starts the final turn report before audio teardown on pagehide', async () => {
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
          turnComplete: true,
        }),
      ),
    );
    expect(screen.getByTestId('transcripts')).toHaveTextContent(
      'Question before leaving',
    );

    act(() => window.dispatchEvent(new Event('pagehide')));

    expect(mockCommitTurn).toHaveBeenCalledWith(
      'session-1',
      expect.objectContaining({
        user_transcript: 'Question before leaving',
      }),
    );
    expect(mockCommitTurn.mock.invocationCallOrder[0]).toBeLessThan(
      mockAudio.stop.mock.invocationCallOrder[0],
    );
    await waitFor(() =>
      expect(mockEndSession).toHaveBeenCalledWith('session-1', 'page_hidden'),
    );
  });

  it('publishes only the played answer checkpoint after interruption', async () => {
    const onTurnCommitted = jest.fn();
    render(<Harness onTurnCommitted={onTurnCommitted} />);
    await startAndOpen();
    await makeReady();
    const callbacks = mockActivateAudio.mock.calls[0][0] as {
      onPlaybackProgress: (turnIndex: number, playedBytes: number) => void;
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
    expect(onTurnCommitted).toHaveBeenCalledWith({
      anchorElementBid: 'element-1',
      turnIndex: 1,
      userTranscript: 'Please explain',
      assistantTranscript: 'Played portion',
    });
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
    expect(screen.getByTestId('retryable')).toHaveTextContent('true');
  });

  it('ends the input stream when muted without opening a text fallback', async () => {
    render(<Harness />);
    await startAndOpen();
    await makeReady();
    mockSockets[0].send.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'mute' }));

    expect(mockAudio.setMuted).toHaveBeenLastCalledWith(true);
    expect(mockSockets[0].send).toHaveBeenCalledWith(
      JSON.stringify({ realtimeInput: { audioStreamEnd: true } }),
    );
    expect(screen.getByTestId('muted')).toHaveTextContent('true');
  });

  it('resumes GoAway on a second Google socket with the same constrained token', async () => {
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
    act(() => mockSockets[1].message(serverEvent({ setupComplete: true })));
    expect(mockSockets[1].send).toHaveBeenCalledTimes(1);
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
    expect(screen.getByTestId('retryable')).toHaveTextContent('true');
  });

  it('fails retryably when Gemini never acknowledges setup', async () => {
    jest.useFakeTimers();
    render(<Harness />);
    await startAndOpen();

    act(() => {
      jest.advanceTimersByTime(20_000);
    });

    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('error')).toHaveTextContent('network_error');
    expect(screen.getByTestId('retryable')).toHaveTextContent('true');
    await act(async () => {
      await Promise.resolve();
    });
    expect(mockAudio.stop).toHaveBeenCalled();
    expect(mockEndSession).toHaveBeenCalledWith(
      'session-1',
      'connection_error',
    );
  });

  it('surfaces microphone denial and allows an explicit retry', async () => {
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
  });

  it('does not emit learner analytics for teacher preview', async () => {
    render(<Harness previewMode />);
    await startAndOpen();
    await makeReady();
    fireEvent.click(screen.getByRole('button', { name: 'end' }));

    expect(mockTrackEvent).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(mockEndSession).toHaveBeenCalledWith('session-1', 'ended_by_user'),
    );
  });

  it('fails closed when Gemini rejects the constrained setup', async () => {
    render(<Harness />);
    await startAndOpen();
    act(() => mockSockets[0].message(serverEvent({ upstreamError: true })));

    expect(screen.getByTestId('state')).toHaveTextContent('ended');
    expect(screen.getByTestId('error')).toHaveTextContent('server_error');
    expect(screen.getByTestId('retryable')).toHaveTextContent('true');
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
