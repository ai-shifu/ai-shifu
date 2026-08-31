'use client';

import React from 'react';
import { ContentRender } from 'markdown-flow-ui/renderer';
import { ScrollToBottomControl } from 'markdown-flow-ui/scroll';
import { Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { CHAT_TYPEWRITER_SPEED_MS } from '@/c-constants/uiConstants';
import { resolveMarkdownFlowLocale } from '@/lib/markdown-flow-locale';
import { cn } from '@/lib/utils';
import type {
  ProfileOnboardingAssistantAnswers,
  ProfileOnboardingRunSession,
  ProfileOnboardingSessionInfo,
  ProfileOnboardingTypewriterCache,
} from './profileOnboardingConversationModel';
import {
  shouldEnableProfileOnboardingTypewriter,
  syncProfileOnboardingTypewriterCache,
} from './profileOnboardingConversationModel';
import { ProfileAssistantAnswersView } from './ProfileAssistantAnswersView';
import { useProfileOnboardingSession } from './useProfileOnboardingSession';

// ContentRender recreates its custom interaction component on every render.
// Isolate it from sibling view/copy/paste state to preserve unsent input.
const StableProfileContentRender = React.memo(ContentRender);

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
  questionScrollFooter?: React.ReactNode;
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
  questionScrollFooter,
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
  const [isDocumentVisible, setIsDocumentVisible] = React.useState(
    () =>
      typeof document === 'undefined' || document.visibilityState !== 'hidden',
  );
  const [typewriterCache, setTypewriterCache] =
    React.useState<ProfileOnboardingTypewriterCache>({});
  const [pendingProfileDraft, setPendingProfileDraft] =
    React.useState<PendingProfileDraft | null>(null);
  const holdProfileDraft = React.useCallback(
    (profileDraft: string, sessionId: string, nickname?: string) => {
      setPendingProfileDraft({ profileDraft, sessionId, nickname });
    },
    [],
  );

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
    onDraftReady: holdProfileDraft,
    onError,
    onSessionCreateRejected,
    onRetry,
  });
  const itemsRef = React.useRef(items);
  itemsRef.current = items;

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
        elementBid: item.elementBid,
        content: item.content,
        isFinished: item.finished,
        finished: item.finished,
        interaction: item.interaction,
        readonly: questionReadonly || item.finished || !item.interaction,
        userInput: item.userInput,
        elementType: item.elementType,
      })),
    [items, questionReadonly],
  );

  React.useEffect(() => {
    setTypewriterCache(previousCache =>
      syncProfileOnboardingTypewriterCache(
        items,
        previousCache,
        !isDocumentVisible,
      ),
    );
  }, [isDocumentVisible, items]);

  React.useEffect(() => {
    if (!pendingProfileDraft) return;
    const hasUnfinishedGuidance =
      isDocumentVisible &&
      items.some(item => {
        if (item.elementType !== 'text') return false;
        const cacheEntry = typewriterCache[item.elementBid];
        return (
          cacheEntry?.isFinished !== true || cacheEntry.content !== item.content
        );
      });
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
    items,
    onDraftReady,
    pendingProfileDraft,
    typewriterCache,
  ]);

  const visibleContentList = React.useMemo(() => {
    if (!isDocumentVisible) return contentList;
    const visibleItems: typeof contentList = [];
    for (const item of contentList) {
      visibleItems.push(item);
      const cacheEntry = typewriterCache[item.elementBid];
      if (
        item.elementType === 'text' &&
        (!cacheEntry?.isFinished || cacheEntry.content !== item.content)
      ) {
        break;
      }
    }
    return visibleItems;
  }, [contentList, isDocumentVisible, typewriterCache]);

  const handleTypeFinished = React.useCallback((elementBid: string) => {
    setTypewriterCache(previousCache => {
      const entry = previousCache[elementBid];
      const item = itemsRef.current.find(
        candidate => candidate.elementBid === elementBid,
      );
      if (!entry && !item) return previousCache;
      return {
        ...previousCache,
        [elementBid]: {
          content: entry?.content ?? item?.content ?? '',
          isFinished: true,
          isSuppressed: entry?.isSuppressed ?? false,
        },
      };
    });
  }, []);
  const typeFinishedCallbacksRef = React.useRef(new Map<string, () => void>());
  const getTypeFinishedCallback = React.useCallback(
    (elementBid: string) => {
      const existingCallback = typeFinishedCallbacksRef.current.get(elementBid);
      if (existingCallback) return existingCallback;
      const callback = () => handleTypeFinished(elementBid);
      typeFinishedCallbacksRef.current.set(elementBid, callback);
      return callback;
    },
    [handleTypeFinished],
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
            'profile-onboarding-markdownflow h-full min-h-0 overflow-y-auto overscroll-contain py-6 pe-1 [scrollbar-gutter:stable] max-sm:[&_button]:min-h-11 max-sm:[&_button]:min-w-11 max-sm:[&_input]:min-h-11 max-sm:[&_input]:text-base max-sm:[&_select]:min-h-11 max-sm:[&_select]:text-base max-sm:[&_textarea]:text-base sm:any-pointer-coarse:[&_button]:min-h-11 sm:any-pointer-coarse:[&_button]:min-w-11 sm:any-pointer-coarse:[&_input]:min-h-11 sm:any-pointer-coarse:[&_input]:text-base sm:any-pointer-coarse:[&_select]:min-h-11 sm:any-pointer-coarse:[&_select]:text-base sm:any-pointer-coarse:[&_textarea]:text-base',
            canUseAssistant && 'sm:scroll-pb-20 sm:pb-20',
          )}
        >
          <div className='markdown-flow'>
            {visibleContentList.length ? (
              visibleContentList.map(item => (
                <StableProfileContentRender
                  key={item.elementBid}
                  locale={locale}
                  content={item.content}
                  userInput={item.userInput}
                  readonly={item.readonly}
                  onSend={item.isFinished ? undefined : send}
                  enableTypewriter={
                    isDocumentVisible &&
                    shouldEnableProfileOnboardingTypewriter(
                      item,
                      typewriterCache[item.elementBid],
                    )
                  }
                  typingSpeed={CHAT_TYPEWRITER_SPEED_MS}
                  typewriterPacing='content-aware'
                  onTypeFinished={
                    item.elementType === 'text'
                      ? getTypeFinishedCallback(item.elementBid)
                      : undefined
                  }
                />
              ))
            ) : (
              <StableProfileContentRender
                locale={locale}
                content=''
                readonly
                enableTypewriter={isDocumentVisible}
                typingSpeed={CHAT_TYPEWRITER_SPEED_MS}
                typewriterPacing='content-aware'
              />
            )}
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
