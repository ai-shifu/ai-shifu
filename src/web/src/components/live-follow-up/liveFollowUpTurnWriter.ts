import {
  commitLiveFollowUpTurn,
  endLiveFollowUpSession,
  finalizeLiveFollowUpSession,
  type LiveFollowUpTurnReport,
  type LiveFollowUpTurnAcknowledgement,
} from '@/lib/liveVoiceFollowUp';

import type { GeminiLiveTurnCommit } from './geminiLiveTurnAccumulator';

const MAX_UNLOAD_REPORT_BYTES = 60 * 1024 - 256;
const NORMAL_DRAIN_TIMEOUT_MS = 5_000;
const RETAINED_TURN_TIMEOUT_MS = 10_000;
// A 45-second binding renewed every 15 seconds leaves at least 30 seconds at
// normal teardown. Keep closing requests inside that budget and expiry grace.
const CLOSING_TIMEOUT_MS = 25_000;
const MAX_FINALIZATION_ATTEMPTS = 3;
const FINALIZATION_RETRY_DELAY_MS = 1_000;
const WAIT_EXPIRED = Symbol('Live report wait expired');

const waitForReport = async <T>(
  report: Promise<T>,
  timeoutMs: number,
): Promise<T | typeof WAIT_EXPIRED> => {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      report,
      new Promise<typeof WAIT_EXPIRED>(resolve => {
        timer = setTimeout(() => resolve(WAIT_EXPIRED), timeoutMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
};

const toReport = (commit: GeminiLiveTurnCommit): LiveFollowUpTurnReport => ({
  turn_index: commit.turnIndex,
  user_transcript: commit.userTranscript,
  played_answer_transcript: commit.playedAnswerTranscript,
  interrupted: commit.interrupted,
  usage_metadata: commit.usageMetadata,
  latency_ms: commit.latencyMs,
});

const fitsUnloadRequest = (commits: GeminiLiveTurnCommit[]) =>
  new Blob([JSON.stringify(commits.map(toReport))]).size <=
  MAX_UNLOAD_REPORT_BYTES;

/** Retains normal reports independently of the single unload request budget. */
export class LiveFollowUpTurnWriter {
  private readonly pending = new Map<number, GeminiLiveTurnCommit>();
  private readonly notified = new Set<number>();
  private chain: Promise<void> | null = null;
  private handoff: Promise<void> | null = null;
  private finishing: Promise<void> | null = null;
  private recovery: Promise<void> | null = null;
  private closingDeadline: number | null = null;
  private finalized = false;
  private normalQueueStopped = false;
  private queueGeneration = 0;

  constructor(
    readonly sessionBid: string,
    private readonly onCommitted: (
      commit: GeminiLiveTurnCommit,
      acknowledgement?: LiveFollowUpTurnAcknowledgement,
    ) => void,
    private readonly onError: () => void,
  ) {}

  private remember(commits: GeminiLiveTurnCommit[]) {
    for (const commit of commits) {
      if (!fitsUnloadRequest([commit])) {
        throw new Error('Live transcript report exceeded its bound');
      }
      this.pending.set(commit.turnIndex, commit);
    }
  }

  private outstanding() {
    return [...this.pending.values()].sort(
      (left, right) => left.turnIndex - right.turnIndex,
    );
  }

  private publish(
    commit: GeminiLiveTurnCommit,
    acknowledgement?: LiveFollowUpTurnAcknowledgement,
  ) {
    this.pending.delete(commit.turnIndex);
    if (this.notified.has(commit.turnIndex)) {
      return;
    }
    this.notified.add(commit.turnIndex);
    // The backend records usage, but deliberately creates no ASK/ANSWER pair,
    // when Gemini never supplies a final user transcription.
    if (!commit.userTranscript.trim()) {
      return;
    }
    try {
      this.onCommitted(commit, acknowledgement);
    } catch {}
  }

  enqueue(commits: GeminiLiveTurnCommit[]) {
    this.remember(commits);
    const generation = this.queueGeneration;
    for (const commit of commits) {
      const persist = async () => {
        if (
          generation !== this.queueGeneration ||
          this.handoff ||
          this.normalQueueStopped ||
          !this.pending.has(commit.turnIndex)
        ) {
          return;
        }
        const acknowledgement = await commitLiveFollowUpTurn(
          this.sessionBid,
          toReport(commit),
        );
        this.publish(commit, acknowledgement);
      };
      const pending = this.chain ? this.chain.then(persist) : persist();
      this.chain = pending.catch(() => {
        if (
          generation === this.queueGeneration &&
          !this.handoff &&
          !this.normalQueueStopped
        ) {
          this.onError();
        }
      });
    }
    if (!fitsUnloadRequest(this.outstanding())) {
      // Stop taking more speech under backpressure, but only after every valid
      // commit has been retained and queued. Foreground teardown drains them.
      this.onError();
    }
  }

  handOffForUnload(commits: GeminiLiveTurnCommit[], reason: string) {
    if (this.finalized)
      return this.handoff ?? this.finishing ?? Promise.resolve();
    if (this.handoff) {
      return this.handoff;
    }
    this.remember(commits);
    const outstanding = this.outstanding();
    if (!fitsUnloadRequest(outstanding)) {
      // Never send an oversized keepalive or end the binding with a truncated
      // batch. Retain/drain the normal queue while the document is alive;
      // browsers cannot guarantee an over-budget backlog survives unload.
      return this.finish(reason);
    }
    // Do not await the active normal request: keepalive only protects requests
    // already initiated before pagehide discards this document. The backend
    // waits for an in-flight predecessor and skips its durable acknowledgement.
    this.handoff = this.finalizeWithRecovery(outstanding, reason);
    return this.handoff;
  }

  private async finalizeWithRecovery(
    outstanding: GeminiLiveTurnCommit[],
    reason: string,
  ) {
    const reports = outstanding.map(toReport);
    for (let attempt = 1; ; attempt += 1) {
      try {
        await this.waitForClosingRequest(() =>
          finalizeLiveFollowUpSession(this.sessionBid, reports, reason),
        );
        outstanding.forEach(commit => this.publish(commit));
        this.finalized = true;
        return;
      } catch (error) {
        if (
          attempt < MAX_FINALIZATION_ATTEMPTS &&
          this.remainingClosingTime() > FINALIZATION_RETRY_DELAY_MS
        ) {
          // The predecessor can still own the bounded backend write lock.
          // Retry the same idempotent batch without re-enabling its successors.
          await this.waitBeforeRetry();
          continue;
        }
        this.handoff = null;
        // A pagehide batch started during recovery must not await the very
        // recovery operation that may be waiting for that batch.
        if (this.recovery || this.remainingClosingTime() <= 0) throw error;
        return this.startRecovery(reason);
      }
    }
  }

  finish(reason: string): Promise<void> {
    if (this.finishing) return this.finishing;
    if (this.handoff) {
      return this.handoff;
    }
    if (this.recovery) return this.recovery;
    this.finishing ??= this.finishNormally(reason);
    return this.finishing;
  }

  private async finishNormally(reason: string) {
    if (this.handoff) {
      return this.handoff;
    }
    // Teardown has stopped heartbeats. Do not let an unbounded fetch consume
    // the 45-second binding TTL before the retained outbox reaches /finalize.
    const drained = await waitForReport(
      this.chain ?? Promise.resolve(),
      Math.min(NORMAL_DRAIN_TIMEOUT_MS, this.remainingClosingTime()),
    );
    if (this.handoff) {
      return this.handoff;
    }
    if (drained === WAIT_EXPIRED) {
      // The active request may still acknowledge later. Stop its successors;
      // the idempotent finalizer or ordered retry now owns the retained turns.
      this.normalQueueStopped = true;
    }
    if (this.pending.size) {
      const outstanding = this.outstanding();
      if (fitsUnloadRequest(outstanding)) {
        return this.handOffForUnload([], reason);
      }
      return this.startRecovery(reason);
    }
    await this.closeBinding(reason);
  }

  private remainingClosingTime() {
    this.closingDeadline ??= performance.now() + CLOSING_TIMEOUT_MS;
    return Math.max(0, this.closingDeadline - performance.now());
  }

  private async waitForClosingRequest<T>(
    request: () => Promise<T>,
  ): Promise<T> {
    const remaining = this.remainingClosingTime();
    if (remaining <= 0) throw new Error('Live turn report timed out');
    const result = await waitForReport(
      request(),
      Math.min(RETAINED_TURN_TIMEOUT_MS, remaining),
    );
    if (result === WAIT_EXPIRED) throw new Error('Live turn report timed out');
    return result;
  }

  private waitBeforeRetry() {
    const remaining = this.remainingClosingTime();
    if (remaining <= 0) throw new Error('Live turn report timed out');
    return new Promise<void>(resolve =>
      setTimeout(resolve, Math.min(FINALIZATION_RETRY_DELAY_MS, remaining)),
    );
  }

  private startRecovery(reason: string) {
    if (this.recovery) return this.recovery;
    // Detach from the stalled normal chain and keep every retry attached to
    // finish(). Only the earliest unacknowledged index can advance the cursor.
    this.normalQueueStopped = true;
    this.queueGeneration += 1;
    this.chain = null;
    this.recovery = this.recoverInOrder(reason);
    return this.recovery;
  }

  private async recoverInOrder(reason: string) {
    while (!this.finalized) {
      if (this.handoff) {
        // A lifecycle callback can initiate a bounded keepalive while a normal
        // recovery write is pending. Join it before issuing another successor.
        try {
          await this.handoff;
        } catch {
          if (this.remainingClosingTime() <= 0)
            throw new Error('Live turn report timed out');
        }
        if (this.finalized) return;
      }
      const commit = this.outstanding()[0];
      if (!commit) break;
      try {
        const acknowledgement = await this.waitForClosingRequest(() =>
          commitLiveFollowUpTurn(this.sessionBid, toReport(commit)),
        );
        this.publish(commit, acknowledgement);
      } catch {
        if (this.finalized) return;
        await this.waitBeforeRetry();
      }
    }
    if (!this.finalized) await this.closeBinding(reason);
  }

  private async closeBinding(reason: string) {
    await this.waitForClosingRequest(() =>
      endLiveFollowUpSession(this.sessionBid, reason),
    );
    this.finalized = true;
  }
}
