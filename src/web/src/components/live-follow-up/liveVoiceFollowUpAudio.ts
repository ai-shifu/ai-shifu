import { LIVE_FOLLOW_UP_AUDIO_WORKLET_PATH } from '@/lib/liveVoiceFollowUp';

export type LiveVoiceAudioCallbacks = {
  onInputFrame: (frame: ArrayBuffer) => void;
  onPlaybackProgress: (turnIndex: number, playedBytes: number) => void;
  onPlaybackComplete: (turnIndex: number) => void;
};

type AudioContextConstructor = new (
  options?: AudioContextOptions,
) => AudioContext;

type PlaybackProgressMessage = {
  type?: unknown;
  turnIndex?: unknown;
  playedBytes?: unknown;
  requestId?: unknown;
};

const PLAYBACK_FLUSH_TIMEOUT_MS = 100;

export class LiveVoiceAudioUnavailableError extends Error {
  constructor(message = 'Live voice audio is unavailable') {
    super(message);
    this.name = 'LiveVoiceAudioUnavailableError';
  }
}

const resolveAudioContextConstructor = (): AudioContextConstructor | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  const browserWindow = window as typeof window & {
    webkitAudioContext?: AudioContextConstructor;
  };
  return window.AudioContext || browserWindow.webkitAudioContext || null;
};

/**
 * Owns one microphone + playback graph for a Live follow-up session.
 * `activate` deliberately asks for the microphone and resumes AudioContext
 * before its first await so callers can invoke it directly from the click
 * stack (required by Safari/iOS user activation rules).
 */
export class LiveVoiceFollowUpAudio {
  private nextFlushRequestId = 1;
  private readonly flushResolvers = new Map<number, () => void>();
  private stopPromise: Promise<void> | null = null;

  private constructor(
    private readonly context: AudioContext,
    private readonly stream: MediaStream,
    private readonly source: MediaStreamAudioSourceNode,
    private readonly capture: AudioWorkletNode,
    private readonly playback: AudioWorkletNode,
    private readonly silentGain: GainNode,
  ) {}

  static activate(
    callbacks: LiveVoiceAudioCallbacks,
    signal?: AbortSignal,
  ): Promise<LiveVoiceFollowUpAudio> {
    const aborted = () =>
      new DOMException('Live audio activation was cancelled', 'AbortError');
    if (signal?.aborted) {
      return Promise.reject(aborted());
    }
    const AudioContextClass = resolveAudioContextConstructor();
    if (
      !AudioContextClass ||
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices?.getUserMedia
    ) {
      return Promise.reject(new LiveVoiceAudioUnavailableError());
    }

    const context = new AudioContextClass({ latencyHint: 'interactive' });
    let resumePromise: Promise<void> | undefined;
    let microphonePromise: Promise<MediaStream> | undefined;
    let workletPromise: Promise<void> | undefined;
    let released = false;
    const releasePendingAudio = () => {
      if (released) return;
      released = true;
      // getUserMedia cannot cancel an open permission prompt. Stop any stream
      // already acquired, or immediately when a late permission result arrives.
      void microphonePromise
        ?.then(stream => stream.getTracks().forEach(track => track.stop()))
        .catch(() => {});
      void resumePromise?.catch(() => {});
      void workletPromise?.catch(() => {});
      void context.close().catch(() => {});
    };
    try {
      // Keep both calls in the real click stack, even with cancellation.
      resumePromise = context.resume();
      microphonePromise = navigator.mediaDevices.getUserMedia({
        audio: {
          autoGainControl: true,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: { ideal: 16000 },
        },
        video: false,
      });
      workletPromise = context.audioWorklet.addModule(
        LIVE_FOLLOW_UP_AUDIO_WORKLET_PATH,
      );
    } catch (error) {
      releasePendingAudio();
      return Promise.reject(error);
    }
    let cancelActivation!: () => void;
    const cancelled = new Promise<never>((_, reject) => {
      cancelActivation = () => {
        releasePendingAudio();
        reject(aborted());
      };
    });
    signal?.addEventListener('abort', cancelActivation, { once: true });

    return Promise.race([
      Promise.all([resumePromise, microphonePromise, workletPromise]),
      cancelled,
    ])
      .then(([, stream]) => {
        if (signal?.aborted) throw aborted();
        const source = context.createMediaStreamSource(stream);
        const capture = new AudioWorkletNode(
          context,
          'live-follow-up-capture',
          { channelCount: 1, numberOfInputs: 1, numberOfOutputs: 1 },
        );
        const playback = new AudioWorkletNode(
          context,
          'live-follow-up-playback',
          { channelCount: 1, numberOfInputs: 0, numberOfOutputs: 1 },
        );
        const silentGain = context.createGain();
        silentGain.gain.value = 0;

        const audio = new LiveVoiceFollowUpAudio(
          context,
          stream,
          source,
          capture,
          playback,
          silentGain,
        );
        capture.port.onmessage = event => {
          if (event.data instanceof ArrayBuffer) {
            callbacks.onInputFrame(event.data);
          }
        };
        playback.port.onmessage = event => {
          audio.handlePlaybackMessage(event.data, callbacks);
        };

        source.connect(capture);
        capture.connect(silentGain);
        silentGain.connect(context.destination);
        playback.connect(context.destination);

        return audio;
      })
      .catch(error => {
        releasePendingAudio();
        throw error;
      })
      .finally(() => {
        signal?.removeEventListener('abort', cancelActivation);
      });
  }

