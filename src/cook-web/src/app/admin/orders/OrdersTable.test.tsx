import { render, screen } from '@testing-library/react';
import OrdersTable from './OrdersTable';
import type { OrderSummary } from '@/components/order/order-types';

const mockBrowserTimeZone = jest.fn(() => 'America/Los_Angeles');

jest.mock('@/lib/browser-timezone', () => ({
  getBrowserTimeZone: () => mockBrowserTimeZone(),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/app/admin/components/AdminTooltipText', () => ({
  __esModule: true,
  default: ({ text, emptyValue }: { text?: string; emptyValue?: string }) => (
    <span>{text || emptyValue || ''}</span>
  ),
}));

const getColumnStyle = () => ({ width: 120 });
const getResizeHandleProps = () => ({
  onMouseDown: jest.fn(),
  'aria-hidden': true as const,
});

const order: OrderSummary = {
  order_bid: 'order-1',
  shifu_bid: 'course-1',
  shifu_name: 'Course One',
  user_bid: 'user-1',
  user_mobile: '',
  user_email: 'learner@example.com',
  user_nickname: 'Learner One',
  payable_price: '99.00',
  paid_price: '89.00',
  discount_amount: '10.00',
  status: 502,
  status_key: 'server.order.orderStatusPaid',
  payment_channel: 'stripe',
  payment_channel_key: 'module.order.paymentChannel.stripe',
  coupon_codes: [],
  created_at: '2026-05-01T12:00:00Z',
  updated_at: '2026-05-01T12:00:00Z',
};

describe('OrdersTable', () => {
  beforeEach(() => {
    mockBrowserTimeZone.mockReturnValue('America/Los_Angeles');
  });

  test('formats order created_at with the admin browser-timezone rule', () => {
    render(
      <OrdersTable
        orders={[order]}
        loading={false}
        total={1}
        pageIndex={1}
        pageCount={1}
        isEmailMode
        defaultUserName='-'
        getColumnStyle={getColumnStyle}
        getResizeHandleProps={getResizeHandleProps}
        formatMoney={value => `¥${value || '0'}`}
        resolveStatusLabel={item => item.status_key}
        onPageChange={jest.fn()}
        onViewDetail={jest.fn()}
      />,
    );

    expect(screen.getByText('2026-05-01 05:00:00')).toBeInTheDocument();
    expect(screen.queryByText('2026-05-01T12:00:00Z')).not.toBeInTheDocument();
  });
});
