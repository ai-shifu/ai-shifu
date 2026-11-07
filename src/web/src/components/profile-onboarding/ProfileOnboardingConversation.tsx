'use client';

import React from 'react';
import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { ScrollToBottomControl } from 'markdown-flow-ui/scroll';
import { Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ElementType } from '@/api/learning';
import ContentBlock from '@/components/chat/ContentBlock';
import LoadingBar from '@/components/chat/LoadingBar';
import StreamingLoadingDotsBar from '@/components/chat/StreamingLoadingDotsBar';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  buildVisibleReadModeItems,
  isReadModeTextContentItemReady,
  shouldEnableReadModeTypewriter,
  syncReadModeTypewriterCache,
  type ReadModeTypewriterCache,
} from '@/lib/read-mode-typewriter-gate';
import { cn } from '@/lib/utils';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import type {
  ProfileOnboardingAssistantAnswers,
  ProfileOnboardingRunSession,
  ProfileOnboardingSessionInfo,
} from './profile-onboarding-conversation-model';
import { ProfileAssistantAnswersView } from './ProfileAssistantAnswersView';
import { useProfileOnboardingSession } from './use-profile-onboarding-session';
import type {
  ProfileAssistantFailureCategory,
  ProfileCollectionRoute,
} from './profile-onboarding-analytics';

const EMPTY_REWINDABLE_IDS: ReadonlySet<string> = new Set();

export {
  isProfileOnboardingSubmissionWithinLimits,
  resolveProfileDraftFromRunEvent,
  resolveProfileNicknameFromRunEvent,
} from './profile-onboarding-conversation-model';
export type {
  ProfileOnboardingRunSession,
  ProfileOnboardingSessionInfo,
} from './profile-onboarding-conversation-model';

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
  onRewindAccepted?: () => void;
  onRewindRejected?: (error: unknown) => void;
  onRewindAnalytics?: (
    outcome: 'attempt' | 'success' | 'failed' | 'cancelled',
  ) => void;
  questionScrollFooter?: React.ReactNode;
  onCollectionRouteChosen?: (route: ProfileCollectionRoute) => void;
  onPlaceholderAccepted?: () => void;
  onAssistantOpened?: () => void;
  assistantAnalyticsScope?: string;
  onAssistantPromptCopied?: (originScope: string) => void;
  onAssistantAttempt?: () => void;
  onAssistantResult?: (
    outcome: 'success' | 'failed',
    failureCategory?: ProfileAssistantFailureCategory,
  ) => void;
};

