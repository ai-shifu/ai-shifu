'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  MonitorSmartphone,
  XCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { useUserStore } from '@/store';
import { EVENT_NAMES, useTracking } from '@/hooks/useTracking';
import { normalizeDeviceOsForAnalytics } from './deviceAuthorizationAnalytics';

type PendingDevice = {
  user_code: string;
  device_name: string;
  device_os: string;
  client_version: string;
  client_ip: string;
};

type ResolvedPendingDevice = PendingDevice & {
  openedFromLink: boolean;
};

type Phase = 'loading' | 'confirm' | 'approved' | 'denied' | 'error';

type Envelope = { code?: number; message?: string; data?: unknown };

// The shared request layer stops unwrapping `data` and returns the raw response
// envelope for any path containing '/login', so login screens can render their
// own business errors (src/lib/request.ts). This page lives under
// /login/device, so it must read the envelope itself -- otherwise a business
// error would be mistaken for a success, and a successful payload would be
// read one level too high.
const readEnvelope = (
  raw: unknown,
): { ok: boolean; message: string; data: unknown } => {
  if (!raw || typeof raw !== 'object') {
    return { ok: false, message: '', data: null };
  }
  const envelope = raw as Envelope;
  if (typeof envelope.code === 'number') {
    return {
      ok: envelope.code === 0,
      message: envelope.message ?? '',
      data: envelope.data ?? null,
    };
  }
  return { ok: true, message: '', data: raw };
};

const AUTH_ERROR_CODES = new Set([1001, 1004, 1005]);

