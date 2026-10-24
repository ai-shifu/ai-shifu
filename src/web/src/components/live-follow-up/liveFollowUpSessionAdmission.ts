import {
  createLiveFollowUpSession,
  getLiveFollowUpOperationStatus,
  getLiveFollowUpOwner,
  LIVE_FOLLOW_UP_CAPACITY_ERROR_CODE,
  LiveFollowUpControlError,
  type LiveFollowUpOperationResult,
  type LiveFollowUpSession,
  type LiveFollowUpSessionRequest,
} from '@/lib/liveVoiceFollowUp';

type PendingRequest = {
  shifuBid: string;
  outlineBid: string;
  requestBid: string;
  target: LiveFollowUpSessionRequest;
  startedAt: number;
};

const REQUEST_RETENTION_MS = 20 * 60_000;

// UUIDv7's timestamp makes old HTTP retries rejectable after Redis tombstones
// expire. Randomness is cryptographic; this ID is never a bearer credential.
export const createLiveFollowUpRequestBid = (timestamp: number): string => {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let milliseconds = Math.floor(timestamp);
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = milliseconds % 256;
    milliseconds = Math.floor(milliseconds / 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x70;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

const controlFailure = (result: LiveFollowUpOperationResult) =>
  new LiveFollowUpControlError(
    result.error_code ?? 'admission_unavailable',
    result.retry_after_ms,
    result.capacity_scopes,
  );

/** Keeps only request identity across media teardown, never tokens or content. */
export class LiveFollowUpSessionAdmission {
  private lastRequest: PendingRequest | null = null;
  private serial = 0;
  private clockOffsetMs = 0;

  async create(
    shifuBid: string,
    outlineBid: string,
    payload: LiveFollowUpSessionRequest,
    isCurrent: () => boolean,
    onReason?: (reason: 'user_start' | 'takeover') => void,
    allowTakeover = true,
  ): Promise<LiveFollowUpSession> {
    const serial = ++this.serial;
    const assertCurrent = () => {
      if (serial !== this.serial || !isCurrent()) {
        throw new DOMException(
          'Live follow-up request cancelled',
          'AbortError',
        );
      }
    };
    assertCurrent();
    const deadline = performance.now() + 20_000;
    let previous = this.lastRequest;
    // A lost legacy response cannot be looked up on an old server. Waiting out
    // the bounded operation retention also outlives every possible credential.
    if (
      previous &&
      performance.now() - previous.startedAt >= REQUEST_RETENTION_MS
    ) {
      previous = null;
      this.lastRequest = null;
    }
    const target: LiveFollowUpSessionRequest = {
      anchor_element_bid: payload.anchor_element_bid,
      preview_mode: payload.preview_mode,
      learning_mode: payload.learning_mode,
      surface: payload.surface,
    };
    // Server discovery survives refresh without keeping bearer credentials or
    // requiring the previous page to successfully send its lifecycle cleanup.
    let owner = await getLiveFollowUpOwner();
    assertCurrent();
    if (!owner) throw new LiveFollowUpControlError('admission_unavailable');
    const observedRevision = owner.admission_revision;
    if (!allowTakeover && owner.rotation_enabled) {
      if (!previous) throw new LiveFollowUpControlError('ownership_conflict');
      const own = await getLiveFollowUpOperationStatus(
        previous.shifuBid,
        previous.outlineBid,
        previous.requestBid,
        previous.target,
      );
      assertCurrent();
      if (
        !own ||
        own.request_bid !== previous.requestBid ||
        !own.ownership_current ||
        own.admission_revision !== observedRevision
      ) {
        throw new LiveFollowUpControlError('ownership_conflict');
      }
    }
    onReason?.(
      owner.rotation_enabled && observedRevision ? 'takeover' : 'user_start',
    );
    while (owner.rotation_enabled && owner.operation_status === 'pending') {
      if (performance.now() + 500 >= deadline)
        throw new LiveFollowUpControlError('pending');
      await new Promise(resolve => setTimeout(resolve, 500));
      assertCurrent();
      owner = await getLiveFollowUpOwner();
      assertCurrent();
      if (!owner || owner.admission_revision !== observedRevision) {
        throw new LiveFollowUpControlError('ownership_conflict');
      }
    }
    if (owner.operation_status === 'rejected') {
      throw new LiveFollowUpControlError(
        owner.error_code ?? 'admission_unavailable',
        undefined,
        owner.capacity_scopes,
      );
    }
    if (owner.rotation_enabled) {
      target.operation = 'takeover';
      target.expected_admission_revision = owner.admission_revision ?? '';
    } else if (previous) {
      const status = await getLiveFollowUpOperationStatus(
        previous.shifuBid,
        previous.outlineBid,
        previous.requestBid,
        previous.target,
      );
      assertCurrent();
      if (!status || status.request_bid !== previous.requestBid) {
        throw new LiveFollowUpControlError('admission_unavailable');
      }
      if (status.operation_status === 'rejected') {
        throw controlFailure(status);
      }
      if (status.operation_status === 'pending') {
        throw new LiveFollowUpControlError('pending', status.retry_after_ms);
      }
      if (status.operation_status === 'missing') {
        previous = null;
        this.lastRequest = null;
      } else if (
        status.ownership_current &&
        status.session_bid &&
        status.admission_revision
      ) {
        target.replace_session_bid = status.session_bid;
        target.expected_admission_revision = status.admission_revision;
      } else {
        throw new LiveFollowUpControlError('ownership_conflict');
      }
    }

    // A server-confirmed pre-mint clock rejection permits one correction. An
    // ambiguous HTTP failure never retries creation or replays learner input.
    for (let correction = 0; correction < 2; correction += 1) {
      assertCurrent();
      if (performance.now() >= deadline)
        throw new LiveFollowUpControlError('admission_unavailable');
      const requestBid = createLiveFollowUpRequestBid(
        Date.now() + this.clockOffsetMs,
      );
      this.lastRequest = {
        shifuBid,
        outlineBid,
        requestBid,
        target,
        startedAt: performance.now(),
      };
      const result = await createLiveFollowUpSession(shifuBid, outlineBid, {
        ...target,
        operation: target.operation ?? 'create',
        request_bid: requestBid,
      }).catch(async (error: unknown) => {
        if (
          serial === this.serial &&
          error instanceof Error &&
          'code' in error &&
          error.code === LIVE_FOLLOW_UP_CAPACITY_ERROR_CODE
        ) {
          // Legacy capacity rejection is known to happen before token minting.
          // Keep the previous owner; an unknown transport failure is different.
          this.lastRequest = previous;
        } else if (
          owner.rotation_enabled &&
          serial === this.serial &&
          isCurrent() &&
          performance.now() < deadline
        ) {
          // A lost response may already have disclosed a credential. Inspect
          // metadata only; never repeat minting or cache/recover bearer tokens.
          await getLiveFollowUpOperationStatus(
            shifuBid,
            outlineBid,
            requestBid,
            target,
          ).catch(() => undefined);
        }
        throw error;
      });
      if (result && 'ephemeral_token' in result) {
        // Return even a stale success so the controller can retire exactly its
        // own session. It must not overwrite a later request's recovery identity.
        if (serial === this.serial && result.request_bid === undefined) {
          this.lastRequest = null;
        }
        return owner.rotation_enabled
          ? {
              ...result,
              previous_admission_revision: target.expected_admission_revision,
            }
          : result;
      }
      assertCurrent();
      if (!result || result.request_bid !== requestBid) {
        throw new LiveFollowUpControlError('response_lost');
      }
      if (result.operation_status === 'rejected') {
        this.lastRequest = previous;
        const serverTime = Date.parse(result.server_time ?? '');
        if (
          correction === 0 &&
          result.error_code === 'stale_request' &&
          Number.isFinite(serverTime)
        ) {
          this.clockOffsetMs = serverTime - Date.now();
          continue;
        }
        throw controlFailure(result);
      }
      throw new LiveFollowUpControlError(
        result.operation_status === 'pending' ? 'pending' : 'response_lost',
        result.retry_after_ms,
      );
    }
    throw new LiveFollowUpControlError('stale_request');
  }
}
