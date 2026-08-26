'use client';

import React from 'react';
import { MarkdownFlow } from 'markdown-flow-ui/renderer';
import { Loader2, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { resolveMarkdownFlowLocale } from '@/lib/markdown-flow-locale';
import { cn } from '@/lib/utils';
import type {
  ProfileOnboardingAssistantAnswers,
  ProfileOnboardingRunSession,
  ProfileOnboardingSessionInfo,
} from './profileOnboardingConversationModel';
import { ProfileAssistantAnswersView } from './ProfileAssistantAnswersView';
import { useProfileOnboardingSession } from './useProfileOnboardingSession';

// ContentRender recreates its custom interaction component on every render.
// Isolate it from sibling view/copy/paste state to preserve unsent input.
const StableMarkdownFlow = React.memo(MarkdownFlow);

export {
  isProfileOnboardingSubmissionWithinLimits,
  resolveProfileDraftFromRunEvent,
  resolveProfileNicknameFromRunEvent,
} from './profileOnboardingConversationModel';
export type {
  ProfileOnboardingRunSession,
  ProfileOnboardingSessionInfo,
} from './profileOnboardingConversationModel';

export type ProfileOnboardingConversationProps = {
  createSession: () => Promise<ProfileOnboardingSessionInfo>;
  runSession: ProfileOnboardingRunSession;
  assistantAnswers?: ProfileOnboardingAssistantAnswers;
  assistantDraft?: string;
  onAssistantDraftChange?: (draft: string) => void;
  onAssistantDraftReady?: (
    draft: string,
    sessionId: string,
    nickname?: string,
  ) => void;
  disabled?: boolean;
  errorMessage?: string;
  onSessionStarted?: (sessionId: string) => void;
  onRunInFlightChange?: (runInFlight: boolean) => void;
  onDraftReady: (
    profileDraft: string,
    sessionId: string,
    nickname?: string,
  ) => void;
  onError: (error: unknown) => void;
  onSessionCreateRejected?: (error: unknown) => void;
  onRetry?: () => void;
};

export default function ProfileOnboardingConversation({
  createSession,
  runSession,
  assistantAnswers,
  assistantDraft,
  onAssistantDraftChange,
  onAssistantDraftReady,
  disabled = false,
  errorMessage = '',
  onSessionStarted,
  onRunInFlightChange,
  onDraftReady,
  onError,
  onSessionCreateRejected,
  onRetry,
}: ProfileOnboardingConversationProps) {
  const { t, i18n } = useTranslation();
  const [assistantVisible, setAssistantVisible] = React.useState(false);
  const assistantView =
    assistantAnswers &&
    typeof assistantDraft === 'string' &&
    onAssistantDraftChange
      ? { draft: assistantDraft, onChange: onAssistantDraftChange }
      : null;
  const showAssistant = assistantVisible && assistantView !== null;
  const latestItemRef = React.useRef<HTMLDivElement>(null);
  const assistantHeadingRef = React.useRef<HTMLHeadingElement>(null);
  const assistantEntryRef = React.useRef<HTMLButtonElement>(null);
  const previousAssistantVisibleRef = React.useRef(false);

  React.useEffect(() => {
    if (previousAssistantVisibleRef.current === showAssistant) return;
    previousAssistantVisibleRef.current = showAssistant;
    // Start with the instructions and copy step, not the paste textarea.
    const target = showAssistant ? assistantHeadingRef : assistantEntryRef;
    target.current?.focus({ preventScroll: true });
  }, [showAssistant]);
  const {
    items,
    status,
    assistantPrompt,
    submitAssistantAnswers,
    resumeQuestions,
    uncertainRequest,
    loading,
    runInFlight,
    assistantProcessing,
    retryAvailable,
    submissionLimitError,
    send,
    retry,
  } = useProfileOnboardingSession({
    createSession,
    runSession,
    assistantAnswers,
    onAssistantDraftReady,
    disabled,
    messages: {
      retryableError: t('module.profileOnboarding.guided.retryableError'),
      streamError: t('module.profileOnboarding.guided.streamError'),
      missingDraft: t('module.profileOnboarding.guided.missingDraft'),
      assistantError: t('module.profileOnboarding.assistant.error'),
    },
    onSessionStarted,
    onRunInFlightChange,
    onDraftReady,
    onError,
    onSessionCreateRejected,
    onRetry,
  });

  React.useEffect(() => {
    if (!items.length) {
      return;
    }
    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    latestItemRef.current?.scrollIntoView?.({
      block: 'nearest',
      behavior: prefersReducedMotion ? 'auto' : 'smooth',
    });
  }, [items.length]);

  const locale = resolveMarkdownFlowLocale(
    i18n.resolvedLanguage ?? i18n.language,
  );
  const visibleErrorMessage = submissionLimitError
    ? t('module.profileOnboarding.guided.inputLimitError')
    : errorMessage;
  const latestItem = items[items.length - 1];
  const streamingNonInteraction = Boolean(
    runInFlight && latestItem && !latestItem.interaction,
  );
  const hasVisibleStatus = Boolean(
    visibleErrorMessage || loading || streamingNonInteraction || retryAvailable,
  );

  // Hidden questions cannot be edited; keep their renderer props unchanged
  // while an import runs or fails. The session hook also rejects manual sends.
  const questionReadonly =
    !showAssistant && (disabled || runInFlight || status !== 'awaiting_input');
  const contentList = React.useMemo(
    () =>
      items.map(item => ({
        content: item.content,
        isFinished: item.finished,
        readonly: questionReadonly || item.finished || !item.interaction,
        userInput: item.userInput,
      })),
    [items, questionReadonly],
  );

  return (
    <div
      data-testid='profile-onboarding-conversation'
      className='flex h-full min-h-0 flex-col gap-3'
      aria-busy={disabled || assistantProcessing}
    >
      {!showAssistant &&
      assistantView &&
      assistantPrompt &&
      status !== 'completed' &&
      status !== 'fatal_error' ? (
        <div className='flex shrink-0 flex-col gap-3 rounded-xl border border-primary/25 bg-primary/5 p-3 sm:flex-row sm:items-center sm:justify-between'>
          <p className='text-sm leading-5 text-foreground'>
            {t('module.profileOnboarding.assistant.entryHint')}
          </p>
          <Button
            ref={assistantEntryRef}
            type='button'
            className='h-auto min-h-10 shrink-0 whitespace-normal py-2 text-start'
            disabled={disabled}
            onClick={() => setAssistantVisible(true)}
          >
            <Sparkles
              className='size-4 shrink-0'
              aria-hidden='true'
            />
            {t('module.profileOnboarding.assistant.entry')}
          </Button>
        </div>
      ) : null}
      <div
        hidden={showAssistant}
        aria-busy={loading || (runInFlight && !assistantProcessing)}
        className={cn(
          'profile-onboarding-markdownflow min-h-0 flex-1 overflow-y-auto overscroll-contain pe-1 [scrollbar-gutter:stable]',
          showAssistant && 'hidden',
        )}
      >
        <StableMarkdownFlow
          locale={locale}
          initialContentList={contentList}
          onSend={send}
        />
        <div
          ref={latestItemRef}
          aria-hidden='true'
        />
      </div>
      {showAssistant && assistantView ? (
        <ProfileAssistantAnswersView
          headingRef={assistantHeadingRef}
          prompt={assistantPrompt}
          value={assistantView.draft}
          disabled={disabled || assistantProcessing}
          waitingForQuestion={runInFlight && !assistantProcessing}
          processingDisabled={
            !['awaiting_input', 'retryable_error'].includes(status)
          }
          unresolved={uncertainRequest}
          onChange={assistantView.onChange}
          onSubmit={submitAssistantAnswers}
          onBack={() => {
            if (resumeQuestions()) setAssistantVisible(false);
          }}
        />
      ) : null}
      {hasVisibleStatus ? (
        <div
          className={cn(
            'flex min-h-9 shrink-0 items-center gap-2 text-sm text-muted-foreground',
            !items.length && 'order-first',
          )}
          role={visibleErrorMessage ? 'alert' : 'status'}
          aria-live={visibleErrorMessage ? 'assertive' : 'polite'}
        >
          {visibleErrorMessage ? (
            <span className='min-w-0 flex-1 text-destructive'>
              {visibleErrorMessage}
            </span>
          ) : loading || streamingNonInteraction ? (
            <>
              <Loader2
                className='h-4 w-4 animate-spin motion-reduce:animate-none'
                aria-hidden='true'
              />
              {items.length
                ? t('module.profileOnboarding.guided.thinking')
                : t('module.profileOnboarding.guided.starting')}
            </>
          ) : null}
          {retryAvailable ? (
            <Button
              type='button'
              size='sm'
              variant='outline'
              disabled={disabled}
              onClick={retry}
            >
              {t('module.profileOnboarding.guided.retry')}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
