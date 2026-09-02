import { useToast } from '@/hooks/useToast';
import { useUserStore } from '@/store';
import apiService from '@/api';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import type { UserInfo } from '@/c-types';
import { useTracking } from '@/c-common/hooks/useTracking';
import {
  buildReferralLoginPayload,
  clearReferralContext,
} from '@/lib/referral-context';
import type { ReferralLoginMetadata } from '@/types/referral';
import {
  buildLoginAttemptAnalytics,
  buildLoginResultAnalytics,
} from '@/lib/loginAnalytics';

interface ApiResponse {
  code: number;
  data?: any;
  message?: string;
  msg?: string;
}

interface LoginResponse extends ApiResponse {
  data?: {
    userInfo: UserInfo;
    token: string;
  };
}

type ApiError = Error & {
  code?: number;
};

type VerificationLoginMethod = 'email' | 'sms';

type SendVerificationCodeResult = {
  rateLimited: boolean;
};

const SMS_SEND_TOO_FREQUENT_CODE = 1012;
const EMAIL_SEND_TOO_FREQUENT_CODE = 1033;
const VERIFICATION_CREDENTIAL_ERROR_CODES = new Set([1013, 1014]);

interface UseAuthOptions {
  onSuccess?: (userInfo: UserInfo) => void;
  onError?: (error: any) => void;
  loginContext?: string;
  courseId?: string;
}

