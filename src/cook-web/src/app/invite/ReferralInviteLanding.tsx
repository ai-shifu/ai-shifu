'use client';

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { ArrowRight, Loader2, Ticket, UserPlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import logoHorizontal from '@/c-assets/logos/ai-shifu-logo-horizontal.png';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import { ContactSideRail } from '@/components/contact/ContactSideRail';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { resolveOfficialSiteUrl } from '@/config/environment';
import {
  normalizeReferralInviteCode,
  saveReferralContext,
} from '@/lib/referral-context';
import type {
  ReferralEntrySource,
  ReferralInviteEventType,
  ReferralInvitePreview,
} from '@/types/referral';

type ReferralInviteLandingProps = {
  initialInviteCode?: string;
};

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.referral.inviteLanding.badge')
 * t('module.referral.inviteLanding.brandName')
 * t('module.referral.inviteLanding.codeLabel')
 * t('module.referral.inviteLanding.codePlaceholder')
 * t('module.referral.inviteLanding.codeRequired')
 * t('module.referral.inviteLanding.descriptionAfterBrand')
 * t('module.referral.inviteLanding.descriptionBeforeBrand')
 * t('module.referral.inviteLanding.fallbackTitle')
 * t('module.referral.inviteLanding.formAria')
 * t('module.referral.inviteLanding.formTitle')
 * t('module.referral.inviteLanding.invitedTitle')
 * t('module.referral.inviteLanding.register')
 * t('module.referral.inviteLanding.submitFailed')
 * t('module.referral.inviteLanding.title')
 * t('module.referral.inviteLanding.trialHint')
 */

const buildLandingPath = () => {
  if (typeof window === 'undefined') {
    return '';
  }
  return `${window.location.pathname}${window.location.search}`;
};

export function ReferralInviteLanding({
  initialInviteCode = '',
}: ReferralInviteLandingProps) {
  const router = useRouter();
  const { t } = useTranslation('module.referral');
  const officialSiteUrlValue = useEnvStore(
    (state: EnvStoreState) => state.officialSiteUrl,
  );
  const officialSiteUrl = resolveOfficialSiteUrl(officialSiteUrlValue);
  const normalizedInitialCode = useMemo(
    () => normalizeReferralInviteCode(initialInviteCode),
    [initialInviteCode],
  );
  const [inviteCode, setInviteCode] = useState(normalizedInitialCode);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [invitePreview, setInvitePreview] =
    useState<ReferralInvitePreview | null>(null);
  const recordedInitialCodeRef = useRef('');
  const referralSessionIdRef = useRef('');

  const recordInviteEvent = useCallback(
    async (
      eventType: ReferralInviteEventType,
      code: string,
      source: ReferralEntrySource,
    ) => {
      let context = saveReferralContext({
        invite_code: code,
        referral_session_id: referralSessionIdRef.current || undefined,
        referral_entry_source: source,
      });
      referralSessionIdRef.current = context.referral_session_id || '';
      const sessionId = await api
        .recordReferralInviteEvent(
          {
            event_type: eventType,
            invite_code: context.invite_code || '',
            session_id: context.referral_session_id || '',
            frontend_session_id: context.referral_session_id || '',
            entry_source: source,
            landing_path: buildLandingPath(),
          },
          { skipErrorToast: true },
        )
        .then(response =>
          String(
            (response as { session_id?: string } | undefined)?.session_id || '',
          ).trim(),
        )
        .catch(() => '');
      if (sessionId && sessionId !== context.referral_session_id) {
        context = saveReferralContext({
          ...context,
          referral_session_id: sessionId,
        });
        referralSessionIdRef.current = sessionId;
      }
      return context;
    },
    [],
  );

  useEffect(() => {
    if (!normalizedInitialCode) {
      return;
    }
    setInviteCode(normalizedInitialCode);
    void api
      .getReferralInvitePreview(
        { invite_code: normalizedInitialCode },
        { skipErrorToast: true },
      )
      .then(response => {
        setInvitePreview((response || null) as ReferralInvitePreview | null);
      })
      .catch(() => {
        setInvitePreview(null);
      });
    if (recordedInitialCodeRef.current === normalizedInitialCode) {
      return;
    }
    recordedInitialCodeRef.current = normalizedInitialCode;
    void (async () => {
      try {
        await recordInviteEvent(
          'invite_link_clicked',
          normalizedInitialCode,
          'invite_link',
        );
        await recordInviteEvent(
          'registration_page_viewed',
          normalizedInitialCode,
          'invite_link',
        );
      } catch {
        // Event collection must not block registration.
      }
    })();
  }, [normalizedInitialCode, recordInviteEvent]);

  const continueWithInviteCode = async (
    code: string,
    source: ReferralEntrySource,
  ) => {
    const normalizedCode = normalizeReferralInviteCode(code);
    if (!normalizedCode) {
      setError(t('inviteLanding.codeRequired'));
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const context = await recordInviteEvent(
        source === 'manual_code'
          ? 'invite_code_entered'
          : 'registration_submitted',
        normalizedCode,
        source,
      );
      const params = new URLSearchParams();
      params.set('invite_code', normalizedCode);
      if (context.referral_session_id) {
        params.set('referral_session_id', context.referral_session_id);
      }
      router.push(`/login?${params.toString()}`);
    } catch {
      setError(t('inviteLanding.submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const submitInviteCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await continueWithInviteCode(inviteCode, 'manual_code');
  };

  const submitInitialInviteCode = async () => {
    await continueWithInviteCode(normalizedInitialCode, 'invite_link');
  };

  const logo = (
    <Image
      src={logoHorizontal}
      alt='AI-Shifu'
      width={180}
      height={40}
      priority
    />
  );
  const linkedLogo = officialSiteUrl ? (
    <a
      href={officialSiteUrl}
      target='_blank'
      rel='noopener noreferrer'
      aria-label='AI-Shifu'
      className='inline-flex w-fit'
    >
      {logo}
    </a>
  ) : (
    logo
  );
  const brandName = officialSiteUrl ? (
    <a
      href={officialSiteUrl}
      target='_blank'
      rel='noopener noreferrer'
      className='font-medium text-primary underline-offset-4 hover:underline'
    >
      {t('inviteLanding.brandName')}
    </a>
  ) : (
    <span className='font-medium text-foreground'>
      {t('inviteLanding.brandName')}
    </span>
  );
  const maskedMobile = invitePreview?.recognized
    ? invitePreview.inviter_mobile_masked
    : '';

  return (
    <main className='min-h-screen bg-stone-50 px-4 py-8'>
      <ContactSideRail />
      <div className='mx-auto flex min-h-[calc(100vh-64px)] w-full max-w-5xl flex-col justify-center gap-8 lg:flex-row lg:items-center'>
        <section className='min-w-0 flex-1 space-y-6'>
          {linkedLogo}
          <div className='space-y-3'>
            <div className='inline-flex items-center gap-2 rounded-md border border-border bg-white px-3 py-1 text-sm text-muted-foreground'>
              <UserPlus className='h-4 w-4' />
              <span>{t('inviteLanding.badge')}</span>
            </div>
            <h1 className='max-w-2xl text-3xl font-semibold leading-tight text-foreground sm:text-4xl'>
              {maskedMobile
                ? t('inviteLanding.invitedTitle', { maskedMobile })
                : normalizedInitialCode
                  ? t('inviteLanding.fallbackTitle')
                  : t('inviteLanding.title')}
            </h1>
            <p className='max-w-2xl text-base leading-7 text-muted-foreground'>
              {t('inviteLanding.descriptionBeforeBrand')}
              {brandName}
              {t('inviteLanding.descriptionAfterBrand')}
            </p>
          </div>
        </section>

        {normalizedInitialCode ? (
          <section
            className='w-full rounded-lg border border-border bg-white p-5 shadow-sm lg:w-[380px]'
            aria-label={t('inviteLanding.formAria')}
          >
            <div className='space-y-4'>
              <Button
                type='button'
                className='w-full gap-2'
                disabled={submitting}
                onClick={submitInitialInviteCode}
              >
                {submitting ? (
                  <Loader2 className='h-4 w-4 animate-spin' />
                ) : null}
                {t('inviteLanding.register')}
                {!submitting ? <ArrowRight className='h-4 w-4' /> : null}
              </Button>
              <p className='text-sm leading-6 text-muted-foreground'>
                {t('inviteLanding.trialHint')}
              </p>
              {error ? (
                <p className='text-sm text-destructive'>{error}</p>
              ) : null}
            </div>
          </section>
        ) : (
          <section
            className='w-full rounded-lg border border-border bg-white p-5 shadow-sm lg:w-[380px]'
            aria-label={t('inviteLanding.formAria')}
          >
            <form
              className='space-y-4'
              onSubmit={submitInviteCode}
            >
              <div className='flex items-center gap-2 text-sm font-medium text-foreground'>
                <Ticket className='h-4 w-4' />
                <span>{t('inviteLanding.formTitle')}</span>
              </div>
              <div className='space-y-2'>
                <Label htmlFor='referral-invite-code'>
                  {t('inviteLanding.codeLabel')}
                </Label>
                <Input
                  id='referral-invite-code'
                  value={inviteCode}
                  onChange={event => {
                    setInviteCode(event.target.value);
                    if (error) {
                      setError('');
                    }
                  }}
                  placeholder={t('inviteLanding.codePlaceholder')}
                  autoComplete='off'
                  className='uppercase'
                />
                {error ? (
                  <p className='text-sm text-destructive'>{error}</p>
                ) : null}
              </div>
              <Button
                type='submit'
                className='w-full gap-2'
                disabled={submitting}
              >
                {submitting ? (
                  <Loader2 className='h-4 w-4 animate-spin' />
                ) : null}
                {t('inviteLanding.register')}
                {!submitting ? <ArrowRight className='h-4 w-4' /> : null}
              </Button>
              <p className='text-sm leading-6 text-muted-foreground'>
                {t('inviteLanding.trialHint')}
              </p>
            </form>
          </section>
        )}
      </div>
    </main>
  );
}
