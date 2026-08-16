import { act, render, screen, waitFor } from '@testing-library/react';
import { ToastAction } from '@/components/ui/Toast';
import { Toaster } from '@/components/ui/Toaster';
import { toast, toastOnce } from './useToast';

let mockPathname = '/current-page';

jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

describe('toast duration', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockPathname = '/current-page';
  });

  afterEach(() => {
    act(() => {
      toast({ title: 'cleanup', duration: 0 }).dismiss();
      jest.runOnlyPendingTimers();
    });
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('keeps a zero-duration toast and its action visible past the provider default', () => {
    const timeoutSpy = jest.spyOn(window, 'setTimeout');
    const retryLabel = 'Retry refresh';
    render(<Toaster />);

    act(() => {
      toast({
        title: 'Rate added, but refresh failed',
        duration: 0,
        action: (
          <ToastAction altText='Retry refreshing the rate list'>
            {retryLabel}
          </ToastAction>
        ),
      });
    });

    expect(
      screen.getByText('Rate added, but refresh failed'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: retryLabel }),
    ).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(6000);
    });

    expect(
      screen.getByText('Rate added, but refresh failed'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: retryLabel }),
    ).toBeInTheDocument();
    expect(
      timeoutSpy.mock.calls.some(
        ([, delay]) => delay === Number.POSITIVE_INFINITY,
      ),
    ).toBe(false);
  });

  it('dismisses a finite-duration toast on schedule', () => {
    render(<Toaster />);

    act(() => {
      toast({ title: 'Temporary notice', duration: 100 });
    });
    expect(screen.getByText('Temporary notice')).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(100);
    });

    expect(screen.queryByText('Temporary notice')).not.toBeInTheDocument();
  });

  it('dismisses a route-scoped permanent toast after navigation', async () => {
    const { rerender } = render(<Toaster />);

    act(() => {
      toast({
        title: 'Credit notice',
        duration: 0,
        dismissOnNavigation: true,
      });
    });
    expect(screen.getByText('Credit notice')).toBeInTheDocument();

    act(() => {
      mockPathname = '/next-page';
      rerender(<Toaster />);
    });

    await waitFor(() => {
      expect(screen.queryByText('Credit notice')).not.toBeInTheDocument();
    });
  });
});

describe('toastOnce', () => {
  afterEach(() => {
    act(() => {
      toast({ title: 'cleanup', duration: 0 }).dismiss();
    });
  });

  it('suppresses duplicates while the previous toast is still visible', () => {
    const first = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'first',
      duration: 0,
    });
    const second = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'second',
      duration: 0,
    });

    expect(second.id).toBe(first.id);
  });

  it('suppresses permanent duplicates until the previous toast is dismissed', () => {
    jest.useFakeTimers();
    const first = toastOnce({
      dedupeKey: 'credit-insufficient:teacher:7101',
      dedupeWindowMs: Number.POSITIVE_INFINITY,
      title: 'first',
      duration: 0,
    });

    act(() => {
      jest.advanceTimersByTime(60_000);
    });

    const duplicate = toastOnce({
      dedupeKey: 'credit-insufficient:teacher:7101',
      dedupeWindowMs: Number.POSITIVE_INFINITY,
      title: 'duplicate',
      duration: 0,
    });
    expect(duplicate.id).toBe(first.id);

    act(() => first.dismiss());
    const afterDismiss = toastOnce({
      dedupeKey: 'credit-insufficient:teacher:7101',
      dedupeWindowMs: Number.POSITIVE_INFINITY,
      title: 'after dismiss',
      duration: 0,
    });
    expect(afterDismiss.id).not.toBe(first.id);
    jest.useRealTimers();
  });

  it('re-shows a deduped toast after the previous toast is dismissed', () => {
    const first = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'first',
      duration: 0,
    });

    act(() => {
      first.dismiss();
    });

    const second = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'second',
      duration: 0,
    });

    expect(second.id).not.toBe(first.id);
  });

  it('re-shows a deduped toast after another toast replaces the previous one', () => {
    const first = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'first',
      duration: 0,
    });

    toast({ title: 'replacement', duration: 0 });

    const second = toastOnce({
      dedupeKey: 'ai-service-unavailable',
      title: 'second',
      duration: 0,
    });

    expect(second.id).not.toBe(first.id);
  });
});
