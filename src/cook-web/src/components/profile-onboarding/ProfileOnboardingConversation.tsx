'use client';

import React from 'react';
import {
  MarkdownFlow,
  type OnSendContentParams,
} from 'markdown-flow-ui/renderer';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { resolveInteractionSubmission } from '@/c-utils/interaction-user-input';
import { Button } from '@/components/ui/Button';
import { resolveMarkdownFlowLocale } from '@/lib/markdown-flow-locale';
import type { ProfileOnboardingStreamEvent } from '@/lib/profileOnboardingSse';

export type ProfileOnboardingSessionInfo = {
  session_id: string;
  block_index?: number;
  block_count?: number;
  profile_draft_block_index?: number;
  done?: boolean;
  expires_in?: number;
};

type ProfileOnboardingConversationItem = {
  content: string;
  elementBid: string;
  interaction: boolean;
  userInput?: string;
  finished: boolean;
};

type StreamHandle = { close?: () => void };

export type ProfileOnboardingRunSession = (params: {
  sessionId: string;
  expectedBlockIndex: number;
  requestId: string;
  userInput?: Record<string, string[]>;
  onMessage: (event: ProfileOnboardingStreamEvent) => void;
  onError: (error: unknown) => void;
}) => StreamHandle;

type ProfileOnboardingRunRequest = {
  expectedBlockIndex: number;
  requestId: string;
  userInput?: Record<string, string[]>;
};

export type ProfileOnboardingConversationProps = {
  createSession: () => Promise<ProfileOnboardingSessionInfo>;
  runSession: ProfileOnboardingRunSession;
  onSessionStarted?: (sessionId: string) => void;
  onDraftReady: (profileDraft: string, sessionId: string) => void;
  onError: (error: unknown) => void;
  onRetry?: () => void;
};

const NON_RETRYABLE_RUNTIME_ERROR_CODES = new Set([
  'transient_markdownflow_invalid',
  'transient_markdownflow_session_not_found',
]);

