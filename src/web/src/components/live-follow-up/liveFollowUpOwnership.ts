import {
  heartbeatLiveFollowUpSession,
  LiveFollowUpControlError,
} from '@/lib/liveVoiceFollowUp';

const CHANNEL = 'live-follow-up-ownership';
const INTERVAL_MS = 3_000;
const AUTHORIZATION_MS = 10_000;

/** Cooperative browser fencing, not revocation of a disclosed Google token. */
export class LiveFollowUpOwnership {
  private stopped = false;
  private pending: Promise<void> | null = null;
  private poll: ReturnType<typeof setTimeout> | undefined;
  private expiry: ReturnType<typeof setTimeout> | undefined;
  private channel: BroadcastChannel | null = null;

  constructor(
    private readonly sessionBid: string,
    private readonly revision: string,
    private readonly onValid: (deadline: number) => void,
    private readonly onLost: (error: unknown) => void,
  ) {}

  async start(previousRevision?: string): Promise<void> {
    try {
      this.channel = new BroadcastChannel(CHANNEL);
      this.channel.onmessage = event => {
        if (event.data?.previousRevision === this.revision) void this.check();
      };
      if (previousRevision) this.channel.postMessage({ previousRevision });
    } catch {
      /* Polling remains authoritative when channels are unavailable. */
    }
    // Start the bound before HTTP, not after a possibly delayed response.
    this.armExpiry(performance.now() + AUTHORIZATION_MS);
    await this.check();
  }

  private armExpiry(deadline: number) {
    clearTimeout(this.expiry);
    this.expiry = setTimeout(
      () => this.fail(new LiveFollowUpControlError('admission_unavailable')),
      Math.max(0, deadline - performance.now()),
    );
  }

  check(): Promise<void> {
    if (this.stopped) return Promise.resolve();
    if (this.pending) return this.pending;
    clearTimeout(this.poll);
    const started = performance.now();
    this.pending = heartbeatLiveFollowUpSession(this.sessionBid)
      .then(() => {
        if (this.stopped) return;
        const deadline = started + AUTHORIZATION_MS;
        if (performance.now() >= deadline) {
          this.fail(new LiveFollowUpControlError('admission_unavailable'));
          return;
        }
        this.armExpiry(deadline);
        this.onValid(deadline);
      })
      .catch(error => {
        if (this.stopped) return;
        // Business/authorization failures are terminal, transport failures can
        // retry only inside the last server-validated authorization deadline.
        const status =
          typeof error === 'object' && error !== null && 'status' in error
            ? error.status
            : undefined;
        if (
          error instanceof LiveFollowUpControlError ||
          (typeof error === 'object' && error !== null && 'code' in error) ||
          (typeof status === 'number' &&
            status >= 400 &&
            status < 500 &&
            status !== 408 &&
            status !== 429)
        )
          this.fail(error);
      })
      .finally(() => {
        this.pending = null;
        if (!this.stopped)
          this.poll = setTimeout(() => void this.check(), INTERVAL_MS);
      });
    return this.pending;
  }

  private fail(error: unknown) {
    if (this.stopped) return;
    this.stop();
    this.onLost(error);
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.poll);
    clearTimeout(this.expiry);
    this.channel?.close();
    this.channel = null;
  }
}
