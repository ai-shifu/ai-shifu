import {
  mergeLiveTranscript,
  type GeminiLiveServerEvent,
  type LiveFollowUpTranscriptRole,
} from '@/lib/liveVoiceFollowUp';

export const GEMINI_LIVE_RECONCILIATION_MS = 500;

export type GeminiLiveTranscriptUpdate = {
  role: LiveFollowUpTranscriptRole;
  turnIndex: number;
  text: string;
  final: boolean;
};

export type GeminiLiveTurnIngestResult = {
  audioTurnIndex: number | null;
  audioChunks: ArrayBuffer[];
  transcriptUpdates: GeminiLiveTranscriptUpdate[];
  interruptedTurnIndex: number | null;
  terminalTurnIndex: number | null;
};

export type GeminiLiveTurnCommit = {
  turnIndex: number;
  userTranscript: string;
  playedAnswerTranscript: string;
  fullAnswerTranscript: string;
  interrupted: boolean;
  usageMetadata: Record<string, unknown> | null;
  latencyMs: number;
};

type OutputCheckpoint = {
  byteCount: number;
  text: string;
};

type TurnState = {
  turnIndex: number;
  startedAt: number;
  userTranscript: string;
  userInterimTranscript: string;
  receivedInputTranscription: boolean;
  userTranscriptFinal: boolean;
  typedInput: boolean;
  locallyInterrupted: boolean;
  discardedByPause: boolean;
  outputTranscript: string;
  outputWaitingForAudio: string;
  outputCheckpoints: OutputCheckpoint[];
  audioSentBytes: number;
  audioPlayedBytes: number;
  playbackComplete: boolean;
  usageMetadata: Record<string, unknown> | null;
  terminalReason: 'turn_complete' | 'interrupted' | 'session_end' | null;
  readyAt: number | null;
};

const hasActivity = (state: TurnState) =>
  Boolean(
    state.userTranscript ||
    state.outputTranscript ||
    state.audioSentBytes ||
    state.usageMetadata,
  );

// Interim speech identifies its turn for routing, but is never durable content.
const hasRoutingActivity = (state: TurnState) =>
  hasActivity(state) || Boolean(state.userInterimTranscript);

const latestSnapshot = (fragments: string[]) => {
  for (let index = fragments.length - 1; index >= 0; index -= 1) {
    const text = fragments[index].trim();
    if (text) {
      return text;
    }
  }
  return '';
};

export class GeminiLiveTurnAccumulator {
  private activeTurnIndex = 1;
  private readonly turns = new Map<number, TurnState>();
  private lastResponseTurnIndex: number | null = null;
  private readonly interruptedAwaitingTurnComplete: number[] = [];
  private pendingTextTurnIndex: number | null = null;
  private outputPaused = false;

  get textHandoffPending() {
    return this.pendingTextTurnIndex !== null;
  }

  pauseOutput(now = Date.now()): number[] {
    this.outputPaused = true;
    const interrupted: number[] = [];
    for (const state of this.turns.values()) {
      if (
        hasRoutingActivity(state) &&
        (!state.terminalReason || !this.playbackSettled(state))
      ) {
        this.discardOutputForPause(state, now);
        interrupted.push(state.turnIndex);
      }
    }
    return interrupted;
  }

  resumeOutput() {
    // A discarded reply stays discarded even if its final chunks arrive after
    // the panel reopens. Only future turns become audible again.
    this.outputPaused = false;
  }

  submitText(text: string, now = Date.now()) {
    if (this.textHandoffPending || !text.trim()) return null;
    const active = this.activeState(now);
    const previous = this.turns.get(this.lastResponseTurnIndex ?? -1);
    const inFlight = hasRoutingActivity(active) && !active.terminalReason;
    const interruptedState = inFlight
      ? active
      : previous && !this.playbackSettled(previous)
        ? previous
        : null;
    if (interruptedState) {
      interruptedState.locallyInterrupted = true;
      if (interruptedState.terminalReason) {
        this.markTerminal(interruptedState, 'interrupted', now);
      }
    }
    const next = inFlight ? this.state(active.turnIndex + 1, now) : active;
    if (inFlight) this.pendingTextTurnIndex = next.turnIndex;
    next.typedInput = true;
    next.userTranscript = text.trim();
    next.userTranscriptFinal = true;
    return {
      update: this.transcriptUpdate(next, 'user', true),
      interruptedTurnIndex: interruptedState?.turnIndex ?? null,
    };
  }

