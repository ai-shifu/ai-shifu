import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { KeyedMutator } from 'swr';
import api from '@/api';
import type { CreatorBillingOverview } from '@/types/billing';
import { WelcomeTrialDialog } from './WelcomeTrialDialog';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en-US',
    },
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    acknowledgeBillingTrialWelcome: jest.fn(),
  },
}));

jest.mock('@/components/ui/Button', () => ({
  Button: ({
    children,
    onClick,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
  }) => <button onClick={onClick}>{children}</button>,
}));

jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({
    children,
    showClose,
    ...props
  }: {
    children: React.ReactNode;
    showClose?: boolean;
  }) => {
    void showClose;
    return <div {...props}>{children}</div>;
  },
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

const mockAcknowledgeBillingTrialWelcome =
  api.acknowledgeBillingTrialWelcome as unknown as jest.Mock;

function buildOverview({
  creatorBid = 'creator-1',
  status = 'granted' as const,
  grantedAt = '2026-04-15T00:00:00Z',
  acknowledgedAt = null as string | null,
}: {
  creatorBid?: string;
  status?: 'granted' | 'eligible' | 'ineligible';
  grantedAt?: string | null;
  acknowledgedAt?: string | null;
}): CreatorBillingOverview {
  return {
    creator_bid: creatorBid,
    wallet: {
      available_credits: 100,
      reserved_credits: 0,
      lifetime_granted_credits: 100,
      lifetime_consumed_credits: 0,
    },
    subscription: null,
    billing_alerts: [],
    trial_offer: {
      enabled: true,
      status,
      product_bid: 'bill-product-plan-trial',
      product_code: 'creator-plan-trial',
      display_name: 'module.billing.package.free.title',
      description: 'module.billing.package.free.description',
      currency: 'CNY',
      price_amount: 0,
      credit_amount: 100,
      valid_days: 15,
      highlights: [
        'module.billing.package.features.free.publish',
        'module.billing.package.features.free.preview',
      ],
      starts_on_first_grant: true,
      granted_at: grantedAt,
      expires_at: '2026-04-30T00:00:00Z',
      welcome_dialog_acknowledged_at: acknowledgedAt,
    },
  };
}

describe('WelcomeTrialDialog', () => {
  beforeEach(() => {
    mockAcknowledgeBillingTrialWelcome.mockReset();
  });

  test('opens only for granted trial without persisted acknowledgement', () => {
    const mutateBillingOverview =
      jest.fn() as KeyedMutator<CreatorBillingOverview>;

    render(
      <WelcomeTrialDialog
        billingOverview={buildOverview({ creatorBid: 'creator-open' })}
        menuReady
        mutateBillingOverview={mutateBillingOverview}
      />,
    );

    expect(screen.getByTestId('welcome-trial-dialog')).toBeInTheDocument();
    expect(
      screen.getByText('module.billing.welcomeTrial.confirm'),
    ).toBeInTheDocument();
  });

  test('does not open for eligible or already acknowledged trials', () => {
    const mutateBillingOverview =
      jest.fn() as KeyedMutator<CreatorBillingOverview>;
    const { rerender } = render(
      <WelcomeTrialDialog
        billingOverview={buildOverview({
          creatorBid: 'creator-eligible',
          status: 'eligible',
          grantedAt: null,
        })}
        menuReady
        mutateBillingOverview={mutateBillingOverview}
      />,
    );

    expect(
      screen.queryByTestId('welcome-trial-dialog'),
    ).not.toBeInTheDocument();

    rerender(
      <WelcomeTrialDialog
        billingOverview={buildOverview({
          creatorBid: 'creator-acked',
          acknowledgedAt: '2026-04-16T00:00:00Z',
        })}
        menuReady
        mutateBillingOverview={mutateBillingOverview}
      />,
    );

    expect(
      screen.queryByTestId('welcome-trial-dialog'),
    ).not.toBeInTheDocument();
  });

  test('dismiss acknowledges the trial welcome and updates overview state', async () => {
    const overview = buildOverview({ creatorBid: 'creator-dismiss' });
    const mutateBillingOverview = jest.fn(async updater => {
      if (typeof updater === 'function') {
        return updater(overview);
      }
      return overview;
    }) as KeyedMutator<CreatorBillingOverview>;
    mockAcknowledgeBillingTrialWelcome.mockResolvedValue({
      acknowledged: true,
      acknowledged_at: '2026-04-16T00:00:00Z',
    });

    render(
      <WelcomeTrialDialog
        billingOverview={overview}
        menuReady
        mutateBillingOverview={mutateBillingOverview}
      />,
    );

    fireEvent.click(screen.getByText('module.billing.welcomeTrial.confirm'));

    await waitFor(() => {
      expect(mockAcknowledgeBillingTrialWelcome).toHaveBeenCalledWith({});
    });
    expect(
      screen.queryByTestId('welcome-trial-dialog'),
    ).not.toBeInTheDocument();
    await waitFor(() => {
      expect(mutateBillingOverview).toHaveBeenCalled();
    });
  });

  test('dismiss stays silent when acknowledgement fails', async () => {
    const mutateBillingOverview =
      jest.fn() as KeyedMutator<CreatorBillingOverview>;
    mockAcknowledgeBillingTrialWelcome.mockRejectedValue(new Error('network'));

    render(
      <WelcomeTrialDialog
        billingOverview={buildOverview({ creatorBid: 'creator-failure' })}
        menuReady
        mutateBillingOverview={mutateBillingOverview}
      />,
    );

    fireEvent.click(screen.getByText('module.billing.welcomeTrial.confirm'));

    await waitFor(() => {
      expect(mockAcknowledgeBillingTrialWelcome).toHaveBeenCalledTimes(1);
    });
    expect(
      screen.queryByTestId('welcome-trial-dialog'),
    ).not.toBeInTheDocument();
    expect(mutateBillingOverview).not.toHaveBeenCalled();
  });

  test('does not reopen for the same trial grant within the current app session', () => {
    const mutateBillingOverview =
      jest.fn() as KeyedMutator<CreatorBillingOverview>;
    const overview = buildOverview({ creatorBid: 'creator-session' });
    const firstRender = render(
      <WelcomeTrialDialog
        billingOverview={overview}
        menuReady
        mutateBillingOverview={mutateBillingOverview}
      />,
    );

    expect(screen.getByTestId('welcome-trial-dialog')).toBeInTheDocument();

    firstRender.unmount();

    render(
      <WelcomeTrialDialog
        billingOverview={overview}
        menuReady
        mutateBillingOverview={mutateBillingOverview}
      />,
    );

    expect(
      screen.queryByTestId('welcome-trial-dialog'),
    ).not.toBeInTheDocument();
  });
});
