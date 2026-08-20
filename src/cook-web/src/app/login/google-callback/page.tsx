'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2, AlertCircle } from 'lucide-react';
import { useGoogleAuth } from '@/hooks/useGoogleAuth';
import { resolveGoogleCallbackOrigin } from '@/lib/google-oauth-callback-origin';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { useTranslation } from 'react-i18next';

export default function GoogleCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const code = searchParams.get('code');
  const state = searchParams.get('state');
  const redirect = searchParams.get('redirect');
  const { finalizeGoogleLogin } = useGoogleAuth();
  const { t } = useTranslation();

  const [error, setError] = useState<string | null>(null);
  const hasHandledRef = useRef(false);

  useEffect(() => {
    if (hasHandledRef.current) {
      return;
    }
    hasHandledRef.current = true;

    const run = async () => {
      console.info('[Google OAuth] running');
      try {
        // Every domain shares one Google callback so that a white-label domain
        // needs no entry of its own in the Google console. If this login began
        // on another domain, hand the code back to it: the token exchange must
        // happen there, where the state was stored and the session belongs.
        if (code && state) {
          const forwardOrigin = await resolveGoogleCallbackOrigin(state);
          if (forwardOrigin && forwardOrigin !== window.location.origin) {
            const forwardUrl = new URL('/login/google-callback', forwardOrigin);
            forwardUrl.searchParams.set('code', code);
            forwardUrl.searchParams.set('state', state);
            if (redirect) {
              forwardUrl.searchParams.set('redirect', redirect);
            }
            // Log the origin only: the URL carries the authorization code
            // and the signed state.
            console.info('[Google OAuth] forwarding to', forwardOrigin);
            window.location.replace(forwardUrl.toString());
            return;
          }
        }

        const fallbackRedirect =
          redirect && redirect.startsWith('/') ? redirect : undefined;
        console.info('[Google OAuth] exchanging token');
        const result = await finalizeGoogleLogin({
          code,
          state,
          fallbackRedirect,
        });
        console.info('[Google OAuth] result', result);
        const targetUrl = `${window.location.origin}${result.redirect}`;
        console.info('[Google OAuth] redirecting to', targetUrl);
        window.location.assign(targetUrl);
      } catch (err: any) {
        console.error('[Google OAuth] finalize error', err);
        setError(err?.message || t('module.auth.googleLoginError'));
        setTimeout(() => {
          const fallbackLoginUrl = `${window.location.origin}/login${
            redirect ? `?redirect=${encodeURIComponent(redirect)}` : ''
          }`;
          console.warn(
            '[Google OAuth] redirecting back to login',
            fallbackLoginUrl,
          );
          window.location.assign(fallbackLoginUrl);
        }, 2500);
      }
    };

    void run();
  }, [code, finalizeGoogleLogin, redirect, router, state, t]);

  return (
    <div className='min-h-screen flex items-center justify-center p-4'>
      <Card className='w-full max-w-sm'>
        <CardHeader>
          <CardTitle className='text-center'>
            {t('module.auth.googleLoginProcessing')}
          </CardTitle>
        </CardHeader>
        <CardContent className='flex flex-col items-center space-y-4 text-center'>
          {error ? (
            <>
              <AlertCircle className='h-10 w-10 text-destructive' />
              <p className='text-sm text-muted-foreground'>{error}</p>
            </>
          ) : (
            <>
              <Loader2 className='h-10 w-10 animate-spin text-primary' />
              <p className='text-sm text-muted-foreground'>
                {t('module.auth.googleLoginRedirecting')}
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
