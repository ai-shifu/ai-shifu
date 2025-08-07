import { useToast } from '@/hooks/useToast';
import { useUserStore } from '@/store/useUserStore';
import apiService from '@/api';
import { useTranslation } from 'react-i18next';
import type { UserInfo } from '@/c-types';

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

interface UseAuthOptions {
  onSuccess?: (userInfo: UserInfo) => void;
  onError?: (error: any) => void;
}

export function useAuth(options: UseAuthOptions = {}) {
  const { toast } = useToast();
  const { login, logout } = useUserStore();
  const { t } = useTranslation();

  // Generic wrapper for API calls with automatic token refresh on expiration
  const callWithTokenRefresh = async <T extends ApiResponse>(
    apiCall: () => Promise<T>,
  ): Promise<T> => {
    const response = await apiCall();

    // Handle token expiration
    if (response.code === 1005) {
      // Refresh token
      await logout(false);
      // Retry the API call
      return await apiCall();
    }

    return response;
  };

  // Handle common login errors
  const handleLoginError = (
    code: number,
    message?: string,
    context?: 'email' | 'sms',
  ) => {
    // Skip token expiration as it's handled by retry logic
    if (code === 1005) return;

    const title = t('auth.failed');
    let description: string;

    switch (code) {
      case 1001:
        description = t('auth.credentialError');
        break;
      case 1003:
        // For SMS context, 1003 means OTP expired; for email context, it means wrong credentials
        description =
          context === 'sms' ? t('auth.otpExpired') : t('auth.credentialError');
        break;
      default:
        description = message || t('common.networkError');
    }

    toast({
      title,
      description,
      variant: 'destructive',
    });
  };

  // Process login response
  const processLoginResponse = async (response: LoginResponse) => {
    if (response.code === 0 && response.data) {
      toast({
        title: t('auth.success'),
      });
      await login(response.data.userInfo, response.data.token);
      options.onSuccess?.(response.data.userInfo);
      return true;
    }
    return false;
  };

  // Email/Password login with automatic retry on token expiration
  const loginWithEmailPassword = async (username: string, password: string) => {
    try {
      const response = await callWithTokenRefresh(() =>
        apiService.login({ username, password }),
      );

      const success = await processLoginResponse(response);
      if (!success) {
        handleLoginError(
          response.code,
          response.message || response.msg,
          'email',
        );
      }

      return response;
    } catch (error: any) {
      toast({
        title: t('auth.failed'),
        description: error.message || t('common.networkError'),
        variant: 'destructive',
      });
      options.onError?.(error);
      throw error;
    }
  };

  // SMS verification login with automatic retry on token expiration
  const loginWithSmsCode = async (
    mobile: string,
    sms_code: string,
    language: string,
  ) => {
    try {
      const response = await callWithTokenRefresh(() =>
        apiService.verifySmsCode({ mobile, sms_code, language }),
      );

      const success = await processLoginResponse(response);
      if (!success) {
        handleLoginError(
          response.code,
          response.message || response.msg,
          'sms',
        );
      }

      return response;
    } catch (error: any) {
      toast({
        title: t('auth.failed'),
        description: error.message || t('common.networkError'),
        variant: 'destructive',
      });
      options.onError?.(error);
      throw error;
    }
  };

  // Send SMS verification code with automatic token refresh
  const sendSmsCode = async (mobile: string, language: string) => {
    try {
      const response = await callWithTokenRefresh(() =>
        apiService.sendSmsCode({ mobile, language }),
      );

      if (response.code !== 0) {
        throw new Error(
          response.message || response.msg || t('common.networkError'),
        );
      }

      return response;
    } catch (error: any) {
      toast({
        title: t('auth.sendFailed'),
        description: error.message || t('common.networkError'),
        variant: 'destructive',
      });
      throw error;
    }
  };

  return {
    loginWithEmailPassword,
    loginWithSmsCode,
    sendSmsCode,
    callWithTokenRefresh,
  };
}
