/* global AudioWorkletProcessor, registerProcessor, sampleRate */

const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;
const INPUT_FRAME_SAMPLES = 640;

class StreamingLinearResampler {
  constructor(sourceRate, targetRate) {
    this.step = sourceRate / targetRate;
    this.buffer = [];
    this.position = 0;
  }

  push(input) {
    for (let index = 0; index < input.length; index += 1) {
      this.buffer.push(input[index]);
    }

    const output = [];
    while (this.position + 1 < this.buffer.length) {
      const leftIndex = Math.floor(this.position);
      const fraction = this.position - leftIndex;
      const left = this.buffer[leftIndex];
      const right = this.buffer[leftIndex + 1];
      output.push(left + (right - left) * fraction);
      this.position += this.step;
    }

    // Keep one source sample so interpolation and the fractional cursor remain
    // continuous across the browser's 128-sample render quanta.
    const consumed = Math.min(
      Math.floor(this.position),
      Math.max(0, this.buffer.length - 1),
    );
    if (consumed > 0) {
      this.buffer.splice(0, consumed);
      this.position -= consumed;
    }
    return output;
  }

  reset() {
    this.buffer = [];
    this.position = 0;
  }
}

class LiveFollowUpCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.muted = false;
    this.pending = [];
    this.resampler = new StreamingLinearResampler(
      sampleRate,
      INPUT_SAMPLE_RATE,
    );
    this.port.onmessage = event => {
      if (event.data?.type === 'muted') {
        const muted = Boolean(event.data.muted);
        if (muted && !this.muted) {
          this.pending = [];
          this.resampler.reset();
        }
        this.muted = muted;
      }
    };
  }

  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input || this.muted) {
      return true;
    }

    this.pending.push(...this.resampler.push(input));
    while (this.pending.length >= INPUT_FRAME_SAMPLES) {
      const frame = this.pending.splice(0, INPUT_FRAME_SAMPLES);
      const pcm = new Int16Array(INPUT_FRAME_SAMPLES);
      for (let index = 0; index < frame.length; index += 1) {
        const value = Math.max(-1, Math.min(1, frame[index]));
        pcm[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}

class LiveFollowUpPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
    this.turnIndexes = [];
    this.position = 0;
    this.step = OUTPUT_SAMPLE_RATE / sampleRate;
    this.playedBytesByTurn = new Map();
    this.dirtyProgressTurns = new Set();
    this.finishedTurns = new Set();
    this.progressSamplesSincePost = 0;
    this.port.onmessage = event => {
      if (event.data?.type === 'flush_and_clear') {
        this.flushPlaybackProgress();
        this.samples = [];
        this.turnIndexes = [];
        this.position = 0;
        this.playedBytesByTurn.clear();
        this.finishedTurns.clear();
        this.progressSamplesSincePost = 0;
        if (Number.isInteger(event.data.requestId)) {
          this.port.postMessage({
            type: 'flush_complete',
            requestId: event.data.requestId,
          });
        }
        return;
      }
      if (event.data?.type === 'clear') {
        this.flushPlaybackProgress();
        this.samples = [];
        this.turnIndexes = [];
        this.position = 0;
        this.playedBytesByTurn.clear();
        this.finishedTurns.clear();
        this.progressSamplesSincePost = 0;
        return;
      }
      if (event.data?.type === 'finish') {
        const turnIndex = Number.isInteger(event.data.turnIndex)
          ? event.data.turnIndex
          : -1;
        if (turnIndex < 0) {
          return;
        }
        this.finishedTurns.add(turnIndex);
        this.completeTurnIfDrained(turnIndex);
        return;
      }
      if (event.data?.type !== 'audio') {
        return;
      }
      const pcm = new Int16Array(event.data.buffer);
      const turnIndex = Number.isInteger(event.data.turnIndex)
        ? event.data.turnIndex
        : -1;
      for (let index = 0; index < pcm.length; index += 1) {
        this.samples.push(pcm[index] / 0x8000);
        this.turnIndexes.push(turnIndex);
      }
    };
  }

  reportConsumedSamples(consumed) {
    if (consumed <= 0) {
      return;
    }

    for (let index = 0; index < consumed; index += 1) {
      const turnIndex = this.turnIndexes[index];
      if (turnIndex < 0) {
        continue;
      }
      const nextBytes = (this.playedBytesByTurn.get(turnIndex) || 0) + 2;
      this.playedBytesByTurn.set(turnIndex, nextBytes);
      this.dirtyProgressTurns.add(turnIndex);
    }

    this.progressSamplesSincePost += consumed;
    if (this.progressSamplesSincePost < 960) {
      return;
    }

    this.flushPlaybackProgress();
  }

  flushPlaybackProgress() {
    if (this.dirtyProgressTurns.size === 0) {
      this.progressSamplesSincePost = 0;
      return;
    }

    this.dirtyProgressTurns.forEach(turnIndex => {
      this.port.postMessage({
        type: 'playback_progress',
        turnIndex,
        playedBytes: this.playedBytesByTurn.get(turnIndex) || 0,
      });
    });
    this.dirtyProgressTurns.clear();
    this.progressSamplesSincePost = 0;
  }

  completeTurnIfDrained(turnIndex) {
    if (
      !this.finishedTurns.has(turnIndex) ||
      this.turnIndexes.includes(turnIndex)
    ) {
      return;
    }
    this.flushPlaybackProgress();
    this.port.postMessage({
      type: 'playback_complete',
      turnIndex,
    });
    this.finishedTurns.delete(turnIndex);
    this.playedBytesByTurn.delete(turnIndex);
  }

  process(_inputs, outputs) {
    const output = outputs[0]?.[0];
    if (!output) {
      return true;
    }

    output.fill(0);
    for (let index = 0; index < output.length; index += 1) {
      if (this.position >= this.samples.length) {
        break;
      }
      const leftIndex = Math.floor(this.position);
      const fraction = this.position - leftIndex;
      const left = this.samples[leftIndex];
      const right =
        this.samples[Math.min(leftIndex + 1, this.samples.length - 1)];
      output[index] = left + (right - left) * fraction;
      this.position += this.step;
    }

    const consumed = Math.min(Math.floor(this.position), this.samples.length);
    if (consumed > 0) {
      const consumedTurnIndexes = new Set(
        this.turnIndexes.slice(0, consumed).filter(turnIndex => turnIndex >= 0),
      );
      this.reportConsumedSamples(consumed);
      this.samples.splice(0, consumed);
      this.turnIndexes.splice(0, consumed);
      this.position -= consumed;
      consumedTurnIndexes.forEach(turnIndex => {
        // MessagePort ordering guarantees the final progress update reaches
        // the browser before completion for this turn.
        this.completeTurnIfDrained(turnIndex);
      });
    }
    return true;
  }
}

registerProcessor('live-follow-up-capture', LiveFollowUpCaptureProcessor);
registerProcessor('live-follow-up-playback', LiveFollowUpPlaybackProcessor);
