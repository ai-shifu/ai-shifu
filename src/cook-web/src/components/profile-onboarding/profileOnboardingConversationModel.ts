import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { resolveInteractionSubmission } from '@/c-utils/interaction-user-input';
import type { ProfileOnboardingStreamEvent } from '@/lib/profileOnboardingSse';

export type ProfileOnboardingSessionInfo = {
  session_id: string;
  block_index?: number;
  block_count?: number;
  profile_draft_block_index?: number;
  done?: boolean;
  expires_in?: number;
};

export type ProfileOnboardingRunSession = (params: {
  sessionId: string;
  expectedBlockIndex: number;
  requestId: string;
  userInput?: Record<string, string[]>;
  onMessage: (event: ProfileOnboardingStreamEvent) => void;
  onError: (error: unknown) => void;
}) => { close?: () => void };

export type ProfileOnboardingConversationItem = {
  content: string;
  elementBid: string;
  interaction: boolean;
  userInput?: string;
  finished: boolean;
};

export type ProfileOnboardingConversationStatus =
  | 'creating'
  | 'streaming'
  | 'awaiting_input'
  | 'completed'
  | 'retryable_error'
  | 'fatal_error';

export type ProfileOnboardingConversationState = {
  status: ProfileOnboardingConversationStatus;
  items: ProfileOnboardingConversationItem[];
  runHasContent: boolean;
  submissionLimitError: boolean;
};

export type ProfileOnboardingConversationAction =
  | { type: 'start_session' }
  | { type: 'start_run' }
  | { type: 'receive_item'; item: ProfileOnboardingConversationItem }
  | { type: 'await_input' }
  | { type: 'complete' }
  | { type: 'fail'; retryable: boolean }
  | { type: 'reject_submission' }
  | { type: 'accept_submission'; userInput: string };

export const initialProfileOnboardingConversationState: ProfileOnboardingConversationState =
  {
    status: 'creating',
    items: [],
    runHasContent: false,
    submissionLimitError: false,
  };

export const profileOnboardingConversationReducer = (
  state: ProfileOnboardingConversationState,
  action: ProfileOnboardingConversationAction,
): ProfileOnboardingConversationState => {
  switch (action.type) {
    case 'start_session':
      return initialProfileOnboardingConversationState;
    case 'start_run':
      if (
        state.status !== 'creating' &&
        state.status !== 'awaiting_input' &&
        state.status !== 'retryable_error'
      ) {
        return state;
      }
      return {
        ...state,
        status: 'streaming',
        runHasContent: false,
        submissionLimitError: false,
      };
    case 'receive_item':
      if (state.status !== 'streaming') {
        return state;
      }
      return {
        ...state,
        items: upsertConversationItem(state.items, action.item),
        runHasContent: true,
      };
    case 'await_input':
      if (state.status !== 'streaming') {
        return state;
      }
      return { ...state, status: 'awaiting_input' };
    case 'complete':
      if (state.status !== 'streaming') {
        return state;
      }
      return { ...state, status: 'completed' };
    case 'fail':
      if (state.status !== 'creating' && state.status !== 'streaming') {
        return state;
      }
      return {
        ...state,
        status: action.retryable ? 'retryable_error' : 'fatal_error',
      };
    case 'reject_submission':
      if (state.status !== 'awaiting_input') {
        return state;
      }
      return { ...state, submissionLimitError: true };
    case 'accept_submission': {
      if (state.status !== 'awaiting_input') {
        return state;
      }
      let lastInteractionIndex = -1;
      for (let index = state.items.length - 1; index >= 0; index -= 1) {
        const item = state.items[index];
        if (item.interaction && !item.finished) {
          lastInteractionIndex = index;
          break;
        }
      }
      if (lastInteractionIndex < 0) {
        return { ...state, submissionLimitError: false };
      }
      const items = [...state.items];
      items[lastInteractionIndex] = {
        ...items[lastInteractionIndex],
        finished: true,
        userInput: action.userInput,
      };
      return { ...state, items, submissionLimitError: false };
    }
  }
};

const NON_RETRYABLE_RUNTIME_ERROR_CODES = new Set([
  'transient_markdownflow_invalid',
]);
export const SESSION_NOT_FOUND_RUNTIME_ERROR_CODE =
  'transient_markdownflow_session_not_found';
