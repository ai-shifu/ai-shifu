import {
  createLiveFollowUpSession,
  getLiveFollowUpOperationStatus,
  type LiveFollowUpOperationResult,
  type LiveFollowUpSessionRequest,
} from '@/lib/liveVoiceFollowUp';

import {
  createLiveFollowUpRequestBid,
  LiveFollowUpSessionAdmission,
} from './liveFollowUpSessionAdmission';

jest.mock('@/lib/liveVoiceFollowUp', () => ({
  ...jest.requireActual('@/lib/liveVoiceFollowUp'),
  createLiveFollowUpSession: jest.fn(),
  getLiveFollowUpOperationStatus: jest.fn(),
}));
jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

const target: LiveFollowUpSessionRequest = {
  anchor_element_bid: 'anchor-1',
  preview_mode: false,
  learning_mode: 'read',
  surface: 'read_content',
};
const current = () => true;

describe('Live follow-up controlled admission', () => {
  const create = jest.mocked(createLiveFollowUpSession);
  const status = jest.mocked(getLiveFollowUpOperationStatus);
  const issued = (requestBid?: string) => ({
    session_bid: 'session-1',
    ephemeral_token: 'auth_tokens/secret',
    websocket_url: 'wss://example.invalid',
    setup: { setup: { systemInstruction: 'private prompt' } },
    history: null,
    expires_at: '2026-09-05T01:15:00Z',
    new_session_expires_at: '2026-09-05T01:01:00Z',
    heartbeat_interval_ms: 15_000,
    ...(requestBid && {
      request_bid: requestBid,
      operation_status: 'issued' as const,
      admission_revision: 'revision-1',
      rotation_enabled: true,
    }),
  });
  const statusResult = (
    patch: Partial<LiveFollowUpOperationResult> = {},
  ): LiveFollowUpOperationResult => ({
    request_bid: create.mock.calls[0][2].request_bid!,
    operation_status: 'issued',
    session_bid: 'session-1',
    admission_revision: 'revision-1',
    ownership_current: true,
    rotation_enabled: true,
    ...patch,
  });
  let admission: LiveFollowUpSessionAdmission;

  beforeEach(() => {
    jest.resetAllMocks();
    admission = new LiveFollowUpSessionAdmission();
    create.mockImplementation(async (_course, _outline, payload) =>
      issued(payload.request_bid),
    );
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('generates a timestamped cryptographically random UUIDv7', () => {
    const timestamp = Date.parse('2026-09-05T00:00:00Z');
    const id = createLiveFollowUpRequestBid(timestamp);
    expect(id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(parseInt(id.replaceAll('-', '').slice(0, 12), 16)).toBe(timestamp);
    expect(createLiveFollowUpRequestBid(timestamp)).not.toBe(id);
  });

  it('creates once with no status, token cache, or caller-supplied ownership', async () => {
    const session = await admission.create(
      'course-1',
      'outline-1',
      { ...target, replace_session_bid: 'untrusted-owner' },
      current,
    );
    expect(session.ephemeral_token).toBe('auth_tokens/secret');
    expect(status).not.toHaveBeenCalled();
    expect(create).toHaveBeenCalledWith('course-1', 'outline-1', {
      ...target,
      operation: 'create',
      request_bid: expect.any(String),
    });
    expect(JSON.stringify(admission)).not.toMatch(/secret|prompt|history/);
  });

  it('looks up the original immutable target before replacing across courses', async () => {
    await admission.create('course-1', 'outline-1', target, current);
    status.mockResolvedValueOnce(statusResult());
    await admission.create(
      'course-2',
      'outline-2',
      { ...target, anchor_element_bid: 'anchor-2' },
      current,
    );
    expect(status).toHaveBeenCalledWith(
      'course-1',
      'outline-1',
      create.mock.calls[0][2].request_bid,
      target,
    );
    expect(create.mock.calls[1]).toEqual([
      'course-2',
      'outline-2',
      {
        ...target,
        anchor_element_bid: 'anchor-2',
        operation: 'create',
        request_bid: expect.any(String),
        replace_session_bid: 'session-1',
        expected_admission_revision: 'revision-1',
      },
    ]);
  });

  it('recovers a lost create response by metadata, never by re-minting its ID', async () => {
    create.mockRejectedValueOnce(new Error('lost response'));
    await expect(
      admission.create('course-1', 'outline-1', target, current),
    ).rejects.toThrow('lost response');
    const firstId = create.mock.calls[0][2].request_bid;
    status.mockResolvedValueOnce(statusResult());
    await admission.create('course-1', 'outline-1', target, current);
    expect(status.mock.calls[0][2]).toBe(firstId);
    expect(create.mock.calls[1][2].request_bid).not.toBe(firstId);
    expect(create.mock.calls[1][2].replace_session_bid).toBe('session-1');
  });

  it.each(['pending', 'rejected', 'issued'] as const)(
    'does not create after a blocked/non-owned status: %s',
    async operation_status => {
      await admission.create('course-1', 'outline-1', target, current);
      status.mockResolvedValueOnce(
        statusResult({
          operation_status,
          ownership_current: false,
          error_code: 'admission_unavailable',
          retry_after_ms: 800,
        }),
      );
      await expect(
        admission.create('course-1', 'outline-1', target, current),
      ).rejects.toHaveProperty(
        'reason',
        operation_status === 'pending'
          ? 'pending'
          : operation_status === 'rejected'
            ? 'admission_unavailable'
            : 'ownership_conflict',
      );
      expect(create).toHaveBeenCalledTimes(1);
    },
  );

  it('allows missing expired operation metadata to proceed through fresh server admission', async () => {
    await admission.create('course-1', 'outline-1', target, current);
    status.mockResolvedValueOnce(statusResult({ operation_status: 'missing' }));
    await admission.create('course-1', 'outline-1', target, current);
    expect(create.mock.calls[1][2]).not.toHaveProperty('replace_session_bid');
  });

  it('keeps the previous recovery identity after a definite pre-mint rejection', async () => {
    await admission.create('course-1', 'outline-1', target, current);
    const firstId = create.mock.calls[0][2].request_bid;
    status.mockResolvedValue(statusResult());
    create.mockImplementationOnce(async (_course, _outline, payload) => ({
      request_bid: payload.request_bid!,
      operation_status: 'rejected',
      error_code: 'capacity_exceeded',
      rotation_enabled: true,
      retry_after_ms: 2000,
    }));
    await expect(
      admission.create('course-1', 'outline-1', target, current),
    ).rejects.toMatchObject({
      reason: 'capacity_exceeded',
      retryAfterMs: 2000,
    });
    await admission.create('course-1', 'outline-1', target, current);
    expect(status.mock.calls[1][2]).toBe(firstId);
  });

  it('corrects clock only once after a confirmed pre-mint stale request', async () => {
    jest.spyOn(Date, 'now').mockReturnValue(1000);
    create.mockImplementationOnce(async (_course, _outline, payload) => ({
      request_bid: payload.request_bid!,
      operation_status: 'rejected',
      error_code: 'stale_request',
      rotation_enabled: true,
      server_time: '2026-09-05T00:00:00Z',
    }));
    await admission.create('course-1', 'outline-1', target, current);
    expect(create).toHaveBeenCalledTimes(2);
    const corrected = create.mock.calls[1][2].request_bid!;
    expect(parseInt(corrected.replaceAll('-', '').slice(0, 12), 16)).toBe(
      Date.parse('2026-09-05T00:00:00Z'),
    );
    expect(status).not.toHaveBeenCalled();
  });

  it('does not loop on repeated stale rejection or correct other failures', async () => {
    create.mockImplementation(async (_course, _outline, payload) => ({
      request_bid: payload.request_bid!,
      operation_status: 'rejected',
      error_code: 'stale_request',
      rotation_enabled: true,
      server_time: '2026-09-05T00:00:00Z',
    }));
    await expect(
      admission.create('course-1', 'outline-1', target, current),
    ).rejects.toHaveProperty('reason', 'stale_request');
    expect(create).toHaveBeenCalledTimes(2);
  });

  it('does not expose metadata-only replay as a usable session', async () => {
    create.mockImplementationOnce(async (_course, _outline, payload) => ({
      request_bid: payload.request_bid!,
      operation_status: 'issued',
      rotation_enabled: true,
      ownership_current: true,
      session_bid: 'session-1',
      admission_revision: 'revision-1',
    }));
    await expect(
      admission.create('course-1', 'outline-1', target, current),
    ).rejects.toHaveProperty('reason', 'response_lost');
    expect(create).toHaveBeenCalledTimes(1);
    status.mockResolvedValueOnce(statusResult());
    await admission.create('course-1', 'outline-1', target, current);
    expect(create.mock.calls[1][2].replace_session_bid).toBe('session-1');
  });

  it('recovers the successor identity after a post-admission provider failure', async () => {
    await admission.create('course-1', 'outline-1', target, current);
    status.mockResolvedValueOnce(statusResult());
    create.mockImplementationOnce(async (_course, _outline, payload) => ({
      request_bid: payload.request_bid!,
      operation_status: 'failed',
      session_bid: 'session-2',
      admission_revision: 'revision-2',
      ownership_current: true,
      rotation_enabled: true,
    }));
    await expect(
      admission.create('course-1', 'outline-1', target, current),
    ).rejects.toHaveProperty('reason', 'response_lost');
    const failedId = create.mock.calls[1][2].request_bid!;
    status.mockResolvedValueOnce({
      ...statusResult(),
      request_bid: failedId,
      operation_status: 'failed',
      session_bid: 'session-2',
      admission_revision: 'revision-2',
    });
    await admission.create('course-1', 'outline-1', target, current);
    expect(status.mock.calls[1][2]).toBe(failedId);
    expect(create.mock.calls[2][2]).toMatchObject({
      replace_session_bid: 'session-2',
      expected_admission_revision: 'revision-2',
    });
  });

  it('cancels after status without minting or consuming a new identity', async () => {
    await admission.create('course-1', 'outline-1', target, current);
    let active = true;
    status.mockImplementationOnce(async () => {
      active = false;
      return statusResult();
    });
    await expect(
      admission.create('course-2', 'outline-2', target, () => active),
    ).rejects.toHaveProperty('name', 'AbortError');
    expect(create).toHaveBeenCalledTimes(1);
  });

  it('returns a late successful session for targeted controller cleanup only', async () => {
    let resolveFirst!: (value: ReturnType<typeof issued>) => void;
    create.mockImplementationOnce(
      () => new Promise(resolve => (resolveFirst = resolve)),
    );
    const first = admission.create('course-1', 'outline-1', target, current);
    status.mockResolvedValueOnce(statusResult());
    const second = await admission.create(
      'course-2',
      'outline-2',
      target,
      current,
    );
    resolveFirst(issued(create.mock.calls[0][2].request_bid));
    await expect(first).resolves.toHaveProperty('session_bid', 'session-1');
    status.mockResolvedValueOnce({
      ...statusResult(),
      request_bid: second.request_bid!,
    });
    await admission.create('course-2', 'outline-2', target, current);
    expect(status.mock.calls[1][2]).toBe(second.request_bid);
  });

  it('lets known legacy sessions use the existing expiry guard without status calls', async () => {
    create.mockResolvedValueOnce(issued());
    await admission.create('course-1', 'outline-1', target, current);
    await admission.create('course-1', 'outline-1', target, current);
    expect(status).not.toHaveBeenCalled();
  });

  it('does not retain a definitively rejected legacy capacity request', async () => {
    create.mockRejectedValueOnce(
      Object.assign(new Error('capacity'), { code: 4018 }),
    );
    await expect(
      admission.create('course-1', 'outline-1', target, current),
    ).rejects.toHaveProperty('code', 4018);
    await admission.create('course-1', 'outline-1', target, current);
    expect(status).not.toHaveBeenCalled();
  });

  it('expires unknown metadata only after the complete operation retention', async () => {
    const now = jest.spyOn(performance, 'now').mockReturnValue(0);
    create.mockRejectedValueOnce(new Error('legacy response lost'));
    await expect(
      admission.create('course-1', 'outline-1', target, current),
    ).rejects.toThrow();
    now.mockReturnValue(20 * 60_000);
    await admission.create('course-1', 'outline-1', target, current);
    expect(status).not.toHaveBeenCalled();
  });
});
