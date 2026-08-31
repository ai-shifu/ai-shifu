import { toast, toastOnce } from '@/hooks/useToast';
import { showAiServiceErrorToast } from './aiServiceToast';

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
  toastOnce: jest.fn(),
}));

jest.mock('i18next', () => ({
  t: (key: string) => key,
}));

describe('aiServiceToast', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('dedupes AI service unavailable toasts with the friendly copy', () => {
    expect(
      showAiServiceErrorToast({
        message: '模型 deepseek 调用失败：provider unavailable',
        fallbackMessage: 'fallback',
      }),
    ).toEqual({
      message: 'module.chat.contentGenerationUnavailable',
      isAiServiceUnavailable: true,
    });

    expect(toastOnce).toHaveBeenCalledWith(
      expect.objectContaining({
        dedupeKey: 'ai-service-unavailable',
        title: 'module.chat.contentGenerationUnavailable',
        variant: 'destructive',
        duration: 8000,
      }),
    );
    expect(toast).not.toHaveBeenCalled();
  });

  it('keeps non-AI business errors on the regular toast path', () => {
    expect(
      showAiServiceErrorToast({
        message: '积分不足，请先购买积分',
        fallbackMessage: 'fallback',
        includeUnknown: true,
      }),
    ).toEqual({
      message: '积分不足，请先购买积分',
      isAiServiceUnavailable: false,
    });

    expect(toast).toHaveBeenCalledWith({
      title: '积分不足，请先购买积分',
      variant: 'destructive',
    });
    expect(toastOnce).not.toHaveBeenCalled();
  });
});
