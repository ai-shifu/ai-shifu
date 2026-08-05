import {
  isAiServiceUnavailableMessage,
  resolveAiServiceErrorToast,
} from './aiServiceError';

jest.mock('i18next', () => ({
  t: (key: string) => `i18n:${key}`,
}));

describe('aiServiceError', () => {
  it('maps technical LLM failures to learner-friendly copy', () => {
    expect(
      resolveAiServiceErrorToast({
        message: '模型 deepseek 调用失败：provider returned 500',
        fallbackMessage: 'fallback',
      }),
    ).toEqual({
      message: 'i18n:module.chat.contentGenerationUnavailable',
      isAiServiceUnavailable: true,
    });
  });

  it('can treat unknown run-stream failures as AI service unavailable', () => {
    expect(
      resolveAiServiceErrorToast({
        message: '未知错误',
        fallbackMessage: 'fallback',
        includeUnknown: true,
      }),
    ).toEqual({
      message: 'i18n:module.chat.contentGenerationUnavailable',
      isAiServiceUnavailable: true,
    });
  });

  it('does not hide unrelated learner-facing errors', () => {
    expect(
      resolveAiServiceErrorToast({
        message: '积分不足，请先购买积分',
        fallbackMessage: 'fallback',
        includeUnknown: true,
      }),
    ).toEqual({
      message: '积分不足，请先购买积分',
      isAiServiceUnavailable: false,
    });
  });

  it('detects common English LLM failure markers', () => {
    expect(isAiServiceUnavailableMessage('LiteLLM APIConnectionError')).toBe(
      true,
    );
    expect(isAiServiceUnavailableMessage('payment canceled')).toBe(false);
  });

  it('does not classify generic unsupported business errors', () => {
    expect(isAiServiceUnavailableMessage('This action is not supported')).toBe(
      false,
    );
    expect(
      resolveAiServiceErrorToast({
        message: 'This action is not supported',
        fallbackMessage: 'fallback',
      }),
    ).toEqual({
      message: 'This action is not supported',
      isAiServiceUnavailable: false,
    });
  });

  it('keeps model unsupported errors classified when AI evidence is present', () => {
    expect(
      isAiServiceUnavailableMessage('Model deepseek is not supported'),
    ).toBe(true);
  });
});
