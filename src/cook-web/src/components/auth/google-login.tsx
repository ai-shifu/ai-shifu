'use client';

import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/c-store/useUserStore';
import apiService from '@/api';
import type { UserInfo } from '@/c-types';
import { environment } from '@/config/environment';

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: GoogleInitConfig) => void;
          renderButton: (
            element: HTMLElement,
            config: GoogleButtonConfig,
          ) => void;
          prompt: () => void;
        };
      };
    };
  }
}

interface GoogleInitConfig {
  client_id: string;
  callback: (response: GoogleCredentialResponse) => void;
  auto_select?: boolean;
  cancel_on_tap_outside?: boolean;
}

interface GoogleButtonConfig {
  theme?: 'outline' | 'filled_blue' | 'filled_black';
  size?: 'large' | 'medium' | 'small';
  text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin';
  shape?: 'rectangular' | 'pill' | 'circle' | 'square';
  locale?: string;
}

interface GoogleCredentialResponse {
  credential: string;
  select_by?: string;
}

interface GoogleLoginProps {
  onLoginSuccess: (userInfo: UserInfo) => void;
  clientId?: string;
}

export function GoogleLogin({
  onLoginSuccess,
  clientId = environment.googleClientId,
}: GoogleLoginProps) {
  const { toast } = useToast();
  const { login } = useUserStore();
  const [isLoading, setIsLoading] = useState(false);
  const [isGoogleLoaded, setIsGoogleLoaded] = useState(false);
  const { t, i18n } = useTranslation();

  const handleGoogleResponse = useCallback(
    async (response: GoogleCredentialResponse) => {
      if (!response.credential) {
        toast({
          title: t('login.google-auth-failed', 'Google authentication failed'),
          variant: 'destructive',
        });
        return;
      }

      try {
        setIsLoading(true);

        const result = await apiService.googleOAuthLogin({
          id_token: response.credential,
          language: i18n.language,
        });

        if (result.code === 0) {
          toast({
            title: t('login.login-success', 'Login successful'),
          });

          await login(result.data.userInfo, result.data.token);
          onLoginSuccess(result.data.userInfo);
        } else {
          toast({
            title: t(
              'login.google-auth-failed',
              'Google authentication failed',
            ),
            description:
              result.message || t('login.network-error', 'Network error'),
            variant: 'destructive',
          });
        }
      } catch (error: unknown) {
        console.error('Google OAuth error:', error);
        const errorMessage =
          error instanceof Error ? error.message : 'Unknown error';
        toast({
          title: t('login.google-auth-failed', 'Google authentication failed'),
          description:
            errorMessage || t('login.network-error', 'Network error'),
          variant: 'destructive',
        });
      } finally {
        setIsLoading(false);
      }
    },
    [toast, t, i18n.language, login, onLoginSuccess],
  );

  const initializeGoogleSignIn = useCallback(() => {
    if (!window.google || !clientId) return;

    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: handleGoogleResponse,
      auto_select: false,
      cancel_on_tap_outside: true,
    });
  }, [clientId, handleGoogleResponse]);

  useEffect(() => {
    if (!clientId) {
      console.warn('Google Client ID not configured');
      return;
    }

    // Load Google Identity Services script
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;

    script.onload = () => {
      if (window.google) {
        initializeGoogleSignIn();
        setIsGoogleLoaded(true);
      }
    };

    script.onerror = () => {
      toast({
        title: t(
          'login.google-script-load-error',
          'Failed to load Google Sign-In',
        ),
        variant: 'destructive',
      });
    };

    document.head.appendChild(script);

    return () => {
      if (document.head.contains(script)) {
        document.head.removeChild(script);
      }
    };
  }, [clientId, t, toast, initializeGoogleSignIn]);

  const handleGoogleSignIn = () => {
    if (!window.google || !isGoogleLoaded) {
      toast({
        title: t('login.google-not-ready', 'Google Sign-In not ready'),
        description: t(
          'login.please-try-again',
          'Please try again in a moment',
        ),
        variant: 'destructive',
      });
      return;
    }

    // Trigger the Google Sign-In flow
    window.google.accounts.id.prompt();
  };

  if (!clientId) {
    return null; // Don't render if no client ID configured
  }

  return (
    <div className='space-y-4'>
      <div className='relative'>
        <div className='absolute inset-0 flex items-center'>
          <span className='w-full border-t' />
        </div>
        <div className='relative flex justify-center text-xs uppercase'>
          <span className='bg-background px-2 text-muted-foreground'>
            {t('login.or-continue-with', 'Or continue with')}
          </span>
        </div>
      </div>

      <Button
        variant='outline'
        type='button'
        className='w-full h-10'
        onClick={handleGoogleSignIn}
        disabled={isLoading || !isGoogleLoaded}
      >
        {isLoading ? (
          <Loader2 className='h-4 w-4 animate-spin mr-2' />
        ) : (
          <svg
            className='h-4 w-4 mr-2'
            viewBox='0 0 24 24'
          >
            <path
              fill='currentColor'
              d='M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z'
            />
            <path
              fill='currentColor'
              d='M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z'
            />
            <path
              fill='currentColor'
              d='M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z'
            />
            <path
              fill='currentColor'
              d='M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z'
            />
          </svg>
        )}
        {t('login.continue-with-google', 'Continue with Google')}
      </Button>
    </div>
  );
}