  setMuted(muted: boolean) {
    this.capture.port.postMessage({ type: 'muted', muted });
  }

  enqueueOutput(buffer: ArrayBuffer, turnIndex: number) {
    if (this.context.state === 'closed' || buffer.byteLength === 0) {
      return;
    }
    this.playback.port.postMessage({ type: 'audio', buffer, turnIndex }, [
      buffer,
    ]);
  }

  finishOutput(turnIndex: number) {
    if (this.context.state === 'closed') {
      return;
    }
    this.playback.port.postMessage({ type: 'finish', turnIndex });
  }

  clearPlayback() {
    this.playback.port.postMessage({ type: 'clear' });
  }

  private handlePlaybackMessage(
    message: unknown,
    callbacks: LiveVoiceAudioCallbacks,
  ) {
    const data = message as PlaybackProgressMessage;
    if (
      data?.type === 'playback_progress' &&
      Number.isInteger(data.turnIndex) &&
      typeof data.playedBytes === 'number' &&
      Number.isFinite(data.playedBytes)
    ) {
      callbacks.onPlaybackProgress(
        Number(data.turnIndex),
        Math.max(0, Math.round(data.playedBytes)),
      );
      return;
    }
    if (
      data?.type === 'playback_complete' &&
      Number.isInteger(data.turnIndex)
    ) {
      callbacks.onPlaybackComplete(Number(data.turnIndex));
      return;
    }
    if (data?.type === 'flush_complete' && Number.isInteger(data.requestId)) {
      this.resolvePlaybackFlush(Number(data.requestId));
    }
  }

  private resolvePlaybackFlush(requestId: number) {
    const resolve = this.flushResolvers.get(requestId);
    if (!resolve) {
      return;
    }
    this.flushResolvers.delete(requestId);
    resolve();
  }

  private flushAndClearPlayback(): Promise<void> {
    if (this.context.state === 'closed') {
      return Promise.resolve();
    }
    const requestId = this.nextFlushRequestId;
    this.nextFlushRequestId += 1;
    return new Promise(resolve => {
      const timeoutId = window.setTimeout(() => {
        this.resolvePlaybackFlush(requestId);
      }, PLAYBACK_FLUSH_TIMEOUT_MS);
      this.flushResolvers.set(requestId, () => {
        window.clearTimeout(timeoutId);
        resolve();
      });
      try {
        this.playback.port.postMessage({
          type: 'flush_and_clear',
          requestId,
        });
      } catch {
        this.resolvePlaybackFlush(requestId);
      }
    });
  }

  stop(): Promise<void> {
    if (!this.stopPromise) {
      this.stopPromise = this.stopInternal();
    }
    return this.stopPromise;
  }

  private async stopInternal() {
    // Stop capture immediately, while keeping the playback port alive long
    // enough to flush its final consumed-byte checkpoint.
    this.stream.getTracks().forEach(track => track.stop());
    this.source.disconnect();
    this.capture.disconnect();
    this.silentGain.disconnect();
    await this.flushAndClearPlayback();
    this.capture.port.onmessage = null;
    this.playback.port.onmessage = null;
    this.playback.disconnect();
    this.flushResolvers.forEach(resolve => resolve());
    this.flushResolvers.clear();
    await this.context.close().catch(() => {});
  }
}
