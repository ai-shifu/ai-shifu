'use client';

import React from 'react';
import { Check, Loader2, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  createProfileOnboardingSession,
  runProfileOnboardingSession,
  type ProfileOnboardingPresentation,
  type ProfileOnboardingSessionIntent,
} from '@/c-api/user';
import { useTracking } from '@/c-common/hooks/useTracking';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/Dialog';
import { cn } from '@/lib/utils';
import {
  countUnicodeCodePoints,
  ProfileDraftEditor,
} from './ProfileDraftEditor';
import ProfileOnboardingConversation from './ProfileOnboardingConversation';
import { PROFILE_ONBOARDING_EVENTS } from './events';

type ProfileOnboardingRoute = 'guided' | 'review';
type ProfileTriggerSource = 'guided' | 'settings';
type TransitionDirection = 'forward' | 'backward';
type PendingAction = 'complete' | 'skip';

const PROFILE_ONBOARDING_STEPS = ['collect', 'review'] as const;
const PROFILE_ONBOARDING_STEP_COUNT = PROFILE_ONBOARDING_STEPS.length;

export type ProfileOnboardingModalProps = {
  open: boolean;
  presentation?: ProfileOnboardingPresentation;
  sessionIntent?: ProfileOnboardingSessionIntent;
  guidedAvailable?: boolean;
  maxLength?: number;
  errorMessage?: string;
  submitting?: boolean;
  onComplete: (
    learnerProfile: string,
    source: ProfileTriggerSource,
    sessionId?: string,
  ) => void | boolean | Promise<void | boolean>;
  onSkip: (sessionId?: string) => void | boolean | Promise<void | boolean>;
};

