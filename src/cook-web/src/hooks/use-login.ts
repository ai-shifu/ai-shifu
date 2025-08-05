import { useToast } from '@/hooks/use-toast';
import { useUserStore } from '@/c-store/useUserStore';
import apiService from '@/api';
import { useTranslation } from 'react-i18next';
import type { UserInfo } from '@/c-types';

interface LoginResponse {
  code: number;
  data?: {
    userInfo: UserInfo;
    token: string;
  };
  message?: string;
  msg?: string;
}

interface UseLoginOptions {
  onSuccess?: (userInfo: UserInfo) => void;
  onError?: (error: any) => void;
}

export function useLogin(options: UseLoginOptions = {}) {
  const { toast } = useToast();
  const { login, logout } = useUserStore();
  const { t } = useTranslation();

  // Handle token expiration by refreshing token and retrying
  const handleTokenExpiration = async (
    loginMethod: () => Promise<LoginResponse>,
  ): Promise<LoginResponse> => {
    // Logout to get new guest token (without page reload)
    await logout(false);

    // Retry the login with new token
    return await loginMethod();
  };

  // Handle common login errors
  const handleLoginError = (code: number, message?: string) => {
    switch (code) {
      case 1001:
      case 1003:
        toast({
          title: t('login.login-failed'),
          description: t('login.username-or-password-error'),
          variant: 'destructive',
        });
        break;
      case 1005:
        // Token expiration is handled by retry logic
        break;
      default:
        toast({
          title: t('login.login-failed'),
          description: message || t('login.network-error'),
          variant: 'destructive',
        });
    }
  };

  // Process login response
  const processLoginResponse = async (response: LoginResponse) => {
    if (response.code === 0 && response.data) {
      toast({
        title: t('login.login-success'),
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
      const loginMethod = () => apiService.login({ username, password });

      let response = await loginMethod();

      // Handle token expiration on login page
      if (response.code === 1005) {
        response = await handleTokenExpiration(loginMethod);
      }

      const success = await processLoginResponse(response);
      if (!success) {
        handleLoginError(response.code, response.message || response.msg);
      }

      return response;
    } catch (error: any) {
      toast({
        title: t('login.login-failed'),
        description: error.message || t('login.network-error'),
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
      const loginMethod = () =>
        apiService.verifySmsCode({ mobile, sms_code, language });

      let response = await loginMethod();

      // Handle token expiration on login page
      if (response.code === 1005) {
        response = await handleTokenExpiration(loginMethod);
      }

      const success = await processLoginResponse(response);
      if (!success) {
        if (response.code === 1003) {
          toast({
            title: t('login.verification-failed'),
            description: t('login.otp-expired'),
            variant: 'destructive',
          });
        } else {
          toast({
            title: t('login.verification-failed'),
            description: t('login.otp-error'),
            variant: 'destructive',
          });
        }
      }

      return response;
    } catch (error: any) {
      toast({
        title: t('login.verification-failed'),
        description: error.message || t('login.network-error'),
        variant: 'destructive',
      });
      options.onError?.(error);
      throw error;
    }
  };

  return {
    loginWithEmailPassword,
    loginWithSmsCode,
  };
}
