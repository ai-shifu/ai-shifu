import {
  commitLiveFollowUpTurn,
  endLiveFollowUpSession,
  finalizeLiveFollowUpSession,
  type LiveFollowUpTurnReport,
} from '@/lib/liveVoiceFollowUp';

import type { GeminiLiveTurnCommit } from './geminiLiveTurnAccumulator';

const MAX_UNLOAD_REPORT_BYTES = 60 * 1024 - 256;

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

  constructor(
    readonly sessionBid: string,
    private readonly onCommitted: (commit: GeminiLiveTurnCommit) => void,
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

  private publish(commit: GeminiLiveTurnCommit) {
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
      this.onCommitted(commit);
    } catch {}
  }

  enqueue(commits: GeminiLiveTurnCommit[]) {
    this.remember(commits);
    for (const commit of commits) {
      const persist = async () => {
        if (this.handoff) {
          return;
        }
        await commitLiveFollowUpTurn(this.sessionBid, toReport(commit));
        this.publish(commit);
      };
      const pending = this.chain ? this.chain.then(persist) : persist();
      this.chain = pending.catch(() => {
        if (!this.handoff) {
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
    this.handoff = finalizeLiveFollowUpSession(
      this.sessionBid,
      outstanding.map(toReport),
      reason,
    ).then(() => {
      outstanding.forEach(commit => this.publish(commit));
    });
    return this.handoff;
  }

  finish(reason: string): Promise<void> {
    if (this.handoff) {
      return this.handoff;
    }
    this.finishing ??= this.finishNormally(reason);
    return this.finishing;
  }

  private async finishNormally(reason: string) {
    if (this.handoff) {
      return this.handoff;
    }
    await this.chain;
    if (this.handoff) {
      return this.handoff;
    }
    if (this.pending.size) {
      const outstanding = this.outstanding();
      if (fitsUnloadRequest(outstanding)) {
        return this.handOffForUnload([], reason);
      }
      // Retry retained reports individually before closing the binding. Normal
      // requests are not subject to fetch's aggregate keepalive byte budget.
      for (const commit of outstanding) {
        if (this.handoff) {
          return this.handoff;
        }
        await commitLiveFollowUpTurn(this.sessionBid, toReport(commit));
        this.publish(commit);
      }
    }
    await endLiveFollowUpSession(this.sessionBid, reason);
  }
}
