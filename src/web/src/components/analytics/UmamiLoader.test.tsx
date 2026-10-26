import { render } from '@testing-library/react';
import { UmamiLoader } from './UmamiLoader';

const mockTrackPageview = jest.fn();
const mockFlushUmamiIdentify = jest.fn();
const mockSubscribeToTrackingResume = jest.fn();
const mockUnsubscribeTrackingResume = jest.fn();
let currentPathname = '/c/private-course';

jest.mock('next/navigation', () => ({
  usePathname: () => currentPathname,
}));

jest.mock('@/lib/tracking', () => ({
  flushUmamiIdentify: (...args: unknown[]) => mockFlushUmamiIdentify(...args),
  getTrackingResumeGeneration: () => 0,
  subscribeToTrackingResume: (...args: unknown[]) =>
    mockSubscribeToTrackingResume(...args),
  trackPageview: (...args: unknown[]) => mockTrackPageview(...args),
}));

jest.mock('@/store', () => ({
  useEnvStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      umamiScriptSrc: 'https://analytics.example.test/script.js',
      umamiWebsiteId: 'website-id',
    }),
  useUserStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ isInitialized: true }),
}));

jest.mock('zustand/react/shallow', () => ({
  useShallow: (selector: unknown) => selector,
}));

describe('UmamiLoader', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSubscribeToTrackingResume.mockReturnValue(
      mockUnsubscribeTrackingResume,
    );
    currentPathname = '/c/private-course';
    window.history.replaceState(
      null,
      '',
      '/c/private-course?invite_code=secret#fragment',
    );
    document.getElementById('umami-analytics-script')?.remove();
  });

  afterEach(() => {
    document.getElementById('umami-analytics-script')?.remove();
  });

  it('owns SPA pageviews using pathname only', () => {
    const { rerender } = render(<UmamiLoader />);

    const script = document.getElementById('umami-analytics-script');
    expect(script).toHaveAttribute('data-auto-track', 'false');
    expect(script).not.toHaveAttribute('data-auto-pageview');

    expect(mockTrackPageview).toHaveBeenCalledWith('/c/private-course');
    expect(mockTrackPageview).not.toHaveBeenCalledWith(
      expect.stringContaining('invite_code'),
    );

    window.history.replaceState(
      null,
      '',
      '/c/private-course?invite_code=changed',
    );
    rerender(<UmamiLoader />);
    expect(mockTrackPageview).toHaveBeenCalledTimes(1);

    currentPathname = '/admin/orders';
    rerender(<UmamiLoader />);
    expect(mockTrackPageview).toHaveBeenNthCalledWith(2, '/admin/orders');
  });

  it('unsubscribes from tracking resumption when unmounted', () => {
    const { unmount } = render(<UmamiLoader />);
    expect(mockSubscribeToTrackingResume).toHaveBeenCalledTimes(1);
    expect(mockUnsubscribeTrackingResume).not.toHaveBeenCalled();

    unmount();

    expect(mockUnsubscribeTrackingResume).toHaveBeenCalledTimes(1);
  });
});
