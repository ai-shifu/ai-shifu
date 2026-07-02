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

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
};

describe('useShifu draft meta handling', () => {
  beforeEach(() => {
    mockSaveMdflow.mockReset();
    mockGetShifuDraftMeta.mockReset();
  });

  it('loads draft meta without browser timezone', async () => {
    mockGetShifuDraftMeta.mockResolvedValue({
      revision: 2,
      updated_at: '2026-06-30T05:37:42Z',
      updated_user: null,
    });

    const { result } = renderHook(() => useShifu(), { wrapper });

    await act(async () => {
      result.current.actions.setCurrentNode({
        bid: 'lesson-1',
        depth: 1,
      } as any);
      await result.current.actions.loadDraftMeta('shifu-1', 'lesson-1');
    });

    expect(mockGetShifuDraftMeta).toHaveBeenCalledWith({
      shifu_bid: 'shifu-1',
      outline_bid: 'lesson-1',
    });
    expect(result.current.latestDraftMeta?.updated_at).toBe(
      '2026-06-30T05:37:42Z',
    );
  });

  it('refreshes draft meta after saving mdflow successfully', async () => {
    mockSaveMdflow.mockResolvedValue({ new_revision: 9 });
    mockGetShifuDraftMeta.mockResolvedValue({
      revision: 9,
      updated_at: '2026-06-30T05:37:42Z',
      updated_user: null,
    });

    const { result } = renderHook(() => useShifu(), { wrapper });

    await act(async () => {
      result.current.actions.setCurrentNode({
        bid: 'lesson-1',
        depth: 1,
      } as any);
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
      });
      expect(result.current.latestDraftMeta?.revision).toBe(9);
    });
  });

  it('does not clear current draft meta when a stale outline request fails', async () => {
    const consoleErrorSpy = jest
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);
    const lessonOneDraftMeta = createDeferred<unknown>();
    mockGetShifuDraftMeta.mockImplementation(({ outline_bid }) => {
      if (outline_bid === 'lesson-1') {
        return lessonOneDraftMeta.promise;
      }
      return Promise.resolve({
        revision: 3,
        updated_at: '2026-06-30T06:37:42Z',
        updated_user: null,
      });
    });

    const { result } = renderHook(() => useShifu(), { wrapper });

    let lessonOnePromise: Promise<unknown> | null = null;
    await act(async () => {
      result.current.actions.setCurrentNode({
        bid: 'lesson-1',
        depth: 1,
      } as any);
      lessonOnePromise = result.current.actions.loadDraftMeta(
        'shifu-1',
        'lesson-1',
      );
    });

    await act(async () => {
      result.current.actions.setCurrentNode({
        bid: 'lesson-2',
        depth: 1,
      } as any);
      await result.current.actions.loadDraftMeta('shifu-1', 'lesson-2');
    });

    expect(result.current.latestDraftMeta?.revision).toBe(3);

    await act(async () => {
      lessonOneDraftMeta.reject(new Error('stale failure'));
      await lessonOnePromise;
    });

    expect(result.current.latestDraftMeta?.revision).toBe(3);
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Failed to load draft meta',
      expect.any(Error),
    );
    consoleErrorSpy.mockRestore();
  });
});
