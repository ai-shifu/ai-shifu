'use client';

import React from 'react';
import { MarkdownFlow } from 'markdown-flow-ui/renderer';
import { ScrollToBottomControl } from 'markdown-flow-ui/scroll';
import { Sparkles } from 'lucide-react';
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
  const questionViewportRef = React.useRef<HTMLDivElement>(null);
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
    assistantAvailable,
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

  const locale = resolveMarkdownFlowLocale(
    i18n.resolvedLanguage ?? i18n.language,
  );
  const visibleErrorMessage = submissionLimitError
    ? t('module.profileOnboarding.guided.inputLimitError')
    : errorMessage;
  const hasVisibleStatus = Boolean(visibleErrorMessage || retryAvailable);
  const canUseAssistant = Boolean(
    assistantView && assistantPrompt && assistantAvailable,
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
      <div
        hidden={showAssistant}
        className={cn('relative min-h-0 flex-1', showAssistant && 'hidden')}
      >
        <div
          ref={questionViewportRef}
          aria-busy={loading || (runInFlight && !assistantProcessing)}
          className={cn(
            'profile-onboarding-markdownflow h-full min-h-0 overflow-y-auto overscroll-contain pe-1 [scrollbar-gutter:stable]',
            canUseAssistant && 'sm:scroll-pb-20 sm:pb-20',
          )}
        >
          <StableMarkdownFlow
            locale={locale}
            initialContentList={contentList}
            onSend={send}
          />
        </div>
        <ScrollToBottomControl
          viewportRef={questionViewportRef}
          scrollTarget={questionViewportRef}
          autoScrollOnInit
          contentVersion={items.length}
          followNewContent={false}
          ariaLabel={t('common.core.scrollToBottom')}
          placement='bottom-center'
          position='absolute'
          bottomOffset={20}
          zIndex={10}
        />
        {!showAssistant && canUseAssistant ? (
          <Button
            ref={assistantEntryRef}
            type='button'
            className='absolute bottom-3 right-3 z-10 hidden h-auto min-h-10 max-w-[calc(50%-2.75rem)] whitespace-normal rounded-full px-4 py-2 text-start shadow-lg sm:inline-flex'
            disabled={disabled}
            onClick={() => setAssistantVisible(true)}
          >
            <Sparkles
              className='size-4 shrink-0'
              aria-hidden='true'
            />
            {t('module.profileOnboarding.assistant.entry')}
          </Button>
        ) : null}
      </div>
      {showAssistant && assistantView ? (
        <ProfileAssistantAnswersView
          headingRef={assistantHeadingRef}
          prompt={assistantPrompt}
          value={assistantView.draft}
          disabled={disabled || assistantProcessing}
          processingDisabled={!assistantAvailable}
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
