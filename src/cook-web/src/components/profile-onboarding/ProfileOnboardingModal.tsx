'use client';

import React from 'react';
import {
  Check,
  ChevronDown,
  Copy,
  Loader2,
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
type TransitionDirection = 'forward' | 'backward';
type PendingAction = 'complete' | 'skip';

const PROFILE_ONBOARDING_STEPS = ['choose', 'collect', 'review'] as const;
const PROFILE_ONBOARDING_STEP_COUNT = PROFILE_ONBOARDING_STEPS.length;
const ROUTE_STEP_INDEX: Record<ProfileOnboardingRoute, number> = {
  choice: 0,
  paste: 1,
  guided: 1,
  review: 2,
};

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
  const [transitionDirection, setTransitionDirection] =
    React.useState<TransitionDirection>('forward');
  const [draft, setDraft] = React.useState('');
  const [pastedDraft, setPastedDraft] = React.useState('');
  const [draftStorageOwnerKey, setDraftStorageOwnerKey] = React.useState('');
  const [source, setSource] = React.useState<ProfileSource | null>(null);
  const [sessionId, setSessionId] = React.useState('');
  const [guidedStarted, setGuidedStarted] = React.useState(false);
  const [guidedReady, setGuidedReady] = React.useState(false);
  const [copyState, setCopyState] = React.useState<'idle' | 'copied'>('idle');
  const [runtimeError, setRuntimeError] = React.useState('');
  const [pendingAction, setPendingAction] =
    React.useState<PendingAction | null>(null);
  const shownRef = React.useRef(false);
  const shownAtRef = React.useRef<number | null>(null);
  const routeHeadingRef = React.useRef<HTMLHeadingElement>(null);
  const pageScrollRef = React.useRef<HTMLDivElement>(null);
  const actionPendingRef = React.useRef(false);
  const routeRef = React.useRef(route);
  const sourceRef = React.useRef(source);
  const presentationRef = React.useRef(presentation);
  const trackEventRef = React.useRef(trackEvent);
  routeRef.current = route;
  sourceRef.current = source;
  presentationRef.current = presentation;
  trackEventRef.current = trackEvent;
  const externalAgentPrompt = t(
    'module.profileOnboarding.externalAgent.prompt',
  );
  const isNonBlocking = presentation === 'non_blocking';
  const isBusy = submitting || pendingAction !== null;
  const currentStepIndex = ROUTE_STEP_INDEX[route];
  const currentStepNumber = currentStepIndex + 1;
  const pageTitle =
    route === 'choice'
      ? t('module.profileOnboarding.choice.title')
      : route === 'paste'
        ? t('module.profileOnboarding.externalAgent.title')
        : route === 'guided'
          ? t('module.profileOnboarding.guided.title')
          : t('module.profileOnboarding.review.title');
  const pageDescription =
    route === 'choice'
      ? t('module.profileOnboarding.choice.description')
      : route === 'paste'
        ? t('module.profileOnboarding.externalAgent.description')
        : route === 'guided'
          ? t('module.profileOnboarding.guided.description')
          : t('module.profileOnboarding.review.description');
  const stepLabels = [
    t('module.profileOnboarding.steps.choose'),
    t('module.profileOnboarding.steps.collect'),
    t('module.profileOnboarding.steps.review'),
  ];
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
      setRoute('choice');
      setTransitionDirection('forward');
      setSource(null);
      setSessionId('');
      setGuidedStarted(false);
      setGuidedReady(false);
      setCopyState('idle');
      setRuntimeError('');
      actionPendingRef.current = false;
      setPendingAction(null);
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
    setTransitionDirection('forward');
    const storedPastedDraft = readPasteDraft(pasteDraftStorageKey);
    setDraft(storedPastedDraft);
    setPastedDraft(storedPastedDraft);
    setDraftStorageOwnerKey(pasteDraftStorageKey);
    setSource(null);
    setSessionId('');
    setGuidedStarted(false);
    setGuidedReady(false);
    setCopyState('idle');
    setRuntimeError('');
    actionPendingRef.current = false;
    setPendingAction(null);
  }, [open, pasteDraftStorageKey]);

  React.useEffect(() => {
    if (
      source !== 'pasted' ||
      (route !== 'paste' && route !== 'review') ||
      draftStorageOwnerKey !== pasteDraftStorageKey ||
      typeof window === 'undefined'
    ) {
      return;
    }
    writePasteDraft(pasteDraftStorageKey, pastedDraft);
  }, [draftStorageOwnerKey, pastedDraft, pasteDraftStorageKey, route, source]);

  React.useEffect(() => {
    pageScrollRef.current?.scrollTo?.({ top: 0, behavior: 'auto' });
    if (pageScrollRef.current) {
      pageScrollRef.current.scrollTop = 0;
    }
    routeHeadingRef.current?.focus();
  }, [route]);

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
    if (sourceRef.current === 'pasted') {
      setPastedDraft(value);
    }
  }, []);

  const transitionTo = React.useCallback(
    (nextRoute: ProfileOnboardingRoute, direction: TransitionDirection) => {
      setRuntimeError('');
      setTransitionDirection(direction);
      setRoute(nextRoute);
    },
    [],
  );

  const unlockAction = React.useCallback(() => {
    actionPendingRef.current = false;
    setPendingAction(null);
  }, []);

  const lockAction = React.useCallback(
    (action: PendingAction) => {
      if (actionPendingRef.current || submitting) {
        return false;
      }
      actionPendingRef.current = true;
      setPendingAction(action);
      return true;
    },
    [submitting],
  );

  const handleCopyPrompt = React.useCallback(async () => {
    if (isBusy) {
      return;
    }
    try {
      await navigator.clipboard.writeText(externalAgentPrompt);
      setCopyState('copied');
      window.setTimeout(() => setCopyState('idle'), 1800);
    } catch {
      setRuntimeError(t('module.profileOnboarding.externalAgent.copyFailed'));
    }
  }, [externalAgentPrompt, isBusy, t]);

  const handleChoiceContinue = React.useCallback(() => {
    if (!source || isBusy || (source === 'guided' && !guidedAvailable)) {
      return;
    }
    if (source === 'pasted') {
      setDraft(pastedDraft);
      setGuidedStarted(false);
      setGuidedReady(false);
      setSessionId('');
      transitionTo('paste', 'forward');
    } else if (guidedReady) {
      transitionTo('review', 'forward');
    } else {
      setGuidedStarted(true);
      transitionTo('guided', 'forward');
    }
    void trackEvent(PROFILE_ONBOARDING_EVENTS.ROUTE_SELECTED, {
      route: source,
      presentation,
    });
  }, [
    guidedAvailable,
    guidedReady,
    isBusy,
    pastedDraft,
    presentation,
    source,
    trackEvent,
    transitionTo,
  ]);

  const handlePasteContinue = React.useCallback(() => {
    const learnerProfile = draft.trim();
    if (
      !learnerProfile ||
      countUnicodeCodePoints(learnerProfile) > maxLength ||
      isBusy
    ) {
      return;
    }
    setSource('pasted');
    setSessionId('');
    transitionTo('review', 'forward');
  }, [draft, isBusy, maxLength, transitionTo]);

  const handleBack = React.useCallback(() => {
    if (isBusy) {
      return;
    }
    if (route === 'review') {
      transitionTo(source === 'guided' ? 'guided' : 'paste', 'backward');
      return;
    }
    if (route === 'paste' || route === 'guided') {
      transitionTo('choice', 'backward');
    }
  }, [isBusy, route, source, transitionTo]);

  const handleSubmit = React.useCallback(async () => {
    const learnerProfile = draft.trim();
    if (
      !learnerProfile ||
      countUnicodeCodePoints(learnerProfile) > maxLength ||
      !source ||
      !lockAction('complete')
    ) {
      return;
    }
    try {
      const completed = await onComplete(
        learnerProfile,
        source,
        source === 'guided' && sessionId ? sessionId : undefined,
      );
      if (completed === false) {
        unlockAction();
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
    } catch {
      setRuntimeError(t('module.profileOnboarding.submitFailed'));
      unlockAction();
    }
  }, [
    draft,
    lockAction,
    maxLength,
    onComplete,
    pasteDraftStorageKey,
    presentation,
    sessionId,
    source,
    t,
    trackEvent,
    unlockAction,
  ]);

  const handleSkip = React.useCallback(async () => {
    if (!lockAction('skip')) {
      return;
    }
    try {
      const skipped = await onSkip(sessionId || undefined);
      if (skipped === false) {
        unlockAction();
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
    } catch {
      unlockAction();
    }
  }, [
    lockAction,
    onSkip,
    pasteDraftStorageKey,
    presentation,
    sessionId,
    trackEvent,
    unlockAction,
  ]);

  const profileLength = countUnicodeCodePoints(draft.trim());
  const combinedError = errorMessage || runtimeError;
  const isSaving = submitting || pendingAction === 'complete';
  const pageAnimationClass =
    transitionDirection === 'forward'
      ? 'motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-right-4 motion-safe:duration-200'
      : 'motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-left-4 motion-safe:duration-200';
  const hasValidDraft = Boolean(draft.trim()) && profileLength <= maxLength;
  const primaryVisible = route !== 'guided' || guidedReady;
  const primaryDisabled =
    isBusy ||
    (route === 'choice' &&
      (!source || (source === 'guided' && !guidedAvailable))) ||
    ((route === 'paste' || route === 'review') && !hasValidDraft) ||
    (route === 'guided' && !guidedReady);
  const primaryLabel =
    route === 'review'
      ? isSaving
        ? t('module.profileOnboarding.submitting')
        : t(
            sessionIntent === 'settings'
              ? 'module.profileOnboarding.settings.save'
              : 'module.profileOnboarding.complete',
          )
      : t('module.profileOnboarding.next');
  const secondaryLabel =
    pendingAction === 'skip'
      ? t('module.profileOnboarding.skipping')
      : sessionIntent === 'settings'
        ? t('module.profileOnboarding.settings.cancel')
        : t('module.profileOnboarding.skip');

  const handlePrimaryAction = () => {
    if (route === 'choice') {
      handleChoiceContinue();
      return;
    }
    if (route === 'paste') {
      handlePasteContinue();
      return;
    }
    if (route === 'guided') {
      if (guidedReady) {
        transitionTo('review', 'forward');
      }
      return;
    }
    void handleSubmit();
  };
  return (
    <Dialog open={open}>
      <DialogContent
        className={cn(
          'flex h-[calc(100dvh-16px)] max-h-none w-[calc(100vw-16px)] max-w-[calc(100vw-16px)] flex-col gap-0 overflow-hidden rounded-2xl border border-border/80 bg-background p-0 shadow-[0_24px_80px_rgba(15,23,42,0.24)] outline-none',
          'sm:max-w-[calc(100vw-32px)] sm:rounded-2xl md:h-[min(720px,calc(100dvh-48px))] md:w-[min(960px,calc(100vw-48px))] md:max-w-[960px]',
        )}
        showClose={false}
        onOpenAutoFocus={event => {
          event.preventDefault();
          routeHeadingRef.current?.focus();
        }}
        onEscapeKeyDown={event => event.preventDefault()}
        onInteractOutside={event => event.preventDefault()}
      >
        <div className='flex h-full min-h-0 min-w-0'>
          <aside className='hidden w-[232px] shrink-0 flex-col border-r border-border/70 bg-muted/25 px-6 py-7 [@media(min-width:768px)_and_(min-height:640px)]:flex'>
            <Sparkles
              className='h-8 w-8 text-primary'
              aria-hidden='true'
            />
            <div className='mt-5'>
              <p className='text-xl font-semibold leading-7 tracking-tight text-foreground'>
                {t('module.profileOnboarding.title')}
              </p>
              {isNonBlocking ? (
                <p className='mt-2 text-sm leading-6 text-muted-foreground'>
                  {t('module.profileOnboarding.upgradeDescription')}
                </p>
              ) : null}
            </div>

            <ol
              className={cn('space-y-2', isNonBlocking ? 'mt-12' : 'mt-8')}
              aria-label={t('module.profileOnboarding.title')}
            >
              {PROFILE_ONBOARDING_STEPS.map((step, index) => {
                const isCompleted = index < currentStepIndex;
                const isCurrent = index === currentStepIndex;
                return (
                  <li
                    key={step}
                    className='relative'
                    aria-current={isCurrent ? 'step' : undefined}
                  >
                    {index < PROFILE_ONBOARDING_STEP_COUNT - 1 ? (
                      <span
                        className={cn(
                          'absolute left-[15px] top-9 h-8 w-px bg-border',
                          index < currentStepIndex && 'bg-primary/45',
                        )}
                        aria-hidden='true'
                      />
                    ) : null}
                    <div
                      className={cn(
                        'flex min-h-12 items-center gap-3 rounded-xl px-2.5 py-2 text-sm font-medium text-muted-foreground',
                        isCurrent && 'bg-primary/[0.08] text-primary',
                        isCompleted && 'text-foreground',
                      )}
                    >
                      <span
                        className={cn(
                          'flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-background text-xs tabular-nums',
                          isCurrent &&
                            'border-primary bg-primary text-primary-foreground',
                          isCompleted &&
                            'border-primary bg-primary text-primary-foreground',
                        )}
                      >
                        {isCompleted ? (
                          <Check
                            className='h-4 w-4'
                            aria-hidden='true'
                          />
                        ) : (
                          index + 1
                        )}
                      </span>
                      <span>{stepLabels[index]}</span>
                    </div>
                  </li>
                );
              })}
            </ol>
          </aside>

          <main className='flex min-h-0 min-w-0 flex-1 flex-col'>
            <div className='shrink-0 border-b border-border/70 px-4 pb-3 pt-[max(12px,env(safe-area-inset-top))] [@media(max-height:480px)]:pb-2 [@media(max-height:480px)]:pt-2 [@media(min-width:768px)_and_(min-height:640px)]:hidden'>
              <div className='flex items-center justify-between gap-3'>
                <span className='truncate text-sm font-semibold text-foreground'>
                  {t('module.profileOnboarding.title')}
                </span>
                <span className='shrink-0 text-xs tabular-nums text-muted-foreground'>
                  {t('module.profileOnboarding.stepCounter', {
                    current: currentStepNumber,
                    total: PROFILE_ONBOARDING_STEP_COUNT,
                  })}
                </span>
              </div>
              <div
                className='mt-2.5 grid grid-cols-3 gap-1.5'
                aria-hidden='true'
              >
                {PROFILE_ONBOARDING_STEPS.map((step, index) => (
                  <span
                    key={step}
                    className={cn(
                      'h-1 rounded-full bg-muted',
                      index <= currentStepIndex && 'bg-primary',
                    )}
                  />
                ))}
              </div>
            </div>

            <header className='h-[164px] shrink-0 overflow-y-auto border-b border-border/70 [@media(max-height:480px)]:h-[112px] [@media(min-width:768px)_and_(min-height:640px)]:h-[144px]'>
              <div className='flex min-h-full flex-col justify-center px-5 py-5 md:px-8 md:py-6'>
                <DialogTitle
                  ref={routeHeadingRef}
                  tabIndex={-1}
                  className='text-xl leading-7 tracking-tight outline-none md:text-2xl md:leading-8'
                >
                  {pageTitle}
                </DialogTitle>
                <DialogDescription className='mt-2 max-w-[58ch] text-sm leading-6'>
                  {pageDescription}
                </DialogDescription>
              </div>
            </header>

            <div className='relative min-h-0 flex-1 overflow-hidden'>
              {route === 'choice' ? (
                <div
                  key='choice'
                  ref={pageScrollRef}
                  data-testid='profile-onboarding-body'
                  className={cn(
                    'absolute inset-0 overflow-y-auto overscroll-contain px-5 py-5 [scrollbar-gutter:stable] [-webkit-overflow-scrolling:touch] md:px-8 md:py-6',
                    pageAnimationClass,
                    'motion-reduce:animate-none motion-reduce:transform-none',
                  )}
                >
                  <section className='space-y-4'>
                    <div className='grid gap-3'>
                      <button
                        type='button'
                        aria-pressed={source === 'pasted'}
                        className={cn(
                          'group flex w-full items-center gap-3 rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/45 hover:bg-primary/[0.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 md:p-5',
                          source === 'pasted' &&
                            'border-primary bg-primary/[0.055] shadow-sm',
                        )}
                        disabled={isBusy}
                        onClick={() => {
                          setRuntimeError('');
                          sourceRef.current = 'pasted';
                          setSource('pasted');
                        }}
                      >
                        <span
                          className={cn(
                            'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-background',
                            source === 'pasted' &&
                              'border-primary bg-primary text-primary-foreground',
                          )}
                          aria-hidden='true'
                        >
                          {source === 'pasted' ? (
                            <Check className='h-4 w-4' />
                          ) : null}
                        </span>
                        <span className='flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary'>
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
                      </button>

                      <button
                        type='button'
                        aria-pressed={source === 'guided'}
                        className={cn(
                          'group flex w-full items-center gap-3 rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/45 hover:bg-primary/[0.035] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 md:p-5',
                          source === 'guided' &&
                            'border-primary bg-primary/[0.055] shadow-sm',
                        )}
                        disabled={isBusy || !guidedAvailable}
                        onClick={() => {
                          setRuntimeError('');
                          sourceRef.current = 'guided';
                          setSource('guided');
                        }}
                      >
                        <span
                          className={cn(
                            'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-background',
                            source === 'guided' &&
                              'border-primary bg-primary text-primary-foreground',
                          )}
                          aria-hidden='true'
                        >
                          {source === 'guided' ? (
                            <Check className='h-4 w-4' />
                          ) : null}
                        </span>
                        <span className='flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary'>
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
                              : t(
                                  'module.profileOnboarding.guided.unavailable',
                                )}
                          </span>
                        </span>
                      </button>
                    </div>

                    <details className='group rounded-xl border border-border/70 bg-muted/35 text-muted-foreground'>
                      <summary className='grid cursor-pointer list-none grid-cols-[auto_minmax(0,1fr)] items-start gap-x-2.5 gap-y-1 px-3.5 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:grid-cols-[auto_minmax(0,1fr)_auto] [&::-webkit-details-marker]:hidden'>
                        <ShieldCheck
                          className='mt-0.5 h-4 w-4 shrink-0 text-primary'
                          aria-hidden='true'
                        />
                        <span className='min-w-0 flex-1 text-xs leading-5'>
                          {t('module.profileOnboarding.privacySummary')}
                        </span>
                        <span className='col-start-2 flex shrink-0 items-center gap-1 text-xs font-medium text-primary sm:col-start-3 sm:row-start-1'>
                          {t('module.profileOnboarding.privacyDetailsLabel')}
                          <ChevronDown
                            className='h-3.5 w-3.5 transition-transform group-open:rotate-180'
                            aria-hidden='true'
                          />
                        </span>
                      </summary>
                      <p className='border-t border-border/60 px-3.5 py-3 text-xs leading-5'>
                        {t('module.profileOnboarding.privacyDetails')}
                      </p>
                    </details>
                    {combinedError ? (
                      <InlineError>{combinedError}</InlineError>
                    ) : null}
                  </section>
                </div>
              ) : null}

              {route === 'paste' ? (
                <div
                  key='paste'
                  ref={pageScrollRef}
                  data-testid='profile-onboarding-body'
                  className={cn(
                    'absolute inset-0 overflow-y-auto overscroll-contain px-5 py-5 scroll-pb-24 [scrollbar-gutter:stable] [-webkit-overflow-scrolling:touch] md:px-8 md:py-6',
                    pageAnimationClass,
                    'motion-reduce:animate-none motion-reduce:transform-none',
                  )}
                >
                  <section className='space-y-5'>
                    <div className='overflow-hidden rounded-xl border border-border bg-muted/25'>
                      <div className='flex flex-col gap-3 border-b border-border/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between'>
                        <p className='text-sm font-medium text-foreground'>
                          {t(
                            'module.profileOnboarding.externalAgent.promptLabel',
                          )}
                        </p>
                        <Button
                          type='button'
                          variant='outline'
                          size='sm'
                          className='min-w-[132px] bg-background sm:w-auto'
                          disabled={isBusy}
                          onClick={() => void handleCopyPrompt()}
                        >
                          {copyState === 'copied' ? (
                            <Check
                              className='h-4 w-4'
                              aria-hidden='true'
                            />
                          ) : (
                            <Copy
                              className='h-4 w-4'
                              aria-hidden='true'
                            />
                          )}
                          <span>
                            {copyState === 'copied'
                              ? t(
                                  'module.profileOnboarding.externalAgent.copied',
                                )
                              : t(
                                  'module.profileOnboarding.externalAgent.copy',
                                )}
                          </span>
                        </Button>
                      </div>
                      <div className='max-h-44 overflow-y-auto whitespace-pre-wrap px-4 py-3 text-sm leading-6 text-foreground'>
                        {externalAgentPrompt}
                      </div>
                    </div>
                    <ProfileDraftEditor
                      inputId='profile-onboarding-paste-draft'
                      variant='onboarding'
                      value={draft}
                      maxLength={maxLength}
                      disabled={isBusy}
                      label={t(
                        'module.profileOnboarding.externalAgent.resultLabel',
                      )}
                      placeholder={t(
                        'module.profileOnboarding.externalAgent.resultPlaceholder',
                      )}
                      onChange={handleDraftChange}
                    />
                    {combinedError ? (
                      <InlineError>{combinedError}</InlineError>
                    ) : null}
                  </section>
                </div>
              ) : null}

              {guidedStarted ? (
                <div
                  ref={route === 'guided' ? pageScrollRef : undefined}
                  data-testid={
                    route === 'guided' ? 'profile-onboarding-body' : undefined
                  }
                  className={cn(
                    route === 'guided'
                      ? 'absolute inset-0 overflow-hidden px-5 py-5 md:px-8 md:py-6'
                      : 'hidden',
                    route === 'guided' && pageAnimationClass,
                    'motion-reduce:animate-none motion-reduce:transform-none',
                  )}
                >
                  <section className='h-full min-h-0'>
                    <ProfileOnboardingConversation
                      createSession={createSession}
                      runSession={runSession}
                      disabled={isBusy}
                      errorMessage={combinedError}
                      onSessionStarted={setSessionId}
                      onDraftReady={(profileDraft, activeSessionId) => {
                        if (
                          sourceRef.current !== 'guided' ||
                          actionPendingRef.current
                        ) {
                          return;
                        }
                        setDraft(profileDraft);
                        setSessionId(activeSessionId);
                        setSource('guided');
                        setGuidedReady(true);
                        setRuntimeError('');
                        if (routeRef.current === 'guided') {
                          transitionTo('review', 'forward');
                        }
                      }}
                      onRetry={() => setRuntimeError('')}
                      onError={error => {
                        if (
                          sourceRef.current !== 'guided' ||
                          actionPendingRef.current
                        ) {
                          return;
                        }
                        void trackEvent(
                          PROFILE_ONBOARDING_EVENTS.RUNTIME_FAILED,
                          {
                            stage: 'guided',
                            presentation,
                          },
                        );
                        setRuntimeError(
                          error instanceof Error && error.message
                            ? error.message
                            : t('module.profileOnboarding.guided.streamError'),
                        );
                      }}
                    />
                  </section>
                </div>
              ) : null}

              {route === 'review' ? (
                <div
                  key='review'
                  ref={pageScrollRef}
                  data-testid='profile-onboarding-body'
                  className={cn(
                    'absolute inset-0 overflow-y-auto overscroll-contain px-5 py-5 scroll-pb-24 [scrollbar-gutter:stable] [-webkit-overflow-scrolling:touch] md:px-8 md:py-6',
                    pageAnimationClass,
                    'motion-reduce:animate-none motion-reduce:transform-none',
                  )}
                >
                  <section className='space-y-4'>
                    <ProfileDraftEditor
                      inputId='profile-onboarding-review-draft'
                      variant='onboarding'
                      value={draft}
                      maxLength={maxLength}
                      disabled={isBusy}
                      label={t('module.profileOnboarding.review.profileLabel')}
                      placeholder={t(
                        'module.profileOnboarding.review.profilePlaceholder',
                      )}
                      onChange={handleDraftChange}
                    />
                    {combinedError ? (
                      <InlineError>{combinedError}</InlineError>
                    ) : null}
                  </section>
                </div>
              ) : null}
            </div>

            <footer
              data-testid='profile-onboarding-footer'
              className='grid min-h-[76px] shrink-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 border-t border-border/70 bg-background px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-3 sm:px-4 md:h-[76px] md:gap-3 md:px-8 md:py-4 [@media(max-height:480px)]:h-[60px] [@media(max-height:480px)]:min-h-[60px] [@media(max-height:480px)]:px-4 [@media(max-height:480px)]:py-2'
            >
              <div
                data-testid='profile-onboarding-footer-back'
                className='flex min-w-0 justify-start'
              >
                <Button
                  type='button'
                  variant='ghost'
                  size='sm'
                  aria-hidden={route === 'choice' ? 'true' : undefined}
                  tabIndex={route === 'choice' ? -1 : undefined}
                  className={cn(
                    'h-11 min-w-[64px] px-1.5 sm:min-w-[76px] sm:px-2 md:h-10 md:min-w-[104px] md:px-4',
                    route === 'choice' && 'invisible pointer-events-none',
                  )}
                  disabled={isBusy || route === 'choice'}
                  onClick={handleBack}
                >
                  {t('module.profileOnboarding.back')}
                </Button>
              </div>

              <div
                data-testid='profile-onboarding-footer-secondary'
                className='flex min-w-0 justify-center'
              >
                <Button
                  type='button'
                  variant='ghost'
                  size='sm'
                  className='h-11 px-1.5 text-muted-foreground hover:text-foreground sm:px-2 md:h-10 md:min-w-[144px] md:border md:border-input md:bg-background md:px-4 md:shadow-sm'
                  disabled={isBusy}
                  onClick={() => void handleSkip()}
                >
                  {pendingAction === 'skip' ? (
                    <Loader2
                      className='h-4 w-4 animate-spin'
                      aria-hidden='true'
                    />
                  ) : null}
                  {secondaryLabel}
                </Button>
              </div>

              <div
                data-testid='profile-onboarding-footer-primary'
                className='flex min-w-0 justify-end'
              >
                <Button
                  type='button'
                  size='sm'
                  aria-label={primaryLabel}
                  aria-hidden={!primaryVisible ? 'true' : undefined}
                  tabIndex={!primaryVisible ? -1 : undefined}
                  className={cn(
                    'h-11 min-w-[82px] px-2 sm:min-w-[88px] sm:px-3 md:h-10 md:min-w-[144px] md:px-5',
                    !primaryVisible && 'invisible pointer-events-none',
                  )}
                  disabled={primaryDisabled || !primaryVisible}
                  onClick={handlePrimaryAction}
                >
                  {route === 'review' && isSaving ? (
                    <Loader2
                      className='h-4 w-4 animate-spin'
                      aria-hidden='true'
                    />
                  ) : null}
                  {route === 'review' ? (
                    <>
                      <span className='md:hidden'>
                        {isSaving
                          ? t('module.profileOnboarding.submitting')
                          : t('module.profileOnboarding.completeCompact')}
                      </span>
                      <span className='hidden md:inline'>{primaryLabel}</span>
                    </>
                  ) : (
                    primaryLabel
                  )}
                </Button>
              </div>
            </footer>
          </main>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function InlineError({ children }: { children: React.ReactNode }) {
  return (
    <div
      role='alert'
      className='rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm leading-5 text-destructive'
    >
      {children}
    </div>
  );
}

export function ProfileDraftEditor({
  inputId = 'profile-onboarding-draft',
  variant = 'default',
  value,
  maxLength,
  disabled,
  label,
  placeholder,
  onChange,
}: {
  inputId?: string;
  variant?: 'default' | 'onboarding';
  value: string;
  maxLength: number;
  disabled: boolean;
  label?: string;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const length = countUnicodeCodePoints(value.trim());
  const isOnboarding = variant === 'onboarding';
  const characterCountText = isOnboarding
    ? length > maxLength
      ? t('module.profileOnboarding.onboardingCharacterCountOverLimit', {
          count: length,
          max: maxLength,
        })
      : t('module.profileOnboarding.onboardingCharacterCount', {
          count: length,
          max: maxLength,
        })
    : length > maxLength
      ? t('module.profileOnboarding.characterCountOverLimit', {
          count: length,
          max: maxLength,
        })
      : t('module.profileOnboarding.characterCount', {
          count: length,
          max: maxLength,
        });
  return (
    <div className='space-y-2'>
      <label
        htmlFor={inputId}
        className='text-sm font-medium'
      >
        {label ?? t('module.profileOnboarding.profileLabel')}
      </label>
      <Textarea
        id={inputId}
        value={value}
        {...(isOnboarding ? { rows: 8 } : { minRows: 8, maxRows: 14 })}
        className={cn(
          isOnboarding && 'h-[184px] resize-none overflow-y-auto md:h-[220px]',
        )}
        disabled={disabled}
        placeholder={
          placeholder ?? t('module.profileOnboarding.profilePlaceholder')
        }
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
        {characterCountText}
      </div>
    </div>
  );
}
