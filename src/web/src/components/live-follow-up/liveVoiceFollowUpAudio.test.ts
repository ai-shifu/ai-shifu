import { LiveVoiceFollowUpAudio } from './liveVoiceFollowUpAudio';

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  LIVE_FOLLOW_UP_AUDIO_WORKLET_PATH: '/worklets/live-follow-up-audio.js',
}));

type MockPort = {
  onmessage: ((event: MessageEvent) => void) | null;
  postMessage: jest.Mock;
};

describe('LiveVoiceFollowUpAudio', () => {
  it('cancels microphone acquisition and releases a stream granted after cancellation', async () => {
    let grant!: (stream: MediaStream) => void;
    const getUserMedia = jest.fn(
      () =>
        new Promise<MediaStream>(resolve => {
          grant = resolve;
        }),
    );
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });
    const abort = new AbortController();
    const pending = LiveVoiceFollowUpAudio.requestMicrophone(abort.signal);
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    abort.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    const stop = jest.fn();
    grant({ getTracks: () => [{ stop }] } as unknown as MediaStream);
    await Promise.resolve();
    expect(stop).toHaveBeenCalledTimes(1);
  });
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
    jest.useRealTimers();
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

  const createPausableAudio = async () => {
    const trackStop = jest.fn();
    const source = { connect: jest.fn(), disconnect: jest.fn() };
    const gains: Array<{
      gain: { value: number };
      connect: jest.Mock;
      disconnect: jest.Mock;
    }> = [];
    const context = {
      state: 'running' as AudioContextState,
      destination: {},
      audioWorklet: { addModule: jest.fn().mockResolvedValue(undefined) },
      createGain: jest.fn(() => {
        const gain = {
          gain: { value: 1 },
          connect: jest.fn(),
          disconnect: jest.fn(),
        };
        gains.push(gain);
        return gain;
      }),
      createMediaStreamSource: jest.fn(() => source),
      resume: jest.fn<Promise<void>, []>(),
      suspend: jest.fn<Promise<void>, []>(),
      close: jest.fn<Promise<void>, []>(),
    };
    context.resume.mockImplementation(async () => {
      context.state = 'running';
    });
    context.suspend.mockImplementation(async () => {
      context.state = 'suspended';
    });
    context.close.mockImplementation(async () => {
      context.state = 'closed';
    });
    const construct = jest.fn(() => context);
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: construct,
    });
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
    Object.defineProperty(globalThis, 'AudioWorkletNode', {
      configurable: true,
      value: MockAudioWorkletNode,
    });
    const getUserMedia = jest.fn();
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });
    const onPlaybackProgress = jest.fn();
    const audio = await LiveVoiceFollowUpAudio.activate({
      onInputFrame: jest.fn(),
      onPlaybackProgress,
      onPlaybackComplete: jest.fn(),
    });
    const port = ports.get('live-follow-up-playback')!;
    const acknowledgeFlush = () => {
      const flush = port.postMessage.mock.calls
        .map(([message]) => message)
        .filter(message => message.type === 'flush_and_clear')
        .at(-1);
      port.onmessage?.(
        new MessageEvent('message', {
          data: { type: 'flush_complete', requestId: flush.requestId },
        }),
      );
    };
    return {
      audio,
      context,
      gains,
      construct,
      port,
      acknowledgeFlush,
      getUserMedia,
      trackStop,
      onPlaybackProgress,
    };
  };

  it('bounds native close after releasing capture and disconnecting output', async () => {
    jest.useFakeTimers();
    const { audio, context, gains, acknowledgeFlush, trackStop } =
      await createPausableAudio();
    audio.attachMicrophone({
      getTracks: () => [{ stop: trackStop }],
    } as unknown as MediaStream);
    context.close.mockReturnValue(new Promise(() => {}));
    const stopped = audio.stop();
    expect(trackStop).toHaveBeenCalledTimes(1);
    expect(gains[0].gain.value).toBe(0);
    acknowledgeFlush();
    await jest.advanceTimersByTimeAsync(1_000);
    await expect(stopped).resolves.toBeUndefined();
    expect(context.close).toHaveBeenCalledTimes(1);
    expect(gains[0].disconnect).toHaveBeenCalledTimes(1);
  });

  it('pauses immediately and resumes playback in the click stack without opening the microphone', async () => {
    const {
      audio,
      context,
      gains,
      construct,
      port,
      acknowledgeFlush,
      getUserMedia,
      trackStop,
      onPlaybackProgress,
    } = await createPausableAudio();
    audio.attachMicrophone({
      getTracks: () => [{ stop: trackStop }],
    } as unknown as MediaStream);
    const pause = audio.pauseOutput();
    expect(trackStop).toHaveBeenCalledTimes(1);
    expect(gains[0].gain.value).toBe(0);
    audio.enqueueOutput(new ArrayBuffer(4), 1);
    expect(port.postMessage).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: 'audio' }),
      expect.anything(),
    );
    port.onmessage?.(
      new MessageEvent('message', {
        data: { type: 'playback_progress', turnIndex: 1, playedBytes: 4 },
      }),
    );
    acknowledgeFlush();
    await pause;
    expect(onPlaybackProgress).toHaveBeenCalledWith(1, 4);
    expect(context.suspend).toHaveBeenCalledTimes(1);
    const resume = audio.resumeOutput();
    expect(context.resume).toHaveBeenCalledTimes(2);
    await resume;
    expect(gains[0].gain.value).toBe(1);
    audio.enqueueOutput(new ArrayBuffer(4), 2);
    expect(port.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: 'audio', turnIndex: 2 }),
      expect.any(Array),
    );
    expect(construct).toHaveBeenCalledTimes(1);
    expect(context.audioWorklet.addModule).toHaveBeenCalledTimes(1);
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(context.close).not.toHaveBeenCalled();
  });

  it('does not let a pending pause suspend an immediately resumed context', async () => {
    const { audio, context, gains, acknowledgeFlush } =
      await createPausableAudio();
    const paused = audio.pauseOutput();
    const resumed = audio.resumeOutput();
    expect(context.resume).toHaveBeenCalledTimes(2);
    acknowledgeFlush();
    await Promise.all([paused, resumed]);
    expect(context.suspend).not.toHaveBeenCalled();
    expect(gains[0].gain.value).toBe(1);
  });

  it('keeps output paused if the panel closes again while resume is pending', async () => {
    const { audio, context, gains, acknowledgeFlush } =
      await createPausableAudio();
    const firstPause = audio.pauseOutput();
    acknowledgeFlush();
    await firstPause;
    let completeResume!: () => void;
    context.resume.mockImplementationOnce(
      () =>
        new Promise<void>(resolve => {
          completeResume = resolve;
        }),
    );
    const resumed = audio.resumeOutput();
    const rejected = expect(resumed).rejects.toMatchObject({
      name: 'AbortError',
    });
    const secondPause = audio.pauseOutput();
    acknowledgeFlush();
    await secondPause;
    completeResume();
    await rejected;
    expect(gains[0].gain.value).toBe(0);
  });

  it('bounds pause even when the worklet and suspended browser stop acknowledging', async () => {
    jest.useFakeTimers();
    const { audio, context, gains } = await createPausableAudio();
    context.suspend.mockImplementationOnce(() => new Promise(() => {}));
    const paused = audio.pauseOutput();
    await jest.advanceTimersByTimeAsync(100);
    expect(context.suspend).toHaveBeenCalledTimes(1);
    await jest.advanceTimersByTimeAsync(1_000);
    await expect(paused).resolves.toBeUndefined();
    expect(gains[0].gain.value).toBe(0);
    expect(context.close).not.toHaveBeenCalled();
  });

  it('rejects a stalled resume without unmuting on a late native resolution', async () => {
    jest.useFakeTimers();
    const { audio, context, gains, acknowledgeFlush } =
      await createPausableAudio();
    const paused = audio.pauseOutput();
    acknowledgeFlush();
    await paused;
    let completeResume!: () => void;
    context.resume.mockImplementationOnce(
      () =>
        new Promise<void>(resolve => {
          completeResume = resolve;
        }),
    );
    const resumed = audio.resumeOutput();
    const rejected = expect(resumed).rejects.toMatchObject({
      name: 'LiveVoiceAudioUnavailableError',
    });
    await jest.advanceTimersByTimeAsync(5_000);
    await rejected;
    completeResume();
    await Promise.resolve();
    expect(gains[0].gain.value).toBe(0);
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
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
    const capture = LiveVoiceFollowUpAudio.requestMicrophone(
      new AbortController().signal,
    );
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(1);
    audio.attachMicrophone(await capture);
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

  it.each(['resume', 'worklet', 'worklet_throw'] as const)(
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
      const getUserMedia = jest.fn(() => Promise.resolve(stream));
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
      expect(getUserMedia).not.toHaveBeenCalled();
      expect(addModule).toHaveBeenCalledTimes(1);
      const rejected = expect(activation).rejects.toMatchObject({
        name: pendingStage === 'worklet_throw' ? 'Error' : 'AbortError',
      });

      controller.abort();
      await rejected;

      expect(close).toHaveBeenCalledTimes(1);
      expect(trackStop).not.toHaveBeenCalled();
      finishPending(stream);
      await pending;
      expect(trackStop).not.toHaveBeenCalled();
      expect(createMediaStreamSource).not.toHaveBeenCalled();
    },
  );
});
