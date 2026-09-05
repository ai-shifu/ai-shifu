type WorkletPort = {
  onmessage: ((event: { data: Record<string, unknown> }) => void) | null;
  postMessage: jest.Mock;
};

type WorkletProcessorInstance = {
  port: WorkletPort;
  process: (inputs: Float32Array[][], outputs: Float32Array[][]) => boolean;
  samples?: number[];
  turnIndexes?: number[];
  readOffset?: number;
};

type WorkletProcessorConstructor = new () => WorkletProcessorInstance;

describe('Live follow-up AudioWorklet', () => {
  const originalAudioWorkletProcessor = Object.getOwnPropertyDescriptor(
    globalThis,
    'AudioWorkletProcessor',
  );
  const originalRegisterProcessor = Object.getOwnPropertyDescriptor(
    globalThis,
    'registerProcessor',
  );
  const originalSampleRate = Object.getOwnPropertyDescriptor(
    globalThis,
    'sampleRate',
  );
  let processors: Record<string, WorkletProcessorConstructor>;

  beforeEach(() => {
    processors = {};
    class MockAudioWorkletProcessor {
      port: WorkletPort = {
        onmessage: null,
        postMessage: jest.fn(),
      };
    }
    Object.defineProperties(globalThis, {
      AudioWorkletProcessor: {
        configurable: true,
        value: MockAudioWorkletProcessor,
      },
      registerProcessor: {
        configurable: true,
        value: (name: string, processor: WorkletProcessorConstructor) => {
          processors[name] = processor;
        },
      },
      sampleRate: { configurable: true, value: 48000 },
    });
    jest.isolateModules(() => {
      jest.requireActual('../../../public/worklets/live-follow-up-audio.js');
    });
  });

  afterEach(() => {
    const restore = (
      name: string,
      descriptor: PropertyDescriptor | undefined,
    ) => {
      if (descriptor) {
        Object.defineProperty(globalThis, name, descriptor);
      } else {
        delete (globalThis as Record<string, unknown>)[name];
      }
    };
    restore('AudioWorkletProcessor', originalAudioWorkletProcessor);
    restore('registerProcessor', originalRegisterProcessor);
    restore('sampleRate', originalSampleRate);
  });

  it('waits for the turn finish marker and flushes progress before completion', () => {
    const PlaybackProcessor = processors['live-follow-up-playback'];
    const processor = new PlaybackProcessor();
    const firstChunk = new Int16Array(1000);
    processor.port.onmessage?.({
      data: { type: 'audio', buffer: firstChunk.buffer, turnIndex: 7 },
    });

    for (let index = 0; index < 20; index += 1) {
      processor.process([], [[new Float32Array(128)]]);
    }
    expect(processor.port.postMessage).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: 'playback_complete' }),
    );

    const finalChunk = new Int16Array(125);
    processor.port.onmessage?.({
      data: { type: 'audio', buffer: finalChunk.buffer, turnIndex: 7 },
    });
    processor.port.onmessage?.({ data: { type: 'finish', turnIndex: 7 } });
    for (let index = 0; index < 4; index += 1) {
      processor.process([], [[new Float32Array(128)]]);
    }

    const messages = processor.port.postMessage.mock.calls.map(
      ([message]) => message as Record<string, unknown>,
    );
    const completionIndex = messages.findIndex(
      message =>
        message.type === 'playback_complete' && message.turnIndex === 7,
    );
    expect(completionIndex).toBeGreaterThan(0);
    expect(messages[completionIndex - 1]).toEqual({
      type: 'playback_progress',
      turnIndex: 7,
      playedBytes: 2250,
    });
  });

  it('flushes progress on interruption clear without reporting completion', () => {
    const PlaybackProcessor = processors['live-follow-up-playback'];
    const processor = new PlaybackProcessor();
    const pcm = new Int16Array(1000);
    processor.port.onmessage?.({
      data: { type: 'audio', buffer: pcm.buffer, turnIndex: 3 },
    });
    processor.process([], [[new Float32Array(128)]]);

    processor.port.onmessage?.({ data: { type: 'clear' } });

    expect(processor.port.postMessage).toHaveBeenCalledWith({
      type: 'playback_progress',
      turnIndex: 3,
      playedBytes: 128,
    });
    expect(processor.port.postMessage).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: 'playback_complete' }),
    );
  });

  it('consumes buffered playback through a cursor without shifting the backlog', () => {
    const PlaybackProcessor = processors['live-follow-up-playback'];
    const processor = new PlaybackProcessor();
    const pcm = new Int16Array(24000);
    processor.port.onmessage?.({
      data: { type: 'audio', buffer: pcm.buffer, turnIndex: 4 },
    });

    for (let index = 0; index < 15; index += 1) {
      processor.process([], [[new Float32Array(128)]]);
    }

    expect(processor.readOffset).toBe(960);
    expect(processor.samples).toHaveLength(24000);
    expect(processor.turnIndexes).toHaveLength(24000);
    expect(processor.port.postMessage).toHaveBeenCalledWith({
      type: 'playback_progress',
      turnIndex: 4,
      playedBytes: 1920,
    });
  });

  it('acknowledges a final progress flush after posting the checkpoint', () => {
    const PlaybackProcessor = processors['live-follow-up-playback'];
    const processor = new PlaybackProcessor();
    const pcm = new Int16Array(1000);
    processor.port.onmessage?.({
      data: { type: 'audio', buffer: pcm.buffer, turnIndex: 9 },
    });
    processor.process([], [[new Float32Array(128)]]);

    processor.port.onmessage?.({
      data: { type: 'flush_and_clear', requestId: 14 },
    });

    expect(processor.port.postMessage.mock.calls.slice(-2)).toEqual([
      [
        {
          type: 'playback_progress',
          turnIndex: 9,
          playedBytes: 128,
        },
      ],
      [{ type: 'flush_complete', requestId: 14 }],
    ]);
  });

  it('drops pending capture samples when muted', () => {
    const CaptureProcessor = processors['live-follow-up-capture'];
    const processor = new CaptureProcessor();
    processor.process([[new Float32Array(1500).fill(0.25)]], []);
    processor.port.onmessage?.({ data: { type: 'muted', muted: true } });
    processor.port.onmessage?.({ data: { type: 'muted', muted: false } });
    processor.process([[new Float32Array(500).fill(0.25)]], []);

    expect(processor.port.postMessage).not.toHaveBeenCalled();
  });

  it('emits 40ms mono PCM16 frames resampled to 16kHz', () => {
    const CaptureProcessor = processors['live-follow-up-capture'];
    const processor = new CaptureProcessor();

    processor.process([[new Float32Array(2000).fill(0.25)]], []);

    expect(processor.port.postMessage).toHaveBeenCalledTimes(1);
    const [frame, transfer] = processor.port.postMessage.mock.calls[0] as [
      ArrayBuffer,
      ArrayBuffer[],
    ];
    expect(frame).toBeInstanceOf(ArrayBuffer);
    expect(frame.byteLength).toBe(640 * Int16Array.BYTES_PER_ELEMENT);
    expect(transfer).toEqual([frame]);
    expect(new Int16Array(frame)[0]).toBeGreaterThan(0);
  });

  it('preserves the 48kHz to 16kHz sampling phase across render quanta', () => {
    const CaptureProcessor = processors['live-follow-up-capture'];
    const processor = new CaptureProcessor();

    for (let index = 0; index < 375; index += 1) {
      processor.process([[new Float32Array(128).fill(0.25)]], []);
    }

    const emittedSamples = processor.port.postMessage.mock.calls.reduce(
      (total, [frame]) => total + (frame as ArrayBuffer).byteLength / 2,
      0,
    );
    expect(emittedSamples).toBe(16000);
    expect(processor.port.postMessage).toHaveBeenCalledTimes(25);
  });
});
