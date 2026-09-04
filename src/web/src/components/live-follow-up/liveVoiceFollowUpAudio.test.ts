import { LiveVoiceFollowUpAudio } from './liveVoiceFollowUpAudio';

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  LIVE_FOLLOW_UP_AUDIO_WORKLET_PATH: '/worklets/live-follow-up-audio.js',
}));

type MockPort = {
  onmessage: ((event: MessageEvent) => void) | null;
  postMessage: jest.Mock;
};

describe('LiveVoiceFollowUpAudio', () => {
  const originalAudioContext = Object.getOwnPropertyDescriptor(
    window,
    'AudioContext',
  );
  const originalAudioWorkletNode = Object.getOwnPropertyDescriptor(
    globalThis,
    'AudioWorkletNode',
  );
  const originalMediaDevices = Object.getOwnPropertyDescriptor(
    navigator,
    'mediaDevices',
  );

  afterEach(() => {
    const restore = (
      target: object,
      name: string,
      descriptor: PropertyDescriptor | undefined,
    ) => {
      if (descriptor) {
        Object.defineProperty(target, name, descriptor);
      } else {
        delete (target as Record<string, unknown>)[name];
      }
    };
    restore(window, 'AudioContext', originalAudioContext);
    restore(globalThis, 'AudioWorkletNode', originalAudioWorkletNode);
    restore(navigator, 'mediaDevices', originalMediaDevices);
  });

  it('waits for the final playback progress ACK before closing audio', async () => {
    const trackStop = jest.fn();
    const stream = {
      getTracks: () => [{ stop: trackStop }],
    } as unknown as MediaStream;
    const source = {
      connect: jest.fn(),
      disconnect: jest.fn(),
    };
    const gain = {
      connect: jest.fn(),
      disconnect: jest.fn(),
      gain: { value: 1 },
    };
    const close = jest.fn().mockResolvedValue(undefined);
    class MockAudioContext {
      state: AudioContextState = 'running';
      destination = {} as AudioDestinationNode;
      audioWorklet = { addModule: jest.fn().mockResolvedValue(undefined) };
      resume = jest.fn().mockResolvedValue(undefined);
      close = close;
      createMediaStreamSource = jest.fn(() => source);
      createGain = jest.fn(() => gain);
    }

    const ports = new Map<string, MockPort>();
    class MockAudioWorkletNode {
      port: MockPort;
      connect = jest.fn();
      disconnect = jest.fn();

      constructor(_context: AudioContext, processorName: string) {
        this.port = { onmessage: null, postMessage: jest.fn() };
        ports.set(processorName, this.port);
      }
    }

    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: MockAudioContext,
    });
    Object.defineProperty(globalThis, 'AudioWorkletNode', {
      configurable: true,
      value: MockAudioWorkletNode,
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: jest.fn().mockResolvedValue(stream) },
    });

    const onPlaybackProgress = jest.fn();
    const audio = await LiveVoiceFollowUpAudio.activate({
      onInputFrame: jest.fn(),
      onPlaybackProgress,
      onPlaybackComplete: jest.fn(),
    });
    const playbackPort = ports.get('live-follow-up-playback');
    expect(playbackPort).toBeDefined();

    const stopPromise = audio.stop();
    expect(trackStop).toHaveBeenCalledTimes(1);
    expect(playbackPort?.postMessage).toHaveBeenCalledWith({
      type: 'flush_and_clear',
      requestId: 1,
    });
    expect(close).not.toHaveBeenCalled();

    playbackPort?.onmessage?.(
      new MessageEvent('message', {
        data: {
          type: 'playback_progress',
          turnIndex: 2,
          playedBytes: 480,
        },
      }),
    );
    playbackPort?.onmessage?.(
      new MessageEvent('message', {
        data: { type: 'flush_complete', requestId: 1 },
      }),
    );
    await stopPromise;

    expect(onPlaybackProgress).toHaveBeenCalledWith(2, 480);
    expect(close).toHaveBeenCalledTimes(1);
  });

  it.each(['microphone', 'resume', 'worklet', 'worklet_throw'] as const)(
    'releases incomplete audio activation resources (%s)',
    async pendingStage => {
      let finishPending!: (stream: MediaStream) => void;
      const pending = new Promise<MediaStream>(resolve => {
        finishPending = resolve;
      });
      const trackStop = jest.fn();
      const stream = {
        getTracks: () => [{ stop: trackStop }],
      } as unknown as MediaStream;
      const resume = jest.fn(() =>
        pendingStage === 'resume' ? pending : Promise.resolve(),
      );
      const addModule = jest.fn(() => {
        if (pendingStage === 'worklet_throw') throw new Error('worklet failed');
        return pendingStage === 'worklet' ? pending : Promise.resolve();
      });
      const getUserMedia = jest.fn(() =>
        pendingStage === 'microphone' ? pending : Promise.resolve(stream),
      );
      const close = jest.fn().mockResolvedValue(undefined);
      const createMediaStreamSource = jest.fn();
      class PendingAudioContext {
        resume = resume;
        audioWorklet = { addModule };
        close = close;
        createMediaStreamSource = createMediaStreamSource;
      }
      Object.defineProperty(window, 'AudioContext', {
        configurable: true,
        value: PendingAudioContext,
      });
      Object.defineProperty(navigator, 'mediaDevices', {
        configurable: true,
        value: { getUserMedia },
      });
      const controller = new AbortController();
      const activation = LiveVoiceFollowUpAudio.activate(
        {
          onInputFrame: jest.fn(),
          onPlaybackProgress: jest.fn(),
          onPlaybackComplete: jest.fn(),
        },
        controller.signal,
      );
      // These still run before activate returns, preserving user activation.
      expect(resume).toHaveBeenCalledTimes(1);
      expect(getUserMedia).toHaveBeenCalledTimes(1);
      expect(addModule).toHaveBeenCalledTimes(1);
      const rejected = expect(activation).rejects.toMatchObject({
        name: pendingStage === 'worklet_throw' ? 'Error' : 'AbortError',
      });

      controller.abort();
      await rejected;

      expect(close).toHaveBeenCalledTimes(1);
      expect(trackStop).toHaveBeenCalledTimes(
        pendingStage === 'microphone' ? 0 : 1,
      );
      finishPending(stream);
      await pending;
      expect(trackStop).toHaveBeenCalledTimes(1);
      expect(createMediaStreamSource).not.toHaveBeenCalled();
    },
  );
});
