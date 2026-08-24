'use client';

import React from 'react';
import { MarkdownFlow } from 'markdown-flow-ui/renderer';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { resolveMarkdownFlowLocale } from '@/lib/markdown-flow-locale';
import { cn } from '@/lib/utils';
import type {
  ProfileOnboardingRunSession,
  ProfileOnboardingSessionInfo,
} from './profileOnboardingConversationModel';
import { useProfileOnboardingSession } from './useProfileOnboardingSession';

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
  disabled?: boolean;
  errorMessage?: string;
  onSessionStarted?: (sessionId: string) => void;
  onDraftReady: (
    profileDraft: string,
    sessionId: string,
    nickname?: string,
  ) => void;
  onError: (error: unknown) => void;
  onRetry?: () => void;
};

export default function ProfileOnboardingConversation({
  createSession,
  runSession,
  disabled = false,
  errorMessage = '',
  onSessionStarted,
  onDraftReady,
  onError,
  onRetry,
}: ProfileOnboardingConversationProps) {
  const { t, i18n } = useTranslation();
  const latestItemRef = React.useRef<HTMLDivElement>(null);
  const {
    items,
    loading,
    runInFlight,
    retryAvailable,
    submissionLimitError,
    send,
    retry,
  } = useProfileOnboardingSession({
    createSession,
    runSession,
    disabled,
    messages: {
      retryableError: t('module.profileOnboarding.guided.retryableError'),
      streamError: t('module.profileOnboarding.guided.streamError'),
      missingDraft: t('module.profileOnboarding.guided.missingDraft'),
    },
    onSessionStarted,
    onDraftReady,
    onError,
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

  return (
    <div
      data-testid='profile-onboarding-conversation'
      className='flex h-full min-h-0 flex-col gap-3'
      aria-busy={disabled || loading || runInFlight}
    >
      <div className='profile-onboarding-markdownflow min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 [scrollbar-gutter:stable]'>
        <MarkdownFlow
          locale={locale}
          initialContentList={items.map(item => ({
            content: item.content,
            isFinished: item.finished,
            readonly:
              disabled || runInFlight || item.finished || !item.interaction,
            userInput: item.userInput,
          }))}
          onSend={send}
        />
        <div
          ref={latestItemRef}
          aria-hidden='true'
        />
      </div>
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
