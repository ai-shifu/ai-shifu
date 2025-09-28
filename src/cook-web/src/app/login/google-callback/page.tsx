'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2, AlertCircle } from 'lucide-react';
import { useGoogleAuth } from '@/hooks/useGoogleAuth';
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

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      try {
        const fallbackRedirect =
          redirect && redirect.startsWith('/') ? redirect : '/main';
        const result = await finalizeGoogleLogin({
          code,
          state,
          fallbackRedirect,
        });
        if (!cancelled) {
          router.replace(result.redirect);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || t('auth.googleLoginError'));
          setTimeout(() => {
            router.replace(
              `/login${redirect ? `?redirect=${encodeURIComponent(redirect)}` : ''}`,
            );
          }, 2500);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [code, finalizeGoogleLogin, redirect, router, state, t]);

  return (
    <div className='min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4'>
      <Card className='w-full max-w-sm'>
        <CardHeader>
          <CardTitle className='text-center'>
            {t('auth.googleLoginProcessing')}
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
                {t('auth.googleLoginRedirecting')}
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