  suppressPlayback(turnIndex: number) {
    return (
      this.outputPaused ||
      this.turns.get(turnIndex)?.locallyInterrupted === true
    );
  }

  process(
    event: GeminiLiveServerEvent,
    now = Date.now(),
  ): GeminiLiveTurnIngestResult {
    const transcriptUpdates: GeminiLiveTranscriptUpdate[] = [];
    const trailingInterruptedTurnIndex =
      event.turnComplete &&
      !event.interrupted &&
      this.interruptedAwaitingTurnComplete.length
        ? this.interruptedAwaitingTurnComplete[0]
        : null;
    const hasModelOutput = Boolean(
      event.outputTranscripts.length || event.audioChunks.length,
    );
    let inputState = event.interrupted
      ? this.activeState(now)
      : this.selectInputState(event.inputTranscripts, now, hasModelOutput);
    // Until the old upstream turn is terminal, even late parts belong to it.
    const pendingPrevious =
      this.pendingTextTurnIndex === null
        ? null
        : this.turns.get(this.pendingTextTurnIndex - 1);
    if (pendingPrevious && !pendingPrevious.typedInput)
      inputState = pendingPrevious;
    const responseState =
      pendingPrevious ??
      (event.interrupted
        ? (this.turns.get(this.lastResponseTurnIndex ?? -1) ?? inputState)
        : trailingInterruptedTurnIndex !== null
          ? this.state(trailingInterruptedTurnIndex, now)
          : event.inputTranscripts.length ||
              event.interimInputTranscripts.length
            ? inputState
            : this.selectResponseState(now, hasModelOutput));
    const responseTouched = hasModelOutput || Boolean(event.usageMetadata);

    if (this.outputPaused) {
      if (
        responseTouched &&
        (!responseState.terminalReason ||
          !this.playbackSettled(responseState) ||
          event.audioChunks.length)
      ) {
        this.discardOutputForPause(responseState, now);
      }
      if (
        event.inputTranscripts.length ||
        event.interimInputTranscripts.length
      ) {
        this.discardOutputForPause(inputState, now);
      }
    }

    for (const fragment of event.outputTranscripts) {
      const merged = mergeLiveTranscript(
        responseState.outputTranscript,
        fragment,
      );
      if (merged === responseState.outputTranscript) {
        continue;
      }
      responseState.outputTranscript = merged;
      this.lastResponseTurnIndex = responseState.turnIndex;
      transcriptUpdates.push(
        this.transcriptUpdate(
          responseState,
          'assistant',
          responseState.terminalReason !== null,
        ),
      );
      if (!event.audioChunks.length) {
        if (responseState.audioSentBytes) {
          this.upsertCheckpoint(responseState);
        } else {
          responseState.outputWaitingForAudio = merged.trim();
        }
      }
    }

    const audioBytes = event.audioChunks.reduce(
      (total, chunk) => total + chunk.byteLength,
      0,
    );
    if (audioBytes) {
      responseState.playbackComplete = false;
      responseState.audioSentBytes += audioBytes;
      this.lastResponseTurnIndex = responseState.turnIndex;
      const checkpointText = responseState.outputTranscript.trim();
      if (checkpointText) {
        this.upsertCheckpoint(responseState, checkpointText);
      } else if (responseState.outputWaitingForAudio) {
        this.upsertCheckpoint(
          responseState,
          responseState.outputWaitingForAudio,
        );
      }
      responseState.outputWaitingForAudio = '';
    }
    if (event.usageMetadata) {
      responseState.usageMetadata = { ...event.usageMetadata };
    }

    let interruptedTurnIndex: number | null = null;
    let terminalTurnIndex: number | null = null;
    if (event.interrupted) {
      this.markTerminal(responseState, 'interrupted', now);
      interruptedTurnIndex = responseState.turnIndex;
      terminalTurnIndex = responseState.turnIndex;
      transcriptUpdates.push(...this.finalUpdates(responseState));
      this.advance(responseState);
      // Speech coalesced with the interruption belongs to the learner's next
      // question, not to the response whose playback was just cancelled.
      inputState =
        pendingPrevious && !pendingPrevious.typedInput
          ? pendingPrevious
          : this.activeState(now);
      if (!event.turnComplete) {
        this.interruptedAwaitingTurnComplete.push(responseState.turnIndex);
      }
    }

    for (const fragment of event.inputTranscripts) {
      if (inputState.typedInput) continue;
      inputState.receivedInputTranscription = true;
      inputState.userInterimTranscript = '';
      const merged = mergeLiveTranscript(inputState.userTranscript, fragment);
      if (merged === inputState.userTranscript) {
        continue;
      }
      inputState.userTranscript = merged;
      if (inputState.terminalReason) {
        inputState.userTranscriptFinal = true;
      }
      transcriptUpdates.push(
        this.transcriptUpdate(
          inputState,
          'user',
          inputState.terminalReason !== null,
        ),
      );
    }
    if (
      !event.inputTranscripts.length &&
      !inputState.typedInput &&
      !inputState.receivedInputTranscription
    ) {
      const interim = latestSnapshot(event.interimInputTranscripts);
      if (interim && interim !== inputState.userInterimTranscript) {
        inputState.userInterimTranscript = interim;
        transcriptUpdates.push({
          role: 'user',
          turnIndex: inputState.turnIndex,
          text: interim,
          final: false,
        });
      }
    }

    if (trailingInterruptedTurnIndex !== null) {
      this.interruptedAwaitingTurnComplete.shift();
    } else if (event.turnComplete && !event.interrupted) {
      const terminalState =
        pendingPrevious || (responseTouched ? responseState : inputState);
      if (hasActivity(terminalState)) {
        this.markTerminal(terminalState, 'turn_complete', now);
        terminalTurnIndex = terminalState.turnIndex;
        transcriptUpdates.push(...this.finalUpdates(terminalState));
        this.advance(terminalState);
      }
    }

    if (pendingPrevious && event.turnComplete) {
      this.activeTurnIndex = this.pendingTextTurnIndex!;
      this.pendingTextTurnIndex = null;
    }

    return {
      audioTurnIndex: audioBytes ? responseState.turnIndex : null,
      audioChunks: event.audioChunks,
      transcriptUpdates,
      interruptedTurnIndex,
      terminalTurnIndex,
    };
  }

