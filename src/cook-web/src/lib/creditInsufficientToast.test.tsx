import { toastOnce } from '@/hooks/useToast';
import {
  CREDIT_INSUFFICIENT_BUSINESS_CODE,
  DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE,
  getCreditInsufficientMessage,
  showCreditInsufficientToast,
} from './creditInsufficientToast';

jest.mock('i18next', () => ({
  __esModule: true,
  default: {
    t: (key: string) =>
      ({
        'module.billing.alerts.actions.checkoutTopup': '购买积分',
        'module.billing.creditInsufficient.learner':
          '当前课程的积分不足，暂时无法继续生成内容，请联系课程老师。',
        'module.billing.creditInsufficient.purchaseActionAltText':
          '前往积分购买页',
        'module.billing.creditInsufficient.teacher':
          '积分余额不足，暂时无法继续使用。',
        'module.billing.creditInsufficient.teacherSoftlimit':
          '积分余额已低于提醒阈值，暂时不能继续调试。',
      })[key] || key,
  },
}));

jest.mock('@/hooks/useToast', () => ({
  toastOnce: jest.fn(),
}));

const mockToastOnce = toastOnce as jest.Mock;

describe('credit insufficient toast', () => {
  beforeEach(() => {
    mockToastOnce.mockReset();
  });

  test('shows the learner-specific permanent notice without a purchase action', () => {
    expect(
      showCreditInsufficientToast({
        audience: 'learner',
        code: CREDIT_INSUFFICIENT_BUSINESS_CODE,
      }),
    ).toBe(true);

    expect(mockToastOnce).toHaveBeenCalledWith(
      expect.objectContaining({
        dedupeKey: 'credit-insufficient:learner:7101',
        dedupeWindowMs: Number.POSITIVE_INFINITY,
        title: '当前课程的积分不足，暂时无法继续生成内容，请联系课程老师。',
        duration: 0,
        dismissOnNavigation: true,
        action: undefined,
      }),
    );
  });

  test.each<[number, string]>([
    [CREDIT_INSUFFICIENT_BUSINESS_CODE, '积分余额不足，暂时无法继续使用。'],
    [
      DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE,
      '积分余额已低于提醒阈值，暂时不能继续调试。',
    ],
  ])('shows teacher code %s with the shared purchase link', (code, title) => {
    showCreditInsufficientToast({ audience: 'teacher', code });

    const options = mockToastOnce.mock.calls[0][0];
    expect(options).toEqual(
      expect.objectContaining({
        title,
        duration: 0,
        dismissOnNavigation: true,
        dedupeWindowMs: Number.POSITIVE_INFINITY,
      }),
    );
    expect(options.action.props.altText).toBe('前往积分购买页');
    expect(options.action.props.children.props).toEqual(
      expect.objectContaining({
        href: '/admin/billing?tab=packages',
        children: '购买积分',
      }),
    );
  });

  test('uses the learner wording for both credit error codes', () => {
    expect(
      getCreditInsufficientMessage(
        'learner',
        DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE,
      ),
    ).toBe('当前课程的积分不足，暂时无法继续生成内容，请联系课程老师。');
  });
});
