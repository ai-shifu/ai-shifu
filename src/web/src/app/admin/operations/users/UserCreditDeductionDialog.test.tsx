import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import UserCreditDeductionDialog from './UserCreditDeductionDialog';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const mockDeduct = api.deductAdminOperationUserCredits as jest.Mock;

jest.mock('@/api', () => ({
  __esModule: true,
  default: { deductAdminOperationUserCredits: jest.fn() },
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('uuid', () => ({ v4: () => 'deduction-request-id' }));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en-US' },
  }),
}));

jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

jest.mock('@/components/ui/Select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  SelectValue: () => null,
}));

const user = {
  user_bid: 'user-sensitive-id',
  mobile: '13812345678',
  email: 'private@example.com',
  nickname: 'Private Name',
  user_status: 'paid',
  user_role: 'creator',
  user_roles: ['creator'],
  login_methods: ['email'],
  registration_source: 'email',
  language: 'zh-CN',
  learning_courses: [],
  learning_course_count: 0,
  created_courses: [],
  created_course_count: 0,
  total_paid_amount: '100',
  available_credits: '1000.75',
  subscription_credits: '600.25',
  topup_credits: '0',
  credits_expire_at: '2027-01-01T00:00:00Z',
  has_active_subscription: true,
  last_login_at: '',
  last_learning_at: '',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('UserCreditDeductionDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('requires two confirmations and submits a decimal deduction once', async () => {
    const onOpenChange = jest.fn();
    const onDeducted = jest.fn();
    const result = {
      status: 'deducted',
      user_bid: user.user_bid,
      amount: '800.40',
      reason: 'account_correction',
      note: 'verified correction',
      wallet_bucket_bids: ['paid', 'manual'],
      ledger_bids: ['ledger-1', 'ledger-2'],
      summary: {
        available_credits: '200.35',
        subscription_credits: '0',
        topup_credits: '0',
        credits_expire_at: '',
        has_active_subscription: true,
      },
    };
    mockDeduct.mockResolvedValue(result);

    render(
      <UserCreditDeductionDialog
        open
        user={user}
        onOpenChange={onOpenChange}
        onDeducted={onDeducted}
      />,
    );

    fireEvent.change(screen.getByLabelText('deductionDialog.amount'), {
      target: { value: '800.40' },
    });
    fireEvent.change(screen.getByLabelText('deductionDialog.note'), {
      target: { value: 'verified correction' },
    });
    fireEvent.click(screen.getByText('deductionDialog.continueButton'));

    expect(mockDeduct).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('deductionDialog.confirmButton'));

    await waitFor(() =>
      expect(mockDeduct).toHaveBeenCalledWith({
        user_bid: user.user_bid,
        request_id: 'deduction-request-id',
        amount: '800.40',
        reason: 'account_correction',
        note: 'verified correction',
      }),
    );
    expect(onDeducted).toHaveBeenCalledWith(result);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mockTrackEvent).toHaveBeenNthCalledWith(
      1,
      'operator_credit_deduction_attempt',
      { surface: 'operator_user_management' },
    );
    expect(mockTrackEvent).toHaveBeenNthCalledWith(
      2,
      'operator_credit_deduction_result',
      { surface: 'operator_user_management', outcome: 'success' },
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
      user.user_bid,
    );
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain('800.40');
  });

  it('rejects amounts with more than two decimal places without tracking', () => {
    render(
      <UserCreditDeductionDialog
        open
        user={user}
        onOpenChange={jest.fn()}
        onDeducted={jest.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText('deductionDialog.amount'), {
      target: { value: '1.001' },
    });
    fireEvent.click(screen.getByText('deductionDialog.continueButton'));

    expect(screen.getByRole('alert')).toHaveTextContent(
      'deductionDialog.errors.amount',
    );
    expect(mockDeduct).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  it.each(['throw', 'reject'])(
    'keeps a successful deduction working when analytics %s',
    async failure => {
      mockTrackEvent.mockImplementation(() => {
        if (failure === 'throw') throw new Error('analytics unavailable');
        return Promise.reject(new Error('analytics unavailable'));
      });
      mockDeduct.mockResolvedValue({ status: 'deducted' });
      const onDeducted = jest.fn();
      render(
        <UserCreditDeductionDialog
          open
          user={user}
          onOpenChange={jest.fn()}
          onDeducted={onDeducted}
        />,
      );
      fireEvent.change(screen.getByLabelText('deductionDialog.amount'), {
        target: { value: '1.25' },
      });
      fireEvent.click(screen.getByText('deductionDialog.continueButton'));
      fireEvent.click(screen.getByText('deductionDialog.confirmButton'));

      await waitFor(() => expect(onDeducted).toHaveBeenCalled());
    },
  );
});
