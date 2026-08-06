'use client';

import React from 'react';
import {
  Check,
  ChevronRight,
  Copy,
  MessageCircleQuestion,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  createProfileOnboardingSession,
  runProfileOnboardingSession,
  type ProfileOnboardingPresentation,
  type ProfileOnboardingSessionIntent,
} from '@/c-api/user';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Textarea } from '@/components/ui/Textarea';
import { cn } from '@/lib/utils';
import { useTracking } from '@/c-common/hooks/useTracking';
import ProfileOnboardingConversation from './ProfileOnboardingConversation';
import { PROFILE_ONBOARDING_EVENTS } from './events';

const LEGACY_PASTE_DRAFT_STORAGE_KEY =
  'profile-onboarding-paste-draft:profile-v2';
const PASTE_DRAFT_STORAGE_KEY_PREFIX =
  'profile-onboarding-paste-draft:profile-v2:';
const ACTIVE_PASTE_DRAFT_STORAGE_KEY =
  'profile-onboarding-paste-draft:active-user:profile-v2';

type ProfileOnboardingRoute = 'choice' | 'paste' | 'guided' | 'review';
type ProfileSource = 'guided' | 'pasted';

export type ProfileOnboardingModalProps = {
  open: boolean;
  presentation?: ProfileOnboardingPresentation;
  sessionIntent?: ProfileOnboardingSessionIntent;
  guidedAvailable?: boolean;
  maxLength?: number;
  draftStorageScope?: string;
  errorMessage?: string;
  submitting?: boolean;
  onComplete: (
    learnerProfile: string,
    source: ProfileSource,
    sessionId?: string,
  ) => void | boolean | Promise<void | boolean>;
  onSkip: (sessionId?: string) => void | boolean | Promise<void | boolean>;
};

export const countUnicodeCodePoints = (value: string) =>
  Array.from(value).length;

const resolvePasteDraftStorageKey = (scope: string) => {
  const normalizedScope = scope.trim();
  return normalizedScope
    ? `${PASTE_DRAFT_STORAGE_KEY_PREFIX}${encodeURIComponent(normalizedScope)}`
    : '';
};

const readPasteDraft = (storageKey: string) => {
  if (typeof window === 'undefined') {
    return '';
  }
  try {
    window.sessionStorage.removeItem(LEGACY_PASTE_DRAFT_STORAGE_KEY);
    const previousStorageKey = window.sessionStorage.getItem(
      ACTIVE_PASTE_DRAFT_STORAGE_KEY,
    );
    if (
      previousStorageKey &&
      previousStorageKey !== storageKey &&
      previousStorageKey.startsWith(PASTE_DRAFT_STORAGE_KEY_PREFIX)
    ) {
      window.sessionStorage.removeItem(previousStorageKey);
    }
    if (!storageKey) {
      window.sessionStorage.removeItem(ACTIVE_PASTE_DRAFT_STORAGE_KEY);
      return '';
    }
    window.sessionStorage.setItem(ACTIVE_PASTE_DRAFT_STORAGE_KEY, storageKey);
    return window.sessionStorage.getItem(storageKey) || '';
  } catch {
    return '';
  }
};

const writePasteDraft = (storageKey: string, draft: string) => {
  if (typeof window === 'undefined' || !storageKey) {
    return;
  }
  try {
    if (draft) {
      window.sessionStorage.setItem(storageKey, draft);
    } else {
      window.sessionStorage.removeItem(storageKey);
    }
  } catch {
    // Ignore storage errors in restricted browser modes.
  }
};

const clearPasteDraft = (storageKey: string) => {
  if (typeof window === 'undefined' || !storageKey) {
    return;
  }
  try {
    window.sessionStorage.removeItem(storageKey);
  } catch {
    // Ignore storage errors in restricted browser modes.
  }
};