  recordPlaybackProgress(turnIndex: number, playedBytes: number) {
    const state = this.turns.get(turnIndex);
    if (!state) {
      return;
    }
    const bounded = Math.min(Math.max(0, playedBytes), state.audioSentBytes);
    state.audioPlayedBytes = Math.max(state.audioPlayedBytes, bounded);
  }

  markPlaybackComplete(turnIndex: number) {
    const state = this.turns.get(turnIndex);
    if (
      !state ||
      state.terminalReason === 'interrupted' ||
      state.locallyInterrupted
    ) {
      return;
    }
    state.audioPlayedBytes = state.audioSentBytes;
    state.playbackComplete = true;
  }

  popReady(now = Date.now(), force = false): GeminiLiveTurnCommit[] {
    const ready: GeminiLiveTurnCommit[] = [];
    for (const turnIndex of [...this.turns.keys()].sort((a, b) => a - b)) {
      const state = this.turns.get(turnIndex);
      if (!state?.terminalReason) {
        continue;
      }
      if (
        (!force && this.pendingTextTurnIndex === turnIndex + 1) ||
        (!force && state.readyAt !== null && state.readyAt > now) ||
        (!force && !this.playbackSettled(state))
      ) {
        // The server accepts only the next turn. Retain every successor until
        // this earlier terminal turn can join the consecutive ready prefix.
        break;
      }
      this.turns.delete(turnIndex);
      ready.push(this.toCommit(state, now));
    }
    return ready;
  }

  finishSession(now = Date.now()): GeminiLiveTurnCommit[] {
    for (const state of this.turns.values()) {
      if (hasActivity(state) && !state.terminalReason) {
        this.markTerminal(state, 'session_end', now);
        this.advance(state);
      }
    }
    return this.popReady(now, true);
  }

  private activeState(now = Date.now()) {
    return this.state(this.activeTurnIndex, now);
  }

  private state(turnIndex: number, now: number) {
    let state = this.turns.get(turnIndex);
    if (!state) {
      state = {
        turnIndex,
        startedAt: now,
        userTranscript: '',
        userInterimTranscript: '',
        receivedInputTranscription: false,
        userTranscriptFinal: false,
        typedInput: false,
        locallyInterrupted: false,
        discardedByPause: false,
        outputTranscript: '',
        outputWaitingForAudio: '',
        outputCheckpoints: [],
        audioSentBytes: 0,
        audioPlayedBytes: 0,
        playbackComplete: false,
        usageMetadata: null,
        terminalReason: null,
        readyAt: null,
      };
      this.turns.set(turnIndex, state);
    }
    return state;
  }