const PROFILE_ONBOARDING_MAX_INPUT_KEY_CODEPOINTS = 256;
const PROFILE_ONBOARDING_MAX_INPUT_VALUES = 100;
const PROFILE_ONBOARDING_MAX_INPUT_VALUE_CODEPOINTS = 4_000;
const PROFILE_ONBOARDING_MAX_INPUT_TOTAL_CODEPOINTS = 10_000;

const countCodePoints = (value: string) => Array.from(value).length;

export const isProfileOnboardingSubmissionWithinLimits = (
  variableName: string,
  values: string[],
) => {
  if (
    !variableName ||
    countCodePoints(variableName) >
      PROFILE_ONBOARDING_MAX_INPUT_KEY_CODEPOINTS ||
    !values.length ||
    values.length > PROFILE_ONBOARDING_MAX_INPUT_VALUES
  ) {
    return false;
  }

  let totalCodePoints = 0;
  for (const value of values) {
    const valueCodePoints = countCodePoints(value);
    if (
      !value.trim() ||
      valueCodePoints > PROFILE_ONBOARDING_MAX_INPUT_VALUE_CODEPOINTS
    ) {
      return false;
    }
    totalCodePoints += valueCodePoints;
    if (totalCodePoints > PROFILE_ONBOARDING_MAX_INPUT_TOTAL_CODEPOINTS) {
      return false;
    }
  }
  return true;
};

export const resolveProfileOnboardingSubmission = (
  content: OnSendContentParams,
) => {
  const selectedValues = Array.isArray(content.selectedValues)
    ? content.selectedValues.filter(
        (value): value is string => typeof value === 'string',
      )
    : [];
  const inputText =
    typeof content.inputText === 'string' ? content.inputText : undefined;
  const buttonText =
    typeof content.buttonText === 'string' ? content.buttonText : undefined;
  // MarkdownFlow carries configured option values in buttonText/selectedValues.
  // Keep those exact for runtime matching while normalizing only their display.
  const { userInput } = resolveInteractionSubmission({
    selectedValues,
    inputText,
    buttonText,
  });
  const values: string[] = [];
  const seen = new Set<string>();
  const addValue = (value: string | undefined, trim: boolean) => {
    if (value === undefined || !value.trim()) {
      return;
    }
    const submittedValue = trim ? value.trim() : value;
    if (seen.has(submittedValue)) {
      return;
    }
    seen.add(submittedValue);
    values.push(submittedValue);
  };

  selectedValues.forEach(value => addValue(value, false));
  addValue(inputText, true);
  addValue(buttonText, false);

  return { values, userInput };
};

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

export const resolveProfileNicknameFromRunEvent = (
  event: ProfileOnboardingStreamEvent,
): string => {
  const topLevelNickname = (
    event as ProfileOnboardingStreamEvent & {
      nickname?: unknown;
    }
  ).nickname;
  if (typeof topLevelNickname === 'string') {
    return topLevelNickname.trim();
  }
  const payload = asObject(event.content);
  const nickname = payload?.nickname;
  return typeof nickname === 'string' ? nickname.trim() : '';
};

export const resolveRunDone = (event: ProfileOnboardingStreamEvent) => {
  const payload = asObject(event.content);
  if (typeof payload?.done === 'boolean') {
    return payload.done;
  }
  return Boolean(resolveProfileDraftFromRunEvent(event));
};

export const resolveNextBlockIndex = (
  event: ProfileOnboardingStreamEvent,
): number | null => {
  const nextBlockIndex = asObject(event.content)?.next_block_index;
  return typeof nextBlockIndex === 'number' &&
    Number.isInteger(nextBlockIndex) &&
    nextBlockIndex >= 0
    ? nextBlockIndex
    : null;
};

export const resolveRuntimeErrorCode = (content: unknown): string => {
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

export const isRetryableRuntimeError = (content: unknown) =>
  !NON_RETRYABLE_RUNTIME_ERROR_CODES.has(resolveRuntimeErrorCode(content));

let fallbackElementSequence = 0;
const nextFallbackElementBid = () =>
  `profile-element-${++fallbackElementSequence}`;

export const resolveProfileOnboardingElement = (
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

export const upsertConversationItem = (
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