export default function ProfileOnboardingModal({
  open,
  presentation = 'blocking',
  sessionIntent = 'onboarding',
  guidedAvailable = true,
  maxLength = 1000,
  errorMessage = '',
  submitting = false,
  onComplete,
  onSkip,
}: ProfileOnboardingModalProps) {
  const { t, i18n } = useTranslation();
  const { trackEvent } = useTracking();
  const [route, setRoute] = React.useState<ProfileOnboardingRoute>('guided');
  const [transitionDirection, setTransitionDirection] =
    React.useState<TransitionDirection>('forward');
  const [draft, setDraft] = React.useState('');
  const [sessionId, setSessionId] = React.useState('');
  const [guidedReady, setGuidedReady] = React.useState(false);
  const [runtimeError, setRuntimeError] = React.useState('');
  const [pendingAction, setPendingAction] =
    React.useState<PendingAction | null>(null);
  const shownRef = React.useRef(false);
  const shownAtRef = React.useRef<number | null>(null);
  const routeHeadingRef = React.useRef<HTMLHeadingElement>(null);
  const pageScrollRef = React.useRef<HTMLDivElement>(null);
  const actionPendingRef = React.useRef(false);
  const routeRef = React.useRef(route);
  const presentationRef = React.useRef(presentation);
  const trackEventRef = React.useRef(trackEvent);
  routeRef.current = route;
  presentationRef.current = presentation;
  trackEventRef.current = trackEvent;

  const isBusy = submitting || pendingAction !== null;
  const currentStepIndex = route === 'guided' ? 0 : 1;
  const currentStepNumber = currentStepIndex + 1;
  const pageTitle = t(
    route === 'guided'
      ? 'module.profileOnboarding.guided.title'
      : 'module.profileOnboarding.review.title',
  );
  const pageDescription = t(
    route === 'guided'
      ? 'module.profileOnboarding.guided.description'
      : 'module.profileOnboarding.review.description',
  );
  const stepLabels = [
    t('module.profileOnboarding.steps.collect'),
    t('module.profileOnboarding.steps.review'),
  ];

  React.useEffect(() => {
    if (!open) {
      shownRef.current = false;
      shownAtRef.current = null;
      setRoute('guided');
      setTransitionDirection('forward');
      setDraft('');
      setSessionId('');
      setGuidedReady(false);
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
    setRoute('guided');
    setTransitionDirection('forward');
    setDraft('');
    setSessionId('');
    setGuidedReady(false);
    setRuntimeError('');
    actionPendingRef.current = false;
    setPendingAction(null);
  }, [open]);

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

  const handleSubmit = React.useCallback(async () => {
    const learnerProfile = draft.trim();
    if (
      !learnerProfile ||
      countUnicodeCodePoints(learnerProfile) > maxLength ||
      !lockAction('complete')
    ) {
      return;
    }
    try {
      const completed = await onComplete(
        learnerProfile,
        sessionIntent === 'settings' ? 'settings' : 'guided',
        sessionId || undefined,
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
        source: sessionIntent === 'settings' ? 'settings' : 'guided',
        presentation,
        duration_ms: durationMs,
      });
    } catch {
      setRuntimeError(t('module.profileOnboarding.submitFailed'));
      unlockAction();
    }
  }, [
    draft,
    lockAction,
    maxLength,
    onComplete,
    presentation,
    sessionId,
    sessionIntent,
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
    } catch {
      unlockAction();
    }
  }, [lockAction, onSkip, presentation, sessionId, trackEvent, unlockAction]);

  const profileLength = countUnicodeCodePoints(draft.trim());
  const hasValidDraft = Boolean(draft.trim()) && profileLength <= maxLength;
  const combinedError = errorMessage || runtimeError;
  const isSaving = submitting || pendingAction === 'complete';
  const primaryVisible = route === 'review' || guidedReady;
  const pageAnimationClass =
    transitionDirection === 'forward'
      ? 'motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-right-4 motion-safe:duration-200'
      : 'motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-left-4 motion-safe:duration-200';
  const primaryLabel =
    route === 'guided'
      ? t('module.profileOnboarding.next')
      : isSaving
        ? t('module.profileOnboarding.submitting')
        : t(
            sessionIntent === 'settings'
              ? 'module.profileOnboarding.settings.save'
              : 'module.profileOnboarding.complete',
          );
  const skipLabel =
    pendingAction === 'skip'
      ? t('module.profileOnboarding.skipping')
      : t('module.profileOnboarding.skip');

  return (
    <Dialog open={open && guidedAvailable}>
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
            </div>
            <ol
              className='mt-8 space-y-2'
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
                          (isCurrent || isCompleted) &&
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
                className='mt-2.5 grid grid-cols-2 gap-1.5'
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

            <header className='relative h-[164px] shrink-0 overflow-y-auto border-b border-border/70 [@media(max-height:480px)]:h-[112px] [@media(min-width:768px)_and_(min-height:640px)]:h-[144px]'>
              <div className='flex min-h-full flex-col justify-center py-5 pl-5 pr-24 md:py-6 md:pl-8 md:pr-32'>
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
              <Button
                data-testid='profile-onboarding-defer-action'
                type='button'
                variant='ghost'
                size='sm'
                className='absolute right-3 top-3 h-9 px-2 text-xs font-normal text-muted-foreground/60 hover:bg-transparent hover:text-muted-foreground md:right-6 md:top-5'
                disabled={isBusy}
                onClick={() => void handleSkip()}
              >
                {pendingAction === 'skip' ? (
                  <Loader2
                    className='h-3.5 w-3.5 animate-spin'
                    aria-hidden='true'
                  />
                ) : null}
                {skipLabel}
              </Button>
            </header>

            <div className='relative min-h-0 flex-1 overflow-hidden'>
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
                      if (actionPendingRef.current) {
                        return;
                      }
                      setDraft(profileDraft);
                      setSessionId(activeSessionId);
                      setGuidedReady(true);
                      setRuntimeError('');
                      if (routeRef.current === 'guided') {
                        transitionTo('review', 'forward');
                      }
                    }}
                    onRetry={() => setRuntimeError('')}
                    onError={error => {
                      if (actionPendingRef.current) {
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
                  <section className='space-y-4 [&_textarea]:h-[184px] [&_textarea]:resize-none [&_textarea]:overflow-y-auto md:[&_textarea]:h-[220px]'>
                    <ProfileDraftEditor
                      inputId='profile-onboarding-review-draft'
                      value={draft}
                      maxLength={maxLength}
                      disabled={isBusy}
                      label={t('module.profileOnboarding.review.profileLabel')}
                      placeholder={t(
                        'module.profileOnboarding.review.profilePlaceholder',
                      )}
                      onChange={setDraft}
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
              className='grid min-h-[76px] shrink-0 grid-cols-2 items-center gap-2 border-t border-border/70 bg-background px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-3 sm:px-4 md:h-[76px] md:gap-3 md:px-8 md:py-4 [@media(max-height:480px)]:h-[60px] [@media(max-height:480px)]:min-h-[60px] [@media(max-height:480px)]:px-4 [@media(max-height:480px)]:py-2'
            >
              <div
                data-testid='profile-onboarding-footer-back'
                className='flex min-w-0 justify-start'
              >
                <Button
                  type='button'
                  variant='ghost'
                  size='sm'
                  aria-hidden={route === 'guided' ? 'true' : undefined}
                  tabIndex={route === 'guided' ? -1 : undefined}
                  className={cn(
                    'h-11 min-w-[64px] px-1.5 sm:min-w-[76px] sm:px-2 md:h-10 md:min-w-[104px] md:px-4',
                    route === 'guided' && 'invisible pointer-events-none',
                  )}
                  disabled={isBusy || route === 'guided'}
                  onClick={() => transitionTo('guided', 'backward')}
                >
                  {t('module.profileOnboarding.back')}
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
                  disabled={
                    isBusy ||
                    !primaryVisible ||
                    (route === 'review' && !hasValidDraft)
                  }
                  onClick={() => {
                    if (route === 'guided') {
                      transitionTo('review', 'forward');
                      return;
                    }
                    void handleSubmit();
                  }}
                >
                  {route === 'review' && isSaving ? (
                    <Loader2
                      className='h-4 w-4 animate-spin'
                      aria-hidden='true'
                    />
                  ) : null}
                  {route === 'guided' ? (
                    primaryLabel
                  ) : (
                    <>
                      <span className='md:hidden'>
                        {isSaving
                          ? t('module.profileOnboarding.submitting')
                          : t('module.profileOnboarding.completeCompact')}
                      </span>
                      <span className='hidden md:inline'>{primaryLabel}</span>
                    </>
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