  private selectInputState(
    fragments: string[],
    now: number,
    hasModelOutput: boolean,
  ) {
    const active = this.activeState(now);
    if (!fragments.length || hasRoutingActivity(active) || hasModelOutput) {
      return active;
    }
    const previous = this.latestMutableTerminal(now);
    return previous && !previous.typedInput ? previous : active;
  }

  private selectResponseState(now: number, hasModelOutput: boolean) {
    const active = this.activeState(now);
    // turnComplete closes model output, including output transcription. New
    // output is a successor even when its unordered input transcript is late;
    // only input/usage-only events may reconcile into the completed turn.
    if (hasRoutingActivity(active) || hasModelOutput) {
      return active;
    }
    return this.latestMutableTerminal(now) || active;
  }

  private latestMutableTerminal(now: number) {
    if (this.lastResponseTurnIndex === null) {
      return null;
    }
    const state = this.turns.get(this.lastResponseTurnIndex);
    if (
      (state?.terminalReason !== 'turn_complete' &&
        !(state?.discardedByPause && state.terminalReason === 'interrupted')) ||
      state.readyAt === null ||
      state.readyAt < now
    ) {
      return null;
    }
    return state;
  }

  private discardOutputForPause(state: TurnState, now: number) {
    state.locallyInterrupted = true;
    state.discardedByPause = true;
    if (state.terminalReason) this.markTerminal(state, 'interrupted', now);
  }

  private markTerminal(
    state: TurnState,
    reason: NonNullable<TurnState['terminalReason']>,
    now: number,
  ) {
    if (!state.terminalReason) {
      state.terminalReason = state.locallyInterrupted ? 'interrupted' : reason;
      state.userTranscriptFinal =
        (state.typedInput || state.receivedInputTranscription) &&
        Boolean(state.userTranscript.trim());
      state.readyAt = now + GEMINI_LIVE_RECONCILIATION_MS;
    } else if (reason === 'interrupted') {
      state.terminalReason = reason;
    }
  }

  private advance(state: TurnState) {
    this.lastResponseTurnIndex = state.turnIndex;
    if (state.turnIndex >= this.activeTurnIndex) {
      this.activeTurnIndex = state.turnIndex + 1;
    }
  }

  private upsertCheckpoint(state: TurnState, text = state.outputTranscript) {
    // Transcription can lead its audio. After discarding output, a late text
    // fragment must not relabel an earlier byte checkpoint as newly heard.
    if (state.discardedByPause) return;
    const normalized = text.trim();
    if (!normalized) {
      return;
    }
    const previous = state.outputCheckpoints.at(-1);
    if (previous?.byteCount === state.audioSentBytes) {
      previous.text = normalized;
      return;
    }
    state.outputCheckpoints.push({
      byteCount: state.audioSentBytes,
      text: normalized,
    });
  }

  private transcriptUpdate(
    state: TurnState,
    role: LiveFollowUpTranscriptRole,
    final: boolean,
  ): GeminiLiveTranscriptUpdate {
    return {
      role,
      turnIndex: state.turnIndex,
      text:
        role === 'user'
          ? state.userTranscript.trim()
          : state.outputTranscript.trim(),
      final,
    };
  }

  private finalUpdates(state: TurnState) {
    const updates: GeminiLiveTranscriptUpdate[] = [];
    if (state.userTranscript.trim()) {
      updates.push(this.transcriptUpdate(state, 'user', true));
    }
    if (state.outputTranscript.trim()) {
      updates.push(this.transcriptUpdate(state, 'assistant', true));
    }
    return updates;
  }

  private playbackSettled(state: TurnState) {
    return (
      state.terminalReason === 'interrupted' ||
      state.audioSentBytes === 0 ||
      state.playbackComplete ||
      state.audioPlayedBytes >= state.audioSentBytes
    );
  }

  private toCommit(state: TurnState, now: number): GeminiLiveTurnCommit {
    let playedAnswerTranscript = '';
    for (const checkpoint of state.outputCheckpoints) {
      if (checkpoint.byteCount > state.audioPlayedBytes) {
        break;
      }
      playedAnswerTranscript = checkpoint.text;
    }
    return {
      turnIndex: state.turnIndex,
      userTranscript: state.userTranscriptFinal
        ? state.userTranscript.trim()
        : '',
      playedAnswerTranscript,
      fullAnswerTranscript: state.outputTranscript.trim(),
      interrupted: state.terminalReason === 'interrupted',
      usageMetadata: state.usageMetadata ? { ...state.usageMetadata } : null,
      latencyMs: Math.max(0, now - state.startedAt),
    };
  }
}
