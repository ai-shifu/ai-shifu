import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BillingSidebarCard } from './BillingSidebarCard';

const mockTrackEvent = jest.fn();
const mockNavigationContinuation = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({
    children,
    href,
    onAuxClick,
    onClick,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
    children?: React.ReactNode;
    href: string;
  }) => (
    <a
      href={href}
      onClick={event => {
        onClick?.(event);
        if (!event.defaultPrevented) {
          mockNavigationContinuation(href);
        }
        event.preventDefault();
      }}
      onAuxClick={event => {
        onAuxClick?.(event);
        if (!event.defaultPrevented && event.button === 1) {
          mockNavigationContinuation(href);
        }
        event.preventDefault();
      }}
      {...props}
    >
      {children}
    </a>
  ),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: mockTrackEvent,
  }),
}));

describe('BillingSidebarCard', () => {
  beforeEach(() => {
    mockTrackEvent.mockReset();
    mockNavigationContinuation.mockReset();
  });

  const renderCard = () => {
    render(<BillingSidebarCard />);
    return screen.getByRole('link', {
      name: 'module.billing.sidebar.summaryTitle module.billing.sidebar.upgradeCta',
    });
  };

  test('tracks one privacy-safe event for a primary packages activation', () => {
    const packagesLink = renderCard();

    expect(mockTrackEvent).not.toHaveBeenCalled();

    fireEvent.click(packagesLink);

    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith(
      'creator_billing_sidebar_packages_click',
      {},
    );
    expect(mockNavigationContinuation).toHaveBeenCalledWith(
      '/admin/billing?tab=packages',
    );
  });

  test('tracks keyboard, modifier, and middle-button new-tab activations once each', async () => {
    const user = userEvent.setup();
    const packagesLink = renderCard();

    packagesLink.focus();
    await user.keyboard('{Enter}');
    fireEvent.click(packagesLink, { metaKey: true });
    fireEvent.click(packagesLink, { ctrlKey: true });
    fireEvent.click(packagesLink, { shiftKey: true });
    fireEvent(
      packagesLink,
      new MouseEvent('auxclick', {
        bubbles: true,
        button: 1,
        cancelable: true,
      }),
    );

    expect(mockTrackEvent.mock.calls).toEqual(
      Array.from({ length: 5 }, () => [
        'creator_billing_sidebar_packages_click',
        {},
      ]),
    );
    expect(mockNavigationContinuation).toHaveBeenCalledTimes(5);
    expect(mockNavigationContinuation).toHaveBeenCalledWith(
      '/admin/billing?tab=packages',
    );
  });

  test('does not track render, rerender, Space, or a right-button auxiliary click', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<BillingSidebarCard />);
    const packagesLink = screen.getByRole('link', {
      name: 'module.billing.sidebar.summaryTitle module.billing.sidebar.upgradeCta',
    });

    rerender(<BillingSidebarCard isLoading />);
    packagesLink.focus();
    await user.keyboard(' ');
    fireEvent(
      packagesLink,
      new MouseEvent('auxclick', {
        bubbles: true,
        button: 2,
        cancelable: true,
      }),
    );

    expect(mockTrackEvent).not.toHaveBeenCalled();
    expect(mockNavigationContinuation).not.toHaveBeenCalled();
  });

  test('does not track the independent billing-details link', () => {
    renderCard();

    fireEvent.click(
      screen.getByRole('link', {
        name: 'module.billing.sidebar.usageCta',
      }),
    );

    expect(mockTrackEvent).not.toHaveBeenCalled();
    expect(mockNavigationContinuation).toHaveBeenCalledWith(
      '/admin/billing?tab=details',
    );
  });

  test('keeps native link navigation available when tracking throws', () => {
    mockTrackEvent.mockImplementationOnce(() => {
      throw new Error('tracking unavailable');
    });
    const packagesLink = renderCard();

    expect(() => fireEvent.click(packagesLink)).not.toThrow();
    expect(mockNavigationContinuation).toHaveBeenCalledWith(
      '/admin/billing?tab=packages',
    );
  });

  test('keeps native link navigation available when tracking rejects', async () => {
    mockTrackEvent.mockRejectedValueOnce(new Error('tracking unavailable'));
    const packagesLink = renderCard();

    fireEvent.click(packagesLink);
    await Promise.resolve();

    expect(mockNavigationContinuation).toHaveBeenCalledWith(
      '/admin/billing?tab=packages',
    );
  });
});
