import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StripeCardForm } from './StripeCardForm';

const mockConfirmPayment = jest.fn();
const mockGetStripeInstance = jest.fn();

jest.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: React.PropsWithChildren) => <>{children}</>,
  PaymentElement: () => <div data-testid='payment-element' />,
  useElements: () => ({ id: 'elements' }),
  useStripe: () => ({ confirmPayment: mockConfirmPayment }),
}));

jest.mock('@/lib/stripe', () => ({
  getStripeInstance: (...args: unknown[]) => mockGetStripeInstance(...args),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('StripeCardForm payment outcomes', () => {
  beforeEach(() => {
    mockConfirmPayment.mockReset();
    mockGetStripeInstance.mockReset().mockReturnValue(Promise.resolve({}));
  });

  const renderForm = (overrides: Record<string, unknown> = {}) => {
    const attempt = {
      orderId: 'order-1',
      lifecycle: 1,
      channel: 'stripe' as const,
      attemptId: 1,
    };
    const props = {
      clientSecret: 'client-secret-never-tracked',
      publishableKey: 'publishable-key',
      onAttempt: jest.fn(() => attempt),
      onConfirmSuccess: jest.fn(),
      onError: jest.fn(),
      ...overrides,
    };
    render(<StripeCardForm {...props} />);
    return { ...props, attempt };
  };

  it('records the accepted attempt before confirming a successful payment', async () => {
    mockConfirmPayment.mockResolvedValue({
      paymentIntent: { status: 'succeeded' },
    });
    const props = renderForm();

    fireEvent.click(await screen.findByRole('button'));

    await waitFor(() =>
      expect(props.onConfirmSuccess).toHaveBeenCalledTimes(1),
    );
    expect(props.onAttempt).toHaveBeenCalledTimes(1);
    expect(props.onAttempt.mock.invocationCallOrder[0]).toBeLessThan(
      mockConfirmPayment.mock.invocationCallOrder[0],
    );
    expect(props.onConfirmSuccess).toHaveBeenCalledWith(props.attempt);
    expect(props.onError).not.toHaveBeenCalled();
  });

  it('forwards known provider failures and pending statuses with attempt context', async () => {
    mockConfirmPayment.mockResolvedValueOnce({
      error: { message: 'private provider detail' },
    });
    const rejected = renderForm();
    fireEvent.click(await screen.findByRole('button'));
    await waitFor(() =>
      expect(rejected.onError).toHaveBeenCalledWith(
        'private provider detail',
        'failed',
        expect.objectContaining({ orderId: 'order-1', channel: 'stripe' }),
      ),
    );

    rejected.onError.mockReset();
    mockConfirmPayment.mockResolvedValueOnce({
      paymentIntent: { status: 'processing' },
    });
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() =>
      expect(rejected.onError).toHaveBeenCalledWith(
        'module.pay.stripeProcessing',
        'pending',
        expect.objectContaining({ orderId: 'order-1', channel: 'stripe' }),
      ),
    );
    await waitFor(() => expect(screen.getByRole('button')).toBeEnabled());

    rejected.onError.mockReset();
    mockConfirmPayment.mockResolvedValueOnce({
      paymentIntent: { status: 'requires_action' },
    });
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => expect(mockConfirmPayment).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.getByRole('button')).toBeEnabled());
    expect(rejected.onError).not.toHaveBeenCalled();
  });

  it('continues the payment when attempt tracking throws', async () => {
    mockConfirmPayment.mockResolvedValue({
      paymentIntent: { status: 'succeeded' },
    });
    const props = renderForm({
      onAttempt: jest.fn(() => {
        throw new Error('tracking unavailable');
      }),
    });

    fireEvent.click(await screen.findByRole('button'));

    await waitFor(() => expect(mockConfirmPayment).toHaveBeenCalledTimes(1));
    expect(props.onConfirmSuccess).toHaveBeenCalledWith(undefined);
    await waitFor(() => expect(screen.getByRole('button')).toBeEnabled());
  });
});
