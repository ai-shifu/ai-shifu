import { renderHook } from '@testing-library/react';
import { useTracking } from './use-tracking';

const mockTracking = jest.fn();

jest.mock('@/lib/tracking', () => ({
  EVENT_NAMES: {},
  tracking: (...args: unknown[]) => mockTracking(...args),
}));

describe('useTracking', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTracking.mockResolvedValue(undefined);
  });

  it('forwards the producer allowlist without implicit enrichment', async () => {
    const { result } = renderHook(() => useTracking());
    const producerPayload = {
      outcome: 'success',
      shifu_bid: 'course-bid',
    };

    await result.current.trackEvent('course_share_result', producerPayload);

    expect(mockTracking).toHaveBeenCalledWith(
      'course_share_result',
      producerPayload,
    );
    expect(mockTracking.mock.calls[0]?.[1]).not.toHaveProperty('device');
    expect(mockTracking.mock.calls[0]?.[1]).not.toHaveProperty('timeStamp');
    expect(mockTracking.mock.calls[0]?.[1]).not.toHaveProperty('user_id');
    expect(mockTracking.mock.calls[0]?.[1]).not.toHaveProperty('user_type');
  });

  it('keeps caller behavior fail-open when tracking throws or rejects', async () => {
    const { result } = renderHook(() => useTracking());

    mockTracking.mockImplementationOnce(() => {
      throw new Error('sync tracking failure');
    });
    await expect(
      result.current.trackEvent('sync_failure'),
    ).resolves.toBeUndefined();

    mockTracking.mockRejectedValueOnce(new Error('async tracking failure'));
    await expect(
      result.current.trackEvent('async_failure'),
    ).resolves.toBeUndefined();
    await Promise.resolve();
  });
});
