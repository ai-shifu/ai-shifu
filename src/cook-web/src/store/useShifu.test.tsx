import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';

const mockSaveMdflow = jest.fn();
const mockGetShifuDraftMeta = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    saveMdflow: (...args: unknown[]) => mockSaveMdflow(...args),
    getShifuDraftMeta: (...args: unknown[]) => mockGetShifuDraftMeta(...args),
  },
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: jest.fn(),
  }),
}));

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: jest.fn(() => 'Asia/Shanghai'),
}));

jest.mock('@/c-api/studyV2', () => ({
  LEARNING_PERMISSION: {
    GUEST: 'guest',
    TRIAL: 'trial',
  },
}));

import { ShifuProvider, useShifu } from './useShifu';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <ShifuProvider>{children}</ShifuProvider>
);

describe('useShifu draft meta timezone handling', () => {
  beforeEach(() => {
    mockSaveMdflow.mockReset();
    mockGetShifuDraftMeta.mockReset();
  });

  it('passes browser timezone when loading draft meta', async () => {
    mockGetShifuDraftMeta.mockResolvedValue({
      revision: 2,
      updated_at: '2026-06-30T13:37:42+08:00',
      updated_user: null,
    });

    const { result } = renderHook(() => useShifu(), { wrapper });

    await act(async () => {
      await result.current.actions.loadDraftMeta('shifu-1', 'lesson-1');
    });

    expect(mockGetShifuDraftMeta).toHaveBeenCalledWith({
      shifu_bid: 'shifu-1',
      outline_bid: 'lesson-1',
      timezone: 'Asia/Shanghai',
    });
    expect(result.current.latestDraftMeta?.updated_at).toBe(
      '2026-06-30T13:37:42+08:00',
    );
  });

  it('refreshes draft meta after saving mdflow successfully', async () => {
    mockSaveMdflow.mockResolvedValue({ new_revision: 9 });
    mockGetShifuDraftMeta.mockResolvedValue({
      revision: 9,
      updated_at: '2026-06-30T13:37:42+08:00',
      updated_user: null,
    });

    const { result } = renderHook(() => useShifu(), { wrapper });

    await act(async () => {
      await result.current.actions.saveMdflow({
        shifu_bid: 'shifu-1',
        outline_bid: 'lesson-1',
        data: 'updated content',
      });
    });

    expect(mockSaveMdflow).toHaveBeenCalledWith({
      shifu_bid: 'shifu-1',
      outline_bid: 'lesson-1',
      data: 'updated content',
      base_revision: undefined,
    });
    await waitFor(() => {
      expect(mockGetShifuDraftMeta).toHaveBeenCalledWith({
        shifu_bid: 'shifu-1',
        outline_bid: 'lesson-1',
        timezone: 'Asia/Shanghai',
      });
      expect(result.current.latestDraftMeta?.revision).toBe(9);
    });
  });
});
