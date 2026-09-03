import {
  commitLiveFollowUpTurn,
  endLiveFollowUpSession,
  finalizeLiveFollowUpSession,
  type LiveFollowUpTurnReport,
} from '@/lib/liveVoiceFollowUp';

import type { GeminiLiveTurnCommit } from './geminiLiveTurnAccumulator';

const MAX_PENDING_REPORT_BYTES = 60 * 1024 - 256;

const toReport = (commit: GeminiLiveTurnCommit): LiveFollowUpTurnReport => ({
  turn_index: commit.turnIndex,
  user_transcript: commit.userTranscript,
  played_answer_transcript: commit.playedAnswerTranscript,
  interrupted: commit.interrupted,
  usage_metadata: commit.usageMetadata,
  latency_ms: commit.latencyMs,
});

/** Retains unacknowledged turns so teardown can initiate one bounded request. */
export class LiveFollowUpTurnWriter {
  private readonly pending = new Map<number, GeminiLiveTurnCommit>();
  private readonly notified = new Set<number>();
  private chain: Promise<void> | null = null;
  private handoff: Promise<void> | null = null;

  constructor(
    readonly sessionBid: string,
    private readonly onCommitted: (commit: GeminiLiveTurnCommit) => void,
    private readonly onError: () => void,
  ) {}

  private remember(commits: GeminiLiveTurnCommit[]) {
    const next = new Map(this.pending);
    for (const commit of commits) {
      next.set(commit.turnIndex, commit);
    }
    if (
      new Blob([JSON.stringify([...next.values()].map(toReport))]).size >
      MAX_PENDING_REPORT_BYTES
    ) {
      throw new Error('Live transcript backlog exceeded its bound');
    }
    for (const commit of commits) {
      this.pending.set(commit.turnIndex, commit);
    }
  }

  private publish(commit: GeminiLiveTurnCommit) {
    this.pending.delete(commit.turnIndex);
    if (this.notified.has(commit.turnIndex)) {
      return;
    }
    this.notified.add(commit.turnIndex);
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
  }

  handOffForUnload(commits: GeminiLiveTurnCommit[], reason: string) {
    if (this.handoff) {
      return this.handoff;
    }
    this.remember(commits);
    const outstanding = [...this.pending.values()].sort(
      (left, right) => left.turnIndex - right.turnIndex,
    );
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

  async finish(reason: string) {
    if (this.handoff) {
      return this.handoff;
    }
    await this.chain;
    if (this.handoff) {
      return this.handoff;
    }
    if (this.pending.size) {
      return this.handOffForUnload([], reason);
    }
    await endLiveFollowUpSession(this.sessionBid, reason);
  }
}