const asObject = (value: unknown): Record<string, unknown> | null => {
  if (value && typeof value === 'object') {
    return value as Record<string, unknown>;
  }
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim();
  if (!normalized.startsWith('{')) {
    return null;
  }
  try {
    const parsed = JSON.parse(normalized);
    return parsed && typeof parsed === 'object'
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
};

export const resolveProfileDraftFromRunEvent = (
  event: ProfileOnboardingStreamEvent,
): string => {
  const topLevelDraft = (
    event as ProfileOnboardingStreamEvent & {
      profile_draft?: unknown;
    }
  ).profile_draft;
  if (typeof topLevelDraft === 'string') {
    return topLevelDraft.trim();
  }
  const payload = asObject(event.content);
  const draft = payload?.profile_draft;
  return typeof draft === 'string' ? draft.trim() : '';
};

const resolveRunDone = (event: ProfileOnboardingStreamEvent) => {
  const payload = asObject(event.content);
  if (typeof payload?.done === 'boolean') {
    return payload.done;
  }
  return Boolean(resolveProfileDraftFromRunEvent(event));
};

const resolveNextBlockIndex = (
  event: ProfileOnboardingStreamEvent,
): number | null => {
  const nextBlockIndex = asObject(event.content)?.next_block_index;
  return typeof nextBlockIndex === 'number' &&
    Number.isInteger(nextBlockIndex) &&
    nextBlockIndex >= 0
    ? nextBlockIndex
    : null;
};

const resolveRuntimeErrorCode = (content: unknown): string => {
  if (typeof content === 'string') {
    const normalized = content.trim();
    const payload = asObject(normalized);
    if (!payload) {
      return normalized;
    }
    const nestedCode =
      payload.public_code ??
      payload.error_code ??
      payload.code ??
      payload.error;
    return typeof nestedCode === 'string' ? nestedCode.trim() : '';
  }
  const payload = asObject(content);
  const nestedCode =
    payload?.public_code ??
    payload?.error_code ??
    payload?.code ??
    payload?.error;
  return typeof nestedCode === 'string' ? nestedCode.trim() : '';
};

const isRetryableRuntimeError = (content: unknown) =>
  !NON_RETRYABLE_RUNTIME_ERROR_CODES.has(resolveRuntimeErrorCode(content));

let fallbackElementSequence = 0;
const nextFallbackElementBid = () =>
  `profile-element-${++fallbackElementSequence}`;

const resolveElement = (
  event: ProfileOnboardingStreamEvent,
): ProfileOnboardingConversationItem | null => {
  const type = event.event_type || event.type || '';
  const payload = asObject(event.content);
  if (type === 'element' && payload) {
    const content = typeof payload.content === 'string' ? payload.content : '';
    if (!content) {
      return null;
    }
    const elementType =
      typeof payload.element_type === 'string' ? payload.element_type : '';
    return {
      content,
      elementBid:
        (typeof payload.element_bid === 'string' && payload.element_bid) ||
        event.generated_block_bid ||
        nextFallbackElementBid(),
      interaction: elementType === 'interaction',
      userInput:
        typeof payload.user_input === 'string' ? payload.user_input : undefined,
      finished: elementType !== 'interaction',
    };
  }
  if (
    (type === 'interaction' || type === 'content') &&
    typeof event.content === 'string' &&
    event.content
  ) {
    return {
      content: event.content,
      elementBid: event.generated_block_bid || nextFallbackElementBid(),
      interaction: type === 'interaction',
      finished: type !== 'interaction',
    };
  }
  return null;
};

const upsertConversationItem = (
  items: ProfileOnboardingConversationItem[],
  item: ProfileOnboardingConversationItem,
) => {
  const index = items.findIndex(entry => entry.elementBid === item.elementBid);
  if (index < 0) {
    return [...items, item];
  }
  const next = [...items];
  next[index] = { ...next[index], ...item };
  return next;
};

export default function ProfileOnboardingConversation({
  createSession,
  runSession,
  onSessionStarted,
  onDraftReady,
  onError,
  onRetry,
}: ProfileOnboardingConversationProps) {
  const { t, i18n } = useTranslation();
  const [items, setItems] = React.useState<ProfileOnboardingConversationItem[]>(
    [],
  );
  const [loading, setLoading] = React.useState(true);
  const [retryAvailable, setRetryAvailable] = React.useState(false);
  const retryAvailableRef = React.useRef(false);
  const sessionIdRef = React.useRef('');
  const blockIndexRef = React.useRef(0);
  const requestSequenceRef = React.useRef(0);
  const streamRef = React.useRef<StreamHandle | null>(null);
  const runAttemptRef = React.useRef(0);
  const lastRunRequestRef = React.useRef<ProfileOnboardingRunRequest | null>(
    null,
  );
  const awaitingInteractionRef = React.useRef(false);
  const streamCompletedRef = React.useRef(false);
  const runtimeFailedRef = React.useRef(false);
  const mountedRef = React.useRef(true);
  const runNextRef = React.useRef<
    (userInput?: Record<string, string[]>) => void
  >(() => {});
  const createSessionRef = React.useRef(createSession);
  const runSessionRef = React.useRef(runSession);
  const onSessionStartedRef = React.useRef(onSessionStarted);
  const onDraftReadyRef = React.useRef(onDraftReady);
  const onErrorRef = React.useRef(onError);
  const onRetryRef = React.useRef(onRetry);
  const tRef = React.useRef(t);
  createSessionRef.current = createSession;
  runSessionRef.current = runSession;
  onSessionStartedRef.current = onSessionStarted;
  onDraftReadyRef.current = onDraftReady;
  onErrorRef.current = onError;
  onRetryRef.current = onRetry;
  tRef.current = t;

  const stopStream = React.useCallback(() => {
    streamRef.current?.close?.();
    streamRef.current = null;
  }, []);

  const handleStreamError = React.useCallback(() => {
    if (streamCompletedRef.current || !mountedRef.current) {
      return;
    }
    runtimeFailedRef.current = true;
    streamCompletedRef.current = true;
    stopStream();
    setLoading(false);
    retryAvailableRef.current = true;
    setRetryAvailable(true);
    onErrorRef.current(
      new Error(tRef.current('module.profileOnboarding.guided.retryableError')),
    );
  }, [stopStream]);

  const handleEvent = React.useCallback(
    (event: ProfileOnboardingStreamEvent) => {
      if (!mountedRef.current) {
        return;
      }
      if (runtimeFailedRef.current) {
        return;
      }
      if (streamCompletedRef.current) {
        return;
      }
      const type = event.event_type || event.type || '';
      const element = resolveElement(event);
      if (element) {
        awaitingInteractionRef.current = element.interaction;
        setItems(current => upsertConversationItem(current, element));
        setLoading(false);
      }
      if (type === 'error') {
        const retryable = isRetryableRuntimeError(event.content);
        runtimeFailedRef.current = true;
        streamCompletedRef.current = true;
        stopStream();
        setLoading(false);
        retryAvailableRef.current = retryable;
        setRetryAvailable(retryable);
        onErrorRef.current(
          new Error(
            tRef.current(
              retryable
                ? 'module.profileOnboarding.guided.retryableError'
                : 'module.profileOnboarding.guided.streamError',
            ),
          ),
        );
        return;
      }
      if (type !== 'done' || event.is_terminal !== true) {
        return;
      }

      const nextBlockIndex = resolveNextBlockIndex(event);
      if (nextBlockIndex !== null) {
        blockIndexRef.current = nextBlockIndex;
      }
      streamCompletedRef.current = true;
      stopStream();
      const draft = resolveProfileDraftFromRunEvent(event);
      if (resolveRunDone(event)) {
        setLoading(false);
        if (!draft) {
          onErrorRef.current(
            new Error(
              tRef.current('module.profileOnboarding.guided.missingDraft'),
            ),
          );
          return;
        }
        onDraftReadyRef.current(draft, sessionIdRef.current);
        return;
      }

      if (!awaitingInteractionRef.current) {
        queueMicrotask(() => runNextRef.current());
      } else {
        setLoading(false);
      }
    },
    [stopStream],
  );

  const runRequest = React.useCallback(
    (request: ProfileOnboardingRunRequest) => {
      if (!sessionIdRef.current || !mountedRef.current) {
        return;
      }
      stopStream();
      lastRunRequestRef.current = request;
      streamCompletedRef.current = false;
      runtimeFailedRef.current = false;
      awaitingInteractionRef.current = false;
      setLoading(true);
      retryAvailableRef.current = false;
      setRetryAvailable(false);
      const runAttempt = ++runAttemptRef.current;
      try {
        const nextStream = runSessionRef.current({
          sessionId: sessionIdRef.current,
          expectedBlockIndex: request.expectedBlockIndex,
          requestId: request.requestId,
          userInput: request.userInput,
          onMessage: event => {
            if (runAttempt === runAttemptRef.current) {
              handleEvent(event);
            }
          },
          onError: () => {
            if (runAttempt === runAttemptRef.current) {
              handleStreamError();
            }
          },
        });
        if (streamCompletedRef.current) {
          nextStream.close?.();
        } else {
          streamRef.current = nextStream;
        }
      } catch {
        handleStreamError();
      }
    },
    [handleEvent, handleStreamError, stopStream],
  );

  const runNext = React.useCallback(
    (userInput?: Record<string, string[]>) => {
      runRequest({
        expectedBlockIndex: blockIndexRef.current,
        requestId: `profile-onboarding-run-${++requestSequenceRef.current}`,
        userInput,
      });
    },
    [runRequest],
  );
  runNextRef.current = runNext;

  React.useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;
    setItems([]);
    setLoading(true);
    retryAvailableRef.current = false;
    setRetryAvailable(false);
    sessionIdRef.current = '';
    blockIndexRef.current = 0;
    requestSequenceRef.current = 0;
    lastRunRequestRef.current = null;
    void createSessionRef
      .current()
      .then(session => {
        if (cancelled || !mountedRef.current) {
          return;
        }
        sessionIdRef.current = session.session_id;
        blockIndexRef.current =
          typeof session.block_index === 'number' &&
          Number.isInteger(session.block_index) &&
          session.block_index >= 0
            ? session.block_index
            : 0;
        onSessionStartedRef.current?.(session.session_id);
        runNextRef.current();
      })
      .catch(() => {
        if (!cancelled && mountedRef.current) {
          setLoading(false);
          onErrorRef.current(
            new Error(
              tRef.current('module.profileOnboarding.guided.streamError'),
            ),
          );
        }
      });
    return () => {
      cancelled = true;
      mountedRef.current = false;
      stopStream();
    };
  }, [stopStream]);

  const handleSend = React.useCallback((content: OnSendContentParams) => {
    const { values, userInput } = resolveInteractionSubmission(content);
    if (!values.length) {
      return;
    }
    const variableName = content.variableName?.trim() || 'input';
    setItems(current => {
      const lastInteractionIndex = current.findLastIndex(
        item => item.interaction && !item.finished,
      );
      if (lastInteractionIndex < 0) {
        return current;
      }
      const next = [...current];
      next[lastInteractionIndex] = {
        ...next[lastInteractionIndex],
        finished: true,
        userInput,
      };
      return next;
    });
    runNextRef.current({ [variableName]: values });
  }, []);

  const handleRetry = React.useCallback(() => {
    const lastRunRequest = lastRunRequestRef.current;
    if (
      !retryAvailableRef.current ||
      !sessionIdRef.current ||
      !lastRunRequest
    ) {
      return;
    }
    retryAvailableRef.current = false;
    setRetryAvailable(false);
    onRetryRef.current?.();
    runRequest(lastRunRequest);
  }, [runRequest]);

  const locale = resolveMarkdownFlowLocale(
    i18n.resolvedLanguage ?? i18n.language,
  );

  return (
    <div className='space-y-4'>
      <div className='profile-onboarding-markdownflow min-h-36'>
        <MarkdownFlow
          locale={locale}
          initialContentList={items.map(item => ({
            content: item.content,
            isFinished: item.finished,
            readonly: item.finished || !item.interaction,
            userInput: item.userInput,
          }))}
          onSend={handleSend}
        />
      </div>
      <div
        className='flex min-h-6 items-center gap-2 text-sm text-muted-foreground'
        role='status'
        aria-live='polite'
      >
        {loading ? (
          <>
            <Loader2
              className='h-4 w-4 animate-spin'
              aria-hidden='true'
            />
            {t('module.profileOnboarding.guided.thinking')}
          </>
        ) : null}
        {retryAvailable ? (
          <Button
            type='button'
            size='sm'
            variant='outline'
            onClick={handleRetry}
          >
            {t('module.profileOnboarding.guided.retry')}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
