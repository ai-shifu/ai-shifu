import { act, renderHook, waitFor } from '@testing-library/react';

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getCreatorOnboardingStatus: jest.fn(),
  },
}));

import { useOnboarding } from './useOnboarding';

jest.mock('@/lib/onboardingTargets', () => ({
  __esModule: true,
  getOnboardingTargetElement: jest.fn(),
}));

const { getOnboardingTargetElement } = jest.requireMock(
  '@/lib/onboardingTargets',
) as {
  getOnboardingTargetElement: jest.Mock;
};

describe('useOnboarding', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  beforeEach(() => {
    getOnboardingTargetElement.mockReset();
    getOnboardingTargetElement.mockReturnValue(null);
  });

  test('closes and resets when onboarding becomes disabled', async () => {
    const onComplete = jest.fn();
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useOnboarding({
          enabled,
          steps: [
            {
              id: 'welcome',
              title: 'Welcome',
              description: 'Hello',
            },
          ],
          onComplete,
        }),
      {
        initialProps: { enabled: true },
      },
    );

    await waitFor(() => {
      expect(result.current.isOpen).toBe(true);
    });

    rerender({ enabled: false });

    await waitFor(() => {
      expect(result.current.isOpen).toBe(false);
      expect(result.current.currentStepIndex).toBe(0);
      expect(result.current.targetRect).toBeNull();
    });
  });

  test('completes automatically when the final missing target is skipped', async () => {
    jest.useFakeTimers();
    const onComplete = jest.fn().mockResolvedValue(undefined);
    const onStepMissing = jest.fn();

    const { result } = renderHook(() =>
      useOnboarding({
        enabled: true,
        steps: [
          {
            id: 'guide_course',
            title: 'Guide',
            description: 'Guide card',
            targetId: 'guide-course-card',
            skipWhenTargetMissing: true,
            waitForTargetMs: 50,
          },
        ],
        onComplete,
        onStepMissing,
      }),
    );

    await waitFor(() => {
      expect(result.current.isOpen).toBe(true);
    });

    await act(async () => {
      jest.advanceTimersByTime(80);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onStepMissing).toHaveBeenCalledTimes(1);
      expect(onComplete).toHaveBeenCalledTimes(1);
      expect(result.current.isOpen).toBe(false);
    });
  });

  test('skips a missing middle target and continues to the next step', async () => {
    jest.useFakeTimers();
    const onComplete = jest.fn().mockResolvedValue(undefined);
    const onStepMissing = jest.fn();

    const { result } = renderHook(() =>
      useOnboarding({
        enabled: true,
        steps: [
          {
            id: 'missing-balance',
            title: 'Balance',
            description: 'Balance',
            targetId: 'billing-balance',
            skipWhenTargetMissing: true,
            waitForTargetMs: 50,
          },
          {
            id: 'create',
            title: 'Create',
            description: 'Create',
          },
        ],
        onComplete,
        onStepMissing,
      }),
    );

    await waitFor(() => {
      expect(result.current.currentStep?.id).toBe('missing-balance');
    });

    await act(async () => {
      jest.advanceTimersByTime(80);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onStepMissing).toHaveBeenCalledTimes(1);
      expect(result.current.currentStep?.id).toBe('create');
      expect(result.current.isOpen).toBe(true);
      expect(onComplete).not.toHaveBeenCalled();
    });
  });

  test('does not resync target rect when only callback identities change', async () => {
    const target = document.createElement('div');
    target.getBoundingClientRect = jest.fn(
      () =>
        ({
          top: 10,
          left: 20,
          width: 120,
          height: 40,
          bottom: 50,
          right: 140,
          x: 20,
          y: 10,
          toJSON: () => ({}),
        }) as DOMRect,
    );
    getOnboardingTargetElement.mockReturnValue(target);
    const steps = [
      {
        id: 'create',
        title: 'Create',
        description: 'Create course',
        targetId: 'create-course',
      },
    ];

    const { result, rerender } = renderHook(
      ({ marker }: { marker: number }) =>
        useOnboarding({
          enabled: true,
          steps,
          onComplete: jest.fn(() => {
            void marker;
          }),
          onStepResolved: jest.fn(() => {
            void marker;
          }),
        }),
      {
        initialProps: { marker: 1 },
      },
    );

    await waitFor(() => {
      expect(result.current.targetRect).not.toBeNull();
    });
    const firstRect = result.current.targetRect;

    rerender({ marker: 2 });

    expect(result.current.targetRect).toBe(firstRect);
    expect(target.getBoundingClientRect).toHaveBeenCalledTimes(1);
  });
});