export function useAuth(options: UseAuthOptions = {}) {
  const { toast } = useToast();
  const { login, logout } = useUserStore();
  const { t } = useTranslation();
  const { trackEvent } = useTracking();

  const buildApiError = (response: ApiResponse): ApiError => {
    const error = new Error(
      response.message || response.msg || t('common.core.networkError'),
    ) as ApiError;
    error.code = response.code;
    return error;
  };

  // Generic wrapper for API calls with automatic token refresh on expiration
  const callWithTokenRefresh = async <T extends ApiResponse>(
    apiCall: () => Promise<T>,
    hasRetried = false,
  ): Promise<T> => {
    const buildTokenRetryError = (message?: string) => {
      const error = new Error(
        message || t('module.auth.failed') || t('common.core.networkError'),
      ) as Error & { code?: number };
      error.code = 1005;
      return error;
    };

    const tokenBefore = useUserStore.getState().getToken?.() || '';
    try {
      const response = await apiCall();

      // Handle token expiration
      if (response.code === 1005) {
        if (!hasRetried) {
          const tokenAfter = useUserStore.getState().getToken?.() || '';
          // Request layer usually handles auth recovery. Only run local recovery
          // if token did not change (recovery likely did not happen yet).
          if (tokenAfter === tokenBefore) {
            await logout(false);
          }
          // Retry the API call once with the new guest token
          return await callWithTokenRefresh(apiCall, true);
        }
        throw buildTokenRetryError(response.message || response.msg);
      }

      return response;
    } catch (error: any) {
      if (error?.code === 1005 && !hasRetried) {
        const tokenAfter = useUserStore.getState().getToken?.() || '';
        if (tokenAfter === tokenBefore) {
          await logout(false);
        }
        return await callWithTokenRefresh(apiCall, true);
      }
      if (error?.code === 1005 && hasRetried) {
        throw buildTokenRetryError(error?.message);
      }
      throw error;
    }
  };

  // Handle common login errors
  const handleLoginError = (
    code: number,
    message?: string,
    context?: 'email' | 'sms',
  ) => {
    // Skip token expiration as it's handled by retry logic
    if (code === 1005) return;

    const title = t('module.auth.failed');
    let description: string;

    switch (code) {
      case 1001:
        description = t('module.auth.credentialError');
        break;
      case 1003:
        description =
          context === 'sms'
            ? t('module.auth.otpExpired')
            : t('module.auth.credentialError');
        break;
      case 1013:
        description = t('module.auth.otpExpired');
        break;
      case 1014:
        description = t('module.auth.otpInvalid');
        break;
      default:
        description = message || t('common.core.networkError');
    }

    toast({
      title,
      description,
      variant: 'destructive',
    });
  };

  // Process login response
  const processLoginResponse = async (
    response: LoginResponse,
    onLoginCommitted?: () => void,
  ) => {
    if (response.code === 0 && response.data) {
      toast({
        title: t('module.auth.success'),
      });
      await login(response.data.userInfo, response.data.token);
      onLoginCommitted?.();
      options.onSuccess?.(response.data.userInfo);
      return true;
    }
    return false;
  };

  const loginWithVerificationCode = async (
    method: VerificationLoginMethod,
    identifier: string,
    code: string,
    language: string,
    referralMetadata?: ReferralLoginMetadata,
  ) => {
    trackEvent('learner_login_attempt', buildLoginAttemptAnalytics(method));
    let loginCommitted = false;
    try {
      const referralPayload = buildReferralLoginPayload(referralMetadata);
      const response = await callWithTokenRefresh(() =>
        method === 'sms'
          ? apiService.smsLogin(
              {
                mobile: identifier,
                sms_code: code,
                language,
                login_context: options.loginContext,
                course_id: options.courseId,
                ...referralPayload,
              },
              { skipErrorToast: true },
            )
          : apiService.emailLogin(
              {
                email: identifier,
                code,
                language,
                login_context: options.loginContext,
                course_id: options.courseId,
                ...referralPayload,
              },
              { skipErrorToast: true },
            ),
      );

      const success = await processLoginResponse(response, () => {
        loginCommitted = true;
        trackEvent(
          'learner_login_result',
          buildLoginResultAnalytics(method, 'success'),
        );
      });
      if (success && referralPayload.invite_code) {
        clearReferralContext();
      }
      if (!success) {
        trackEvent(
          'learner_login_result',
          buildLoginResultAnalytics(method, 'failed', 'credentials_rejected'),
        );
        handleLoginError(
          response.code,
          response.message || response.msg,
          method,
        );
      }

      return response;
    } catch (error: any) {
      if (!loginCommitted) {
        const failureCategory = VERIFICATION_CREDENTIAL_ERROR_CODES.has(
          error?.code,
        )
          ? 'credentials_rejected'
          : 'request_failed';
        trackEvent(
          'learner_login_result',
          buildLoginResultAnalytics(method, 'failed', failureCategory),
        );
      }
      toast({
        title: t('module.auth.failed'),
        description: error.message || t('common.core.networkError'),
        variant: 'destructive',
      });
      options.onError?.(error);
      throw error;
    }
  };

  const sendVerificationCode = async (
    apiCall: () => Promise<ApiResponse>,
    rateLimitCode: number,
  ): Promise<SendVerificationCodeResult> => {
    try {
      const response = await callWithTokenRefresh(apiCall);

      if (response.code === rateLimitCode) {
        return { rateLimited: true };
      }
      if (response.code !== 0) {
        throw buildApiError(response);
      }

      return { rateLimited: false };
    } catch (error: any) {
      if (error?.code === rateLimitCode) {
        return { rateLimited: true };
      }
      toast({
        title: t('module.auth.sendFailed'),
        description: error.message || t('common.core.networkError'),
        variant: 'destructive',
      });
      throw error;
    }
  };

  // Keep the public channel methods stable while sharing orchestration.
  const loginWithSmsCode = async (
    mobile: string,
    smsCode: string,
    language: string,
    referralMetadata?: ReferralLoginMetadata,
  ) =>
    loginWithVerificationCode(
      'sms',
      mobile,
      smsCode,
      language,
      referralMetadata,
    );

  const loginWithEmailCode = async (
    email: string,
    code: string,
    language: string,
    referralMetadata?: ReferralLoginMetadata,
  ) =>
    loginWithVerificationCode('email', email, code, language, referralMetadata);

  const sendSmsCode = async (mobile: string, captchaTicket: string) =>
    sendVerificationCode(
      () =>
        apiService.sendSmsCode(
          {
            mobile,
            captcha_ticket: captchaTicket,
            language: i18n.language,
          },
          { skipErrorToast: true },
        ),
      SMS_SEND_TOO_FREQUENT_CODE,
    );

  const sendEmailCode = async (email: string) =>
    sendVerificationCode(
      () =>
        apiService.sendEmailCode(
          {
            email,
            language: i18n.language,
          },
          { skipErrorToast: true },
        ),
      EMAIL_SEND_TOO_FREQUENT_CODE,
    );

  return {
    loginWithSmsCode,
    sendSmsCode,
    loginWithEmailCode,
    sendEmailCode,
    callWithTokenRefresh,
  };
}
