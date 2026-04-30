import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import OperatorOrderDetailSheet from './OperatorOrderDetailSheet';

const translationCache = new Map<string, { t: (key: string) => string }>();
const baseTranslation = (namespace?: string | string[]) => {
  const ns = Array.isArray(namespace) ? namespace[0] : namespace;
  const cacheKey = ns || 'translation';
  if (!translationCache.has(cacheKey)) {
    translationCache.set(cacheKey, {
      t: (key: string) => (ns && ns !== 'translation' ? `${ns}.${key}` : key),
    });
  }
  return translationCache.get(cacheKey)!;
};

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOperationOrderDetail: jest.fn(),
  },
}));

jest.mock('@/lib/request', () => ({
  __esModule: true,
  ErrorWithCode: class MockErrorWithCode extends Error {
    code: number;

    constructor(message: string, code: number) {
      super(message);
      this.code = code;
    }
  },
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: (state: {
      loginMethodsEnabled: string[];
      defaultLoginMethod: string;
    }) => unknown,
  ) =>
    selector({
      loginMethodsEnabled: ['phone'],
      defaultLoginMethod: 'phone',
    }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: (namespace?: string | string[]) => baseTranslation(namespace),
}));

jest.mock('@/components/loading', () => ({
  __esModule: true,
  default: () => <div data-testid='loading-indicator' />,
}));

jest.mock('@/components/ErrorDisplay', () => ({
  __esModule: true,
  default: ({ errorMessage }: { errorMessage: string }) => (
    <div>{errorMessage}</div>
  ),
}));

jest.mock('@/components/ui/Sheet', () => ({
  __esModule: true,
  Sheet: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) =>
    open ? <div>{children}</div> : null,
  SheetContent: ({ children }: React.PropsWithChildren) => (
    <div role='dialog'>{children}</div>
  ),
  SheetHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SheetTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

const mockGetAdminOperationOrderDetail =
  api.getAdminOperationOrderDetail as jest.Mock;

describe('OperatorOrderDetailSheet', () => {
  beforeEach(() => {
    mockGetAdminOperationOrderDetail.mockReset();
  });

  test('renders translated source label and hides activities section when empty', async () => {
    mockGetAdminOperationOrderDetail.mockResolvedValue({
      order: {
        order_bid: 'order-1',
        shifu_bid: 'd5b52a3538484cb29274b10cfe349fab',
        shifu_name: 'Course 1',
        user_bid: 'user-1',
        user_mobile: '13800138000',
        user_email: '',
        user_nickname: 'Tester',
        payable_price: '99',
        paid_price: '0',
        discount_amount: '99',
        status: 502,
        status_key: 'server.order.orderStatusSuccess',
        payment_channel: 'manual',
        payment_channel_key: 'module.order.paymentChannel.manual',
        order_source: '',
        order_source_key: '',
        coupon_codes: ['FREE100'],
        created_at: '2026-04-23T10:00:00Z',
        updated_at: '2026-04-23T11:00:00Z',
      },
      payment: {
        payment_channel: 'manual',
        payment_channel_key: 'module.order.paymentChannel.manual',
        status: 0,
        status_key: 'module.order.paymentStatus.unknown',
        amount: '0',
        currency: '',
        payment_intent_id: '',
        checkout_session_id: '',
        latest_charge_id: '',
        receipt_url: '',
        payment_method: '',
        transaction_no: '',
        charge_id: '',
        channel: '',
        created_at: '',
        updated_at: '',
      },
      coupons: [],
      activities: [],
    });

    render(
      <OperatorOrderDetailSheet
        open
        orderBid='order-1'
      />,
    );

    await waitFor(() => {
      expect(mockGetAdminOperationOrderDetail).toHaveBeenCalledWith({
        order_bid: 'order-1',
      });
    });

    expect(
      await screen.findByText('module.operationsOrder.detail.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('order-1')).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsOrder.source.importActivation'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.operationsOrder.detail.sections.activities'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('d5b52a3538484cb29274b10cfe349fab'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.operationsCourse.table.courseId'),
    ).toHaveClass('whitespace-nowrap');
  });

  test('shows error UI when detail request fails', async () => {
    mockGetAdminOperationOrderDetail.mockRejectedValueOnce(
      new Error('detail failed'),
    );

    render(
      <OperatorOrderDetailSheet
        open
        orderBid='order-1'
      />,
    );

    expect(await screen.findByText('detail failed')).toBeInTheDocument();
  });
});