const DeviceAuthorizationContent = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const isInitialized = useUserStore(state => state.isInitialized);
  const { trackEvent } = useTracking();

  const codeFromUrl = searchParams.get('code') ?? '';
  const [enteredCode, setEnteredCode] = useState(codeFromUrl);
  const [pending, setPending] = useState<ResolvedPendingDevice | null>(null);
  const [phase, setPhase] = useState<Phase>(
    codeFromUrl ? 'loading' : 'confirm',
  );
  const [errorMessage, setErrorMessage] = useState('');
  const [missingCode, setMissingCode] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const redirectToLogin = useCallback(() => {
    const target = codeFromUrl
      ? `/login/device?code=${encodeURIComponent(codeFromUrl)}`
      : '/login/device';
    router.replace(`/login?redirect=${encodeURIComponent(target)}`);
  }, [codeFromUrl, router]);

  const trackEventRef = useRef(trackEvent);
  useEffect(() => {
    trackEventRef.current = trackEvent;
  }, [trackEvent]);

  const shownPromptRef = useRef<{
    code: string;
    openedFromLink: boolean;
  } | null>(null);

  const redirectToLoginRef = useRef(redirectToLogin);
  useEffect(() => {
    redirectToLoginRef.current = redirectToLogin;
  }, [redirectToLogin]);

  // Send visitors through the normal login page first, then straight back
  // here: an already signed-in browser should never be asked to log in again.
  useEffect(() => {
    if (!isInitialized || isLoggedIn) {
      return;
    }
    redirectToLogin();
  }, [isInitialized, isLoggedIn, redirectToLogin]);

  const loadPending = useCallback(async (code: string, fromLink: boolean) => {
    setPhase('loading');
    setErrorMessage('');
    try {
      const { ok, message, data } = readEnvelope(
        await api.deviceAuthPending({ user_code: code }),
      );
      const device =
        ok && data && typeof data === 'object' ? (data as PendingDevice) : null;
      if (!device?.user_code) {
        setErrorMessage(message);
        setPhase('error');
        return;
      }
      setPending({ ...device, openedFromLink: fromLink });
      setPhase('confirm');
    } catch (error) {
      // An expired token arrives here as a rejection, and the request layer
      // skips its own login redirect for every path containing '/login'.
      const errorCode = (error as { code?: number } | null)?.code;
      if (typeof errorCode === 'number' && AUTH_ERROR_CODES.has(errorCode)) {
        redirectToLoginRef.current();
        return;
      }
      setErrorMessage((error as Error)?.message || '');
      setPhase('error');
    }
  }, []);

  useEffect(() => {
    if (!isInitialized || !isLoggedIn || !codeFromUrl) {
      return;
    }
    void loadPending(codeFromUrl, true);
  }, [codeFromUrl, isInitialized, isLoggedIn, loadPending]);

  // One exposure per resolved request: the pairing code identifies the
  // request, so re-renders cannot inflate the eligible-view denominator. The
  // code itself is never sent -- it is a live credential for ten minutes.
  useEffect(() => {
    const code = pending?.user_code;
    if (!code || shownPromptRef.current?.code === code) {
      return;
    }
    shownPromptRef.current = {
      code,
      openedFromLink: pending.openedFromLink,
    };
    void trackEventRef.current(EVENT_NAMES.DEVICE_AUTH_PROMPT_SHOWN, {
      device_os: normalizeDeviceOsForAnalytics(pending?.device_os),
      from_link: pending.openedFromLink,
    });
  }, [pending]);

  const handleLookup = useCallback(() => {
    const code = enteredCode.trim();
    if (!code) {
      setMissingCode(true);
      return;
    }
    setMissingCode(false);
    void loadPending(code, false);
  }, [enteredCode, loadPending]);

  const handleDecision = useCallback(
    async (approve: boolean) => {
      const code = pending?.user_code || enteredCode.trim();
      if (!code) {
        return;
      }
      setSubmitting(true);
      setErrorMessage('');
      try {
        const { ok, message } = readEnvelope(
          approve
            ? await api.deviceAuthApprove({ user_code: code })
            : await api.deviceAuthDeny({ user_code: code }),
        );
        if (!ok) {
          setErrorMessage(message);
          setPhase('error');
          return;
        }
        setPhase(approve ? 'approved' : 'denied');
        const openedFromLink =
          shownPromptRef.current?.code === code
            ? shownPromptRef.current.openedFromLink
            : (pending?.openedFromLink ?? false);
        void trackEventRef.current(
          approve
            ? EVENT_NAMES.DEVICE_AUTH_APPROVED
            : EVENT_NAMES.DEVICE_AUTH_DENIED,
          {
            device_os: normalizeDeviceOsForAnalytics(pending?.device_os),
            from_link: openedFromLink,
          },
        );
      } catch (error) {
        setErrorMessage((error as Error)?.message || '');
        setPhase('error');
      } finally {
        setSubmitting(false);
      }
    },
    [enteredCode, pending],
  );

  const renderDetail = (label: string, value: string) => (
    <div className='flex items-start justify-between gap-4 text-sm'>
      <span className='text-muted-foreground shrink-0'>{label}</span>
      <span className='text-right break-all'>{value}</span>
    </div>
  );

  const renderBody = () => {
    if (!isInitialized || (!isLoggedIn && codeFromUrl)) {
      return (
        <div className='flex flex-col items-center space-y-4 text-center'>
          <Loader2 className='h-10 w-10 animate-spin text-primary' />
        </div>
      );
    }

    if (phase === 'loading') {
      return (
        <div className='flex flex-col items-center space-y-4 text-center'>
          <Loader2 className='h-10 w-10 animate-spin text-primary' />
          <p className='text-sm text-muted-foreground'>
            {t('module.auth.deviceAuthLoading')}
          </p>
        </div>
      );
    }

    if (phase === 'approved') {
      return (
        <div className='flex flex-col items-center space-y-4 text-center'>
          <CheckCircle2 className='h-10 w-10 text-primary' />
          <p className='font-medium'>
            {t('module.auth.deviceAuthApprovedTitle')}
          </p>
          <p className='text-sm text-muted-foreground'>
            {t('module.auth.deviceAuthApprovedHint')}
          </p>
        </div>
      );
    }

    if (phase === 'denied') {
      return (
        <div className='flex flex-col items-center space-y-4 text-center'>
          <XCircle className='h-10 w-10 text-muted-foreground' />
          <p className='font-medium'>
            {t('module.auth.deviceAuthDeniedTitle')}
          </p>
          <p className='text-sm text-muted-foreground'>
            {t('module.auth.deviceAuthDeniedHint')}
          </p>
        </div>
      );
    }

    if (phase === 'error') {
      return (
        <div className='flex flex-col items-center space-y-4 text-center'>
          <AlertCircle className='h-10 w-10 text-destructive' />
          <p className='text-sm text-muted-foreground'>
            {errorMessage || t('module.auth.deviceAuthFailedTitle')}
          </p>
        </div>
      );
    }

    // A pending request was resolved: show what is being authorized, and make
    // the user confirm. Skipping this step would let anyone who can get a link
    // in front of a signed-in user bind that account to their own client.
    if (pending) {
      return (
        <div className='space-y-6'>
          <div className='flex flex-col items-center space-y-3 text-center'>
            <MonitorSmartphone className='h-10 w-10 text-primary' />
            <p className='text-sm'>{t('module.auth.deviceAuthIntro')}</p>
          </div>

          <div className='space-y-2 rounded-md border p-4'>
            {renderDetail(
              t('module.auth.deviceAuthDeviceLabel'),
              pending.device_name || t('module.auth.deviceAuthUnknownDevice'),
            )}
            {pending.device_os
              ? renderDetail(
                  t('module.auth.deviceAuthSystemLabel'),
                  pending.device_os,
                )
              : null}
            {pending.client_ip
              ? renderDetail(
                  t('module.auth.deviceAuthIpLabel'),
                  pending.client_ip,
                )
              : null}
            {renderDetail(
              t('module.auth.deviceAuthCodeLabel'),
              pending.user_code,
            )}
          </div>

          <p className='text-sm text-muted-foreground'>
            {t('module.auth.deviceAuthWarning')}
          </p>

          <div className='flex gap-3'>
            <Button
              className='flex-1'
              disabled={submitting}
              onClick={() => void handleDecision(true)}
            >
              {t('module.auth.deviceAuthApprove')}
            </Button>
            <Button
              className='flex-1'
              variant='outline'
              disabled={submitting}
              onClick={() => void handleDecision(false)}
            >
              {t('module.auth.deviceAuthDeny')}
            </Button>
          </div>
        </div>
      );
    }

    // Reached without a pairing code in the URL, which happens when the user
    // opens the link on a different device and types the code by hand.
    return (
      <div className='space-y-4'>
        <p className='text-sm text-muted-foreground'>
          {t('module.auth.deviceAuthIntro')}
        </p>
        <Input
          value={enteredCode}
          onChange={event => setEnteredCode(event.target.value)}
          placeholder={t('module.auth.deviceAuthCodePlaceholder')}
          aria-label={t('module.auth.deviceAuthCodeLabel')}
        />
        {missingCode ? (
          <p className='text-sm text-destructive'>
            {t('module.auth.deviceAuthCodeRequired')}
          </p>
        ) : null}
        <Button
          className='w-full'
          onClick={handleLookup}
        >
          {t('module.auth.deviceAuthContinue')}
        </Button>
      </div>
    );
  };

  return (
    <div className='min-h-screen flex items-center justify-center p-4'>
      <Card className='w-full max-w-sm'>
        <CardHeader>
          <CardTitle className='text-center'>
            {t('module.auth.deviceAuthTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent>{renderBody()}</CardContent>
      </Card>
    </div>
  );
};

export default function DeviceAuthorizationPage() {
  return (
    <Suspense
      fallback={
        <div className='min-h-screen flex items-center justify-center p-4'>
          <Loader2 className='h-10 w-10 animate-spin text-primary' />
        </div>
      }
    >
      <DeviceAuthorizationContent />
    </Suspense>
  );
}
