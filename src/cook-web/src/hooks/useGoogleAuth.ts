'use client';

import { useCallback } from 'react';
import apiService from '@/api';
import { environment } from '@/config/environment';
import { useAuth } from '@/hooks/useAuth';
import { useToast } from '@/hooks/useToast';
import { useUserStore } from '@/store';
import { useTranslation } from 'react-i18next';
import type { UserInfo } from '@/c-types';
import {
  clearGoogleOAuthSession,
  getGoogleOAuthRedirect,
  getGoogleOAuthState,
  setGoogleOAuthRedirect,
  setGoogleOAuthState,
} from '@/lib/google-oauth-session';

interface OAuthStartPayload {
  authorization_url: string;
  state: string;
}

interface UserTokenPayload {
  userInfo: UserInfo;
  token: string;
}

interface ApiEnvelope<T> {
  code: number;
  message?: string;
  msg?: string;
  data?: T;
}

interface UseGoogleAuthOptions {
  onSuccess?: (userInfo: UserInfo, redirectPath: string) => void;
  onError?: (error: unknown) => void;
}

interface StartGoogleLoginOptions {
  redirectPath?: string;
  redirectUriOverride?: string;
}

interface FinalizeGoogleLoginOptions {
  code: string | null;
  state: string | null;
  fallbackRedirect?: string;
}

function extractData<T>(response: T | ApiEnvelope<T>): T {
  if (response && typeof response === 'object' && 'code' in response) {
    const envelope = response as ApiEnvelope<T>;
    if (envelope.code !== 0) {
      const message =
        envelope.message || envelope.msg || 'OAuth request failed';
      throw Object.assign(new Error(message), { code: envelope.code });
    }
    return envelope.data as T;
  }
  return response as T;
}

function buildRedirectUri(override?: string): string {
  const origin =
    typeof window !== 'undefined' && window.location
      ? window.location.origin
      : 'http://localhost:3001';
  const target = override || `${origin}/login/google-callback`;

  try {
    const url = new URL(target, origin);
    return url.toString();
  } catch (error) {
    console.warn(
      'Invalid Google OAuth redirect URI, falling back to origin.',
      error,
    );
    return `${origin}/login/google-callback`;
  }
}

export function useGoogleAuth(options: UseGoogleAuthOptions = {}) {
  const { toast } = useToast();
  const { t } = useTranslation();
  const login = useUserStore(state => state.login);
  const ensureGuestToken = useUserStore(state => state.ensureGuestToken);
  const { callWithTokenRefresh } = useAuth();

  const clearGoogleSession = useCallback(() => {
    clearGoogleOAuthSession();
  }, []);

  const startGoogleLogin = useCallback(
    async ({
      redirectPath,
      redirectUriOverride,
    }: StartGoogleLoginOptions = {}) => {
      try {
        if (typeof window === 'undefined') {
          throw new Error('Google OAuth requires a browser environment.');
        }

        const redirectTarget = redirectPath || '/main';
        setGoogleOAuthRedirect(redirectTarget);

        const redirectUri = buildRedirectUri(redirectUriOverride);

        await ensureGuestToken();

        const response = await callWithTokenRefresh(() =>
          apiService.googleOauthStart({ redirect_uri: redirectUri }),
        );
        const payload = extractData<OAuthStartPayload>(response);

        if (!payload.authorization_url) {
          throw new Error('Missing Google authorization URL');
        }

        setGoogleOAuthState(payload.state);
        window.location.href = payload.authorization_url;
      } catch (error: any) {
        clearGoogleSession();
        const message = error?.message || t('auth.googleLoginError');
        toast({
          title: t('auth.failed'),
          description: message,
          variant: 'destructive',
        });
        options.onError?.(error);
        throw error;
      }
    },
    [
      callWithTokenRefresh,
      clearGoogleSession,
      ensureGuestToken,
      options,
      t,
      toast,
    ],
  );

  const finalizeGoogleLogin = useCallback(
    async ({ code, state, fallbackRedirect }: FinalizeGoogleLoginOptions) => {
      if (!code) {
        const error = new Error('Missing OAuth code');
        options.onError?.(error);
        throw error;
      }

      try {
        const expectedState = getGoogleOAuthState();
        if (expectedState && state && expectedState !== state) {
          throw new Error(t('auth.googleStateMismatch'));
        }

        const response = await callWithTokenRefresh(() =>
          apiService.googleOauthCallback({ code, state: state || '' }),
        );
        const payload = extractData<UserTokenPayload>(response);

        if (!payload?.token || !payload?.userInfo) {
          throw new Error('Invalid OAuth callback payload');
        }

        await login(payload.userInfo, payload.token);

        const redirectTarget =
          fallbackRedirect || getGoogleOAuthRedirect() || '/main';

        options.onSuccess?.(payload.userInfo, redirectTarget);
        toast({ title: t('auth.success') });

        clearGoogleSession();

        return {
          redirect: redirectTarget,
          userInfo: payload.userInfo,
        };
      } catch (error: any) {
        clearGoogleSession();
        const message = error?.message || t('auth.googleLoginError');
        toast({
          title: t('auth.failed'),
          description: message,
          variant: 'destructive',
        });
        options.onError?.(error);
        throw error;
      }
    },
    [callWithTokenRefresh, clearGoogleSession, login, options, t, toast],
  );

  const getPendingRedirect = useCallback(() => {
    return getGoogleOAuthRedirect();
  }, []);

  return {
    startGoogleLogin,
    finalizeGoogleLogin,
    clearGoogleSession,
    getPendingRedirect,
  };
}