type PendingProfileDraft = {
  profileDraft: string;
  sessionId: string;
  nickname?: string;
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
  onRewindAccepted,
  onRewindRejected,
  onRewindAnalytics,
  questionScrollFooter,
  onCollectionRouteChosen,
  onPlaceholderAccepted,
  onAssistantOpened,
  assistantAnalyticsScope,
  onAssistantPromptCopied,
  onAssistantAttempt,
  onAssistantResult,
}: ProfileOnboardingConversationProps) {
  const { t } = useTranslation();
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
  const [isDocumentVisible, setIsDocumentVisible] = React.useState(
    () =>
      typeof document === 'undefined' || document.visibilityState !== 'hidden',
  );
  const [typewriterCache, setTypewriterCache] =
    React.useState<ReadModeTypewriterCache>({});
  const [pendingProfileDraft, setPendingProfileDraft] =
    React.useState<PendingProfileDraft | null>(null);
  const holdProfileDraft = React.useCallback(
    (profileDraft: string, sessionId: string, nickname?: string) => {
      setPendingProfileDraft({ profileDraft, sessionId, nickname });
    },
    [],
  );
  const invalidateProfileDraft = React.useCallback(() => {
    setPendingProfileDraft(null);
    onRewindAccepted?.();
  }, [onRewindAccepted]);

  React.useEffect(() => {
    const syncVisibility = () =>
      setIsDocumentVisible(document.visibilityState !== 'hidden');
    syncVisibility();
    document.addEventListener('visibilitychange', syncVisibility);
    return () =>
      document.removeEventListener('visibilitychange', syncVisibility);
  }, []);

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
    summaryProcessing,
    assistantProcessing,
    retryAvailable,
    submissionLimitError,
    activeInteractionId,
    rewindableInteractionIds = EMPTY_REWINDABLE_IDS,
    reGenerateConfirm,
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
    onDraftReady: holdProfileDraft,
    onError,
    onSessionCreateRejected,
    onRetry,
    onRewindAccepted: invalidateProfileDraft,
    onRewindRejected,
    onRewindAnalytics,
    onAssistantAttempt,
    onAssistantResult,
  });
  const itemsRef = React.useRef(items);
  itemsRef.current = items;

  const visibleErrorMessage = submissionLimitError
    ? t('module.profileOnboarding.guided.inputLimitError')
    : errorMessage;
  const hasVisibleStatus = Boolean(visibleErrorMessage || retryAvailable);
  const canUseAssistant = Boolean(
    assistantView && assistantPrompt && assistantAvailable,
  );
  const reportRouteChosen = React.useCallback(
    (route: ProfileCollectionRoute) => {
      try {
        onCollectionRouteChosen?.(route);
      } catch {}
    },
    [onCollectionRouteChosen],
  );

  // Hidden questions cannot be edited; keep their renderer props unchanged
  // while an import runs or fails. The session hook also rejects manual sends.
  const questionReadonly =
    !showAssistant && (disabled || runInFlight || status !== 'awaiting_input');
  const rewindReadonly =
    !showAssistant &&
    (disabled ||
      runInFlight ||
      (status !== 'awaiting_input' && status !== 'completed'));
  const readModeItems = React.useMemo<ChatContentItem[]>(
    () =>
      items
        .filter(
          item =>
            !item.interaction ||
            item.finished ||
            !activeInteractionId ||
            (item.interactionId || item.elementBid) === activeInteractionId,
        )
        .map(item => ({
          element_bid: item.elementBid,
          element_type: item.elementType as ElementType,
          type: item.interaction
            ? ChatContentItemType.INTERACTION
            : ChatContentItemType.CONTENT,
          content: item.content,
          is_final: item.isFinal ?? true,
          shouldUseTypewriter: !item.interaction && item.elementType === 'text',
          readonly: !item.interaction
            ? true
            : item.finished
              ? rewindReadonly ||
                !item.interactionId ||
                !rewindableInteractionIds.has(item.interactionId)
              : questionReadonly ||
                Boolean(
                  activeInteractionId &&
                  (item.interactionId || item.elementBid) !==
                    activeInteractionId,
                ),
          user_input: item.userInput,
        })),
    [
      activeInteractionId,
      items,
      questionReadonly,
      rewindReadonly,
      rewindableInteractionIds,
    ],
  );

  React.useEffect(() => {
    setTypewriterCache(previousCache =>
      syncReadModeTypewriterCache(readModeItems, previousCache, {
        suppressTypewriter: !isDocumentVisible,
      }),
    );
  }, [isDocumentVisible, readModeItems]);

  React.useEffect(() => {
    if (!pendingProfileDraft || runInFlight) return;
    const hasUnfinishedGuidance =
      isDocumentVisible &&
      readModeItems.some(
        item => !isReadModeTextContentItemReady(item, typewriterCache),
      );
    if (hasUnfinishedGuidance) return;
    setPendingProfileDraft(null);
    if (pendingProfileDraft.nickname) {
      onDraftReady(
        pendingProfileDraft.profileDraft,
        pendingProfileDraft.sessionId,
        pendingProfileDraft.nickname,
      );
    } else {
      onDraftReady(
        pendingProfileDraft.profileDraft,
        pendingProfileDraft.sessionId,
      );
    }
  }, [
    isDocumentVisible,
    onDraftReady,
    pendingProfileDraft,
    readModeItems,
    runInFlight,
    typewriterCache,
  ]);

  const visibleContentList = React.useMemo(
    () =>
      isDocumentVisible
        ? buildVisibleReadModeItems(readModeItems, typewriterCache)
        : readModeItems,
    [isDocumentVisible, readModeItems, typewriterCache],
  );

  const handleTypeFinished = React.useCallback(
    (elementBid: string, content: string) => {
      setTypewriterCache(previousCache => {
        const entry = previousCache[elementBid];
        if (entry?.content === content && entry.isFinished)
          return previousCache;
        return {
          ...previousCache,
          [elementBid]: { ...entry, content, isFinished: true },
        };
      });
    },
    [],
  );
  const handleSend = React.useCallback(
    (content: OnSendContentParams, elementBid: string) => {
      const item = itemsRef.current.find(
        candidate =>
          candidate.elementBid === elementBid && candidate.interaction,
      );
      if (item) send(content, item.interactionId || item.elementBid);
    },
    [send],
  );
  const showQuestionProgress = runInFlight && !assistantProcessing;

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
            'profile-onboarding-markdownflow h-full min-h-0 overflow-y-auto overscroll-contain py-6 pe-1 [scrollbar-gutter:stable] max-sm:[&_button]:min-h-11 max-sm:[&_button]:min-w-11 max-sm:[&_input]:min-h-11 max-sm:[&_input]:text-base max-sm:[&_select]:min-h-11 max-sm:[&_select]:text-base max-sm:[&_textarea]:text-base sm:any-pointer-coarse:[&_button]:min-h-11 sm:any-pointer-coarse:[&_button]:min-w-11 sm:any-pointer-coarse:[&_input]:min-h-11 sm:any-pointer-coarse:[&_input]:text-base sm:any-pointer-coarse:[&_select]:min-h-11 sm:any-pointer-coarse:[&_select]:text-base sm:any-pointer-coarse:[&_textarea]:text-base',
            canUseAssistant && 'sm:scroll-pb-20 sm:pb-20',
          )}
        >
          <div className='markdown-flow'>
            {visibleContentList.map(item => (
              <ContentBlock
                key={item.element_bid}
                item={item}
                blockBid={item.element_bid}
                mobileStyle={false}
                showAudioAction={false}
                onPlaceholderAccepted={onPlaceholderAccepted}
                onSend={handleSend}
                enableStreamingTypewriter={
                  isDocumentVisible &&
                  shouldEnableReadModeTypewriter(
                    item,
                    typewriterCache[item.element_bid],
                  )
                }
                onTypeFinished={
                  item.shouldUseTypewriter ? handleTypeFinished : undefined
                }
              />
            ))}
            {summaryProcessing ? (
              <div
                className='mt-4 flex items-center gap-2 text-sm text-muted-foreground'
                role='status'
              >
                <StreamingLoadingDotsBar />
                {t('module.profileOnboarding.guided.summarizing')}
              </div>
            ) : showQuestionProgress ? (
              <div
                className='mt-4'
                role='status'
              >
                <StreamingLoadingDotsBar />
                <span className='sr-only'>{t('module.chat.thinking')}</span>
              </div>
            ) : loading && !assistantProcessing ? (
              <div role='status'>
                <LoadingBar />
              </div>
            ) : null}
          </div>
          {questionScrollFooter}
        </div>
        <ScrollToBottomControl
          viewportRef={questionViewportRef}
          scrollTarget={questionViewportRef}
          autoScrollOnInit
          contentVersion={visibleContentList.length}
          followNewContent={false}
          ariaLabel={t('common.core.scrollToBottom')}
          placement='bottom-center'
          position='absolute'
          bottomOffset={36}
          zIndex={10}
        />
        {!showAssistant && canUseAssistant ? (
          <Button
            ref={assistantEntryRef}
            type='button'
            className='absolute bottom-9 right-3 z-10 hidden h-auto min-h-10 max-w-[calc(50%-2.75rem)] whitespace-normal rounded-full px-4 py-2 text-start shadow-[0_6px_12px_-8px_rgba(15,23,42,0.38)] sm:inline-flex'
            disabled={disabled}
            onClick={() => {
              reportRouteChosen('ai_assistant');
              try {
                onAssistantOpened?.();
              } catch {}
              setAssistantVisible(true);
            }}
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
          analyticsScope={assistantAnalyticsScope}
          onPromptCopied={onAssistantPromptCopied}
          onBack={() => {
            if (resumeQuestions()) {
              reportRouteChosen('guided_questions');
              setAssistantVisible(false);
            }
          }}
        />
      ) : null}
      {reGenerateConfirm?.open ? (
        <Dialog
          open
          onOpenChange={open => {
            if (!open) reGenerateConfirm.onCancel();
          }}
        >
          <DialogContent className='sm:max-w-md'>
            <DialogHeader>
              <DialogTitle>
                {t('module.chat.regenerateConfirmTitle')}
              </DialogTitle>
              <DialogDescription>
                {t('module.chat.regenerateConfirmDescription')}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className='flex gap-2 sm:gap-2'>
              <Button
                type='button'
                variant='outline'
                onClick={reGenerateConfirm.onCancel}
              >
                {t('common.core.cancel')}
              </Button>
              <Button
                type='button'
                onClick={reGenerateConfirm.onConfirm}
              >
                {t('common.core.ok')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
      {hasVisibleStatus ? (
        <div
          className={cn(
            'flex min-h-9 shrink-0 items-center gap-2 text-sm text-muted-foreground',
            !items.length ? 'order-first pt-6' : 'pb-6',
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
