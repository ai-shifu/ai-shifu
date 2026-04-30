import { useCallback, useEffect, useState } from 'react';

import apiService from '@/api';

type ApiEnvelope<T> = {
  code?: number;
  data?: T;
  message?: string;
  msg?: string;
};

type CaptchaChallenge = {
  captcha_id: string;
  image: string;
  expires_in: number;
};

type CaptchaTicket = {
  captcha_ticket: string;
  expires_in: number;
};

type ApiError = Error & {
  code?: number;
};

const unwrapApiPayload = <T>(response: ApiEnvelope<T> | T): T => {
  const maybeEnvelope = response as ApiEnvelope<T>;
  if (typeof maybeEnvelope?.code === 'number') {
    if (maybeEnvelope.code !== 0) {
      const error = new Error(
        maybeEnvelope.message || maybeEnvelope.msg || 'Captcha request failed',
      ) as ApiError;
      error.code = maybeEnvelope.code;
      throw error;
    }
    return maybeEnvelope.data as T;
  }
  return response as T;
};

export function useCaptchaTicket(enabled = true) {
  const [captchaId, setCaptchaId] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [captchaCode, setCaptchaCode] = useState('');
  const [isCaptchaLoading, setIsCaptchaLoading] = useState(false);

  const refreshCaptcha = useCallback(async () => {
    setIsCaptchaLoading(true);
    try {
      const response = await apiService.getCaptcha({});
      const captcha = unwrapApiPayload<CaptchaChallenge>(response);
      setCaptchaId(captcha.captcha_id);
      setCaptchaImage(captcha.image);
      setCaptchaCode('');
      return captcha;
    } finally {
      setIsCaptchaLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    void refreshCaptcha().catch(() => {
      setCaptchaId('');
      setCaptchaImage('');
      setCaptchaCode('');
    });
  }, [enabled, refreshCaptcha]);

  const verifyCaptcha = useCallback(async () => {
    if (!captchaId || !captchaCode.trim()) {
      const error = new Error('Captcha is required') as ApiError;
      error.code = 1009;
      throw error;
    }
    const response = await apiService.verifyCaptcha({
      captcha_id: captchaId,
      captcha_code: captchaCode.trim(),
    });
    const ticket = unwrapApiPayload<CaptchaTicket>(response);
    return ticket.captcha_ticket;
  }, [captchaCode, captchaId]);

  return {
    captchaId,
    captchaImage,
    captchaCode,
    setCaptchaCode,
    isCaptchaLoading,
    refreshCaptcha,
    verifyCaptcha,
  };
}