export default function ProfileOnboardingModal({
  open,
  presentation = 'blocking',
  sessionIntent = 'onboarding',
  guidedAvailable = true,
  maxLength = 1000,
  draftStorageScope = '',
  errorMessage = '',
  submitting = false,
  onComplete,
  onSkip,
}: ProfileOnboardingModalProps) {
  const { t, i18n } = useTranslation();
  const { trackEvent } = useTracking();
  const [route, setRoute] = React.useState<ProfileOnboardingRoute>('choice');
  const [draft, setDraft] = React.useState('');
  const [draftStorageOwnerKey, setDraftStorageOwnerKey] = React.useState('');
  const [source, setSource] = React.useState<ProfileSource>('pasted');
  const [sessionId, setSessionId] = React.useState('');
  const [copyState, setCopyState] = React.useState<'idle' | 'copied'>('idle');
  const [runtimeError, setRuntimeError] = React.useState('');
  const shownRef = React.useRef(false);
  const shownAtRef = React.useRef<number | null>(null);
  const titleRef = React.useRef<HTMLHeadingElement>(null);
  const presentationRef = React.useRef(presentation);
  const trackEventRef = React.useRef(trackEvent);
  presentationRef.current = presentation;
  trackEventRef.current = trackEvent;
  const externalAgentPrompt = t(
    'module.profileOnboarding.externalAgent.prompt',
  );
  const isNonBlocking = presentation === 'non_blocking';
  const pasteDraftStorageKey = React.useMemo(
    () => resolvePasteDraftStorageKey(draftStorageScope),
    [draftStorageScope],
  );

  React.useEffect(() => {
    // Reconcile the owner even while the modal is closed so logout/account
    // switches cannot leave another user's draft available to later code in
    // the same tab.
    readPasteDraft(pasteDraftStorageKey);
  }, [pasteDraftStorageKey]);

  React.useEffect(() => {
    if (!open) {
      shownRef.current = false;
      shownAtRef.current = null;
      return;
    }
    if (!shownRef.current) {
      shownRef.current = true;
      shownAtRef.current = Date.now();
      void trackEventRef.current(PROFILE_ONBOARDING_EVENTS.SHOWN, {
        presentation: presentationRef.current,
      });
    }
    setRoute('choice');
    setDraft(readPasteDraft(pasteDraftStorageKey));
    setDraftStorageOwnerKey(pasteDraftStorageKey);
    setSource('pasted');
    setSessionId('');
    setCopyState('idle');
    setRuntimeError('');
  }, [open, pasteDraftStorageKey]);

  React.useEffect(() => {
    if (
      route !== 'paste' ||
      draftStorageOwnerKey !== pasteDraftStorageKey ||
      typeof window === 'undefined'
    ) {
      return;
    }
    writePasteDraft(pasteDraftStorageKey, draft);
  }, [draft, draftStorageOwnerKey, pasteDraftStorageKey, route]);

  const createSession = React.useCallback(
    () =>
      createProfileOnboardingSession(
        i18n.resolvedLanguage ?? i18n.language,
        sessionIntent,
      ),
    [i18n.language, i18n.resolvedLanguage, sessionIntent],
  );
  const runSession = React.useCallback(
    ({
      sessionId: activeSessionId,
      expectedBlockIndex,
      requestId,
      userInput,
      onMessage,
      onError,
    }: Parameters<
      React.ComponentProps<typeof ProfileOnboardingConversation>['runSession']
    >[0]) =>
      runProfileOnboardingSession({
        sessionId: activeSessionId,
        expectedBlockIndex,
        requestId,
        userInput,
        language: i18n.resolvedLanguage ?? i18n.language,
        onMessage,
        onError,
      }),
    [i18n.language, i18n.resolvedLanguage],
  );

  const handleDraftChange = React.useCallback((value: string) => {
    setDraft(value);
  }, []);

  const handleCopyPrompt = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(externalAgentPrompt);
      setCopyState('copied');
      window.setTimeout(() => setCopyState('idle'), 1800);
    } catch {
      setRuntimeError(t('module.profileOnboarding.externalAgent.copyFailed'));
    }
  }, [externalAgentPrompt, t]);

  const handleSubmit = React.useCallback(async () => {
    const learnerProfile = draft.trim();
    if (
      !learnerProfile ||
      countUnicodeCodePoints(learnerProfile) > maxLength ||
      submitting
    ) {
      return;
    }
    const completed = await onComplete(
      learnerProfile,
      source,
      sessionId || undefined,
    );
    if (completed === false) {
      return;
    }
    const durationMs =
      shownAtRef.current === null
        ? 0
        : Math.max(0, Date.now() - shownAtRef.current);
    void trackEvent(PROFILE_ONBOARDING_EVENTS.COMPLETED, {
      source,
      presentation,
      duration_ms: durationMs,
    });
    clearPasteDraft(pasteDraftStorageKey);
  }, [
    draft,
    maxLength,
    onComplete,
    pasteDraftStorageKey,
    presentation,
    sessionId,
    source,
    submitting,
    trackEvent,
  ]);

  const handleSkip = React.useCallback(async () => {
    const skipped = await onSkip(sessionId || undefined);
    if (skipped === false) {
      return;
    }
    const durationMs =
      shownAtRef.current === null
        ? 0
        : Math.max(0, Date.now() - shownAtRef.current);
    void trackEvent(PROFILE_ONBOARDING_EVENTS.SKIPPED, {
      action: 'skipped',
      presentation,
      duration_ms: durationMs,
    });
    clearPasteDraft(pasteDraftStorageKey);
  }, [onSkip, pasteDraftStorageKey, presentation, sessionId, trackEvent]);

  const profileLength = countUnicodeCodePoints(draft.trim());
  const combinedError = errorMessage || runtimeError;
  return (
    <Dialog open={open}>
      <DialogContent
        className={cn(
          'flex max-h-[calc(100dvh-24px)] w-[calc(100vw-24px)] max-w-[600px] flex-col gap-0 overflow-hidden rounded-2xl border border-border/80 bg-background p-0 shadow-[0_24px_80px_rgba(15,23,42,0.24)] outline-none',
          'sm:max-h-[min(760px,calc(100dvh-48px))] sm:rounded-2xl',
        )}
        showClose={false}
        onOpenAutoFocus={event => {
          event.preventDefault();
          titleRef.current?.focus();
        }}
        onEscapeKeyDown={event => event.preventDefault()}
        onInteractOutside={event => event.preventDefault()}
      >
        <div className='border-b border-border/70 bg-gradient-to-br from-primary/[0.09] via-background to-background px-5 py-5 sm:px-6 sm:py-6'>
          <DialogHeader className='text-left'>
            <div className='flex items-start gap-3.5'>
              <div className='mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm'>
                <Sparkles
                  className='h-5 w-5'
                  aria-hidden='true'
                />
              </div>
              <div className='min-w-0 space-y-1.5'>
                <DialogTitle
                  ref={titleRef}
                  tabIndex={-1}
                  className='text-xl leading-7 tracking-tight outline-none sm:text-2xl'
                >
                  {t('module.profileOnboarding.title')}
                </DialogTitle>
                <DialogDescription className='max-w-[48ch] text-sm leading-6'>
                  {isNonBlocking
                    ? t('module.profileOnboarding.upgradeDescription')
                    : t('module.profileOnboarding.description')}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
        </div>

        <div className='min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6 sm:py-6'>
          {route === 'choice' ? (
            <section className='space-y-4'>
              <div>
                <h2 className='text-lg font-semibold leading-7 tracking-tight'>
                  {t('module.profileOnboarding.routeQuestion')}
                </h2>
                <p className='mt-1 text-sm leading-6 text-muted-foreground'>
                  {t('module.profileOnboarding.routeQuestionHint')}
                </p>
              </div>
              <div className='flex items-start gap-2.5 rounded-xl bg-muted/50 px-3.5 py-3 text-muted-foreground'>
                <ShieldCheck
                  className='mt-0.5 h-4 w-4 shrink-0 text-primary'
                  aria-hidden='true'
                />
                <p className='text-xs leading-5'>
                  {t('module.profileOnboarding.privacyNotice')}
                </p>
              </div>
              <div className='grid gap-3'>
                <button
                  type='button'
                  className='group flex w-full items-center gap-3.5 rounded-xl border border-border bg-card p-4 text-left shadow-sm transition-colors hover:border-primary/40 hover:bg-primary/[0.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'
                  disabled={submitting}
                  onClick={() => {
                    setSource('pasted');
                    setRuntimeError('');
                    setRoute('paste');
                    void trackEvent(PROFILE_ONBOARDING_EVENTS.ROUTE_SELECTED, {
                      route: 'pasted',
                      presentation,
                    });
                  }}
                >
                  <span className='flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary'>
                    <Sparkles
                      className='h-5 w-5'
                      aria-hidden='true'
                    />
                  </span>
                  <span className='min-w-0 flex-1'>
                    <span className='block font-medium leading-6'>
                      {t('module.profileOnboarding.hasAgent.yes')}
                    </span>
                    <span className='mt-0.5 block text-sm leading-5 text-muted-foreground'>
                      {t('module.profileOnboarding.hasAgent.yesHint')}
                    </span>
                  </span>
                  <ChevronRight
                    className='h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary'
                    aria-hidden='true'
                  />
                </button>
                <button
                  type='button'
                  className='group flex w-full items-center gap-3.5 rounded-xl border border-border bg-card p-4 text-left shadow-sm transition-colors hover:border-primary/40 hover:bg-primary/[0.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'
                  disabled={submitting || !guidedAvailable}
                  onClick={() => {
                    setSource('guided');
                    setRuntimeError('');
                    setRoute('guided');
                    void trackEvent(PROFILE_ONBOARDING_EVENTS.ROUTE_SELECTED, {
                      route: 'guided',
                      presentation,
                    });
                  }}
                >
                  <span className='flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary'>
                    <MessageCircleQuestion
                      className='h-5 w-5'
                      aria-hidden='true'
                    />
                  </span>
                  <span className='min-w-0 flex-1'>
                    <span className='block font-medium leading-6'>
                      {t('module.profileOnboarding.hasAgent.no')}
                    </span>
                    <span className='mt-0.5 block text-sm leading-5 text-muted-foreground'>
                      {guidedAvailable
                        ? t('module.profileOnboarding.hasAgent.noHint')
                        : t('module.profileOnboarding.guided.unavailable')}
                    </span>
                  </span>
                  <ChevronRight
                    className='h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary'
                    aria-hidden='true'
                  />
                </button>
              </div>
            </section>
          ) : null}

          {route === 'paste' ? (
            <section className='space-y-5'>
              <div className='space-y-2'>
                <div className='flex items-center justify-between gap-3'>
                  <h2 className='font-medium'>
                    {t('module.profileOnboarding.externalAgent.title')}
                  </h2>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    disabled={submitting}
                    onClick={handleCopyPrompt}
                  >
                    {copyState === 'copied' ? (
                      <Check
                        className='mr-1.5 h-4 w-4'
                        aria-hidden='true'
                      />
                    ) : (
                      <Copy
                        className='mr-1.5 h-4 w-4'
                        aria-hidden='true'
                      />
                    )}
                    {copyState === 'copied'
                      ? t('module.profileOnboarding.externalAgent.copied')
                      : t('module.profileOnboarding.externalAgent.copy')}
                  </Button>
                </div>
                <div className='whitespace-pre-wrap rounded-lg border bg-muted/40 p-4 text-sm leading-6'>
                  {externalAgentPrompt}
                </div>
                <p className='text-xs leading-5 text-muted-foreground'>
                  {t('module.profileOnboarding.externalAgent.switchHint')}
                </p>
              </div>
              <ProfileDraftEditor
                inputId='profile-onboarding-paste-draft'
                value={draft}
                maxLength={maxLength}
                disabled={submitting}
                onChange={handleDraftChange}
              />
            </section>
          ) : null}

          {route === 'guided' ? (
            <section className='space-y-3'>
              <p className='text-sm leading-6 text-muted-foreground'>
                {t('module.profileOnboarding.guided.description')}
              </p>
              <ProfileOnboardingConversation
                createSession={createSession}
                runSession={runSession}
                onSessionStarted={setSessionId}
                onDraftReady={(profileDraft, activeSessionId) => {
                  setDraft(profileDraft);
                  setSessionId(activeSessionId);
                  setSource('guided');
                  setRuntimeError('');
                  setRoute('review');
                }}
                onRetry={() => setRuntimeError('')}
                onError={error => {
                  void trackEvent(PROFILE_ONBOARDING_EVENTS.RUNTIME_FAILED, {
                    stage: 'guided',
                    presentation,
                  });
                  setRuntimeError(
                    error instanceof Error && error.message
                      ? error.message
                      : t('module.profileOnboarding.guided.streamError'),
                  );
                }}
              />
            </section>
          ) : null}

          {route === 'review' ? (
            <section className='space-y-4'>
              <div>
                <h2 className='font-medium'>
                  {t('module.profileOnboarding.review.title')}
                </h2>
                <p className='mt-1 text-sm leading-6 text-muted-foreground'>
                  {t('module.profileOnboarding.review.description')}
                </p>
              </div>
              <ProfileDraftEditor
                inputId='profile-onboarding-review-draft'
                value={draft}
                maxLength={maxLength}
                disabled={submitting}
                onChange={handleDraftChange}
              />
            </section>
          ) : null}

          {combinedError ? (
            <div
              role='alert'
              className='mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive'
            >
              {combinedError}
            </div>
          ) : null}
        </div>

        <DialogFooter
          className={cn(
            'gap-2 border-t border-border/70 bg-muted/20 px-5 py-3.5 sm:flex-row sm:items-center sm:space-x-0 sm:px-6',
            route === 'choice'
              ? 'items-center sm:justify-center'
              : 'sm:justify-between',
          )}
        >
          <div
            className={cn(
              'flex items-center gap-1',
              route === 'choice'
                ? 'justify-center'
                : 'w-full justify-between sm:w-auto sm:justify-start',
            )}
          >
            {route !== 'choice' ? (
              <Button
                type='button'
                variant='ghost'
                disabled={submitting}
                onClick={() => {
                  setRuntimeError('');
                  setRoute('choice');
                }}
              >
                {t('module.profileOnboarding.back')}
              </Button>
            ) : null}
            <Button
              type='button'
              variant='ghost'
              className='text-muted-foreground hover:text-foreground'
              disabled={submitting}
              onClick={handleSkip}
            >
              {t(
                sessionIntent === 'settings'
                  ? 'module.profileOnboarding.settings.cancel'
                  : 'module.profileOnboarding.skip',
              )}
            </Button>
          </div>
          {route === 'paste' || route === 'review' ? (
            <Button
              type='button'
              disabled={
                !draft.trim() || profileLength > maxLength || submitting
              }
              className='w-full sm:w-auto'
              onClick={handleSubmit}
            >
              {t(
                sessionIntent === 'settings'
                  ? 'module.profileOnboarding.settings.save'
                  : 'module.profileOnboarding.complete',
              )}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ProfileDraftEditor({
  inputId = 'profile-onboarding-draft',
  value,
  maxLength,
  disabled,
  onChange,
}: {
  inputId?: string;
  value: string;
  maxLength: number;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const length = countUnicodeCodePoints(value.trim());
  return (
    <div className='space-y-2'>
      <label
        htmlFor={inputId}
        className='text-sm font-medium'
      >
        {t('module.profileOnboarding.profileLabel')}
      </label>
      <Textarea
        id={inputId}
        value={value}
        minRows={8}
        maxRows={14}
        disabled={disabled}
        placeholder={t('module.profileOnboarding.profilePlaceholder')}
        aria-describedby={`${inputId}-character-count`}
        onChange={event => onChange(event.target.value)}
      />
      <div
        id={`${inputId}-character-count`}
        className={cn(
          'text-right text-xs text-muted-foreground',
          length > maxLength && 'font-medium text-destructive',
        )}
        aria-live='polite'
      >
        {t(
          length > maxLength
            ? 'module.profileOnboarding.characterCountOverLimit'
            : 'module.profileOnboarding.characterCount',
          {
            count: length,
            max: maxLength,
          },
        )}
      </div>
    </div>
  );
}
