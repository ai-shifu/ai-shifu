import { useCallback, useRef, useState, type RefObject } from 'react';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import { hasStreamingAskMessage } from './ask-state';
import { useAskStateStore } from './use-ask-state-store';
import { useReadingFollowUpPoint } from './use-reading-follow-up-point';

type Entry = 'boundary' | 'history';
type CloseMethod = 'close' | 'continue';
type ReadingState = {
  scopeKey: string;
  expandedAnchor: string | null;
  selectedAnchor: string | null;
  drafts: ReadonlySet<string>;
};
type Options = {
  items: ChatContentItem[];
  eligibleAnchors: ReadonlySet<string>;
  enabled: boolean;
  mobile: boolean;
  previewMode: boolean;
  rootRef: RefObject<HTMLElement | null>;
  scopeKey: string;
  onEnsureAsk: (anchor: string) => void;
  trackEvent: (name: string, payload: Record<string, string>) => unknown;
};

const initialState = (scopeKey: string): ReadingState => ({
  scopeKey,
  expandedAnchor: null,
  selectedAnchor: null,
  drafts: new Set(),
});

/** Own only the reading surface lifecycle; messages remain in the shared store. */
export function useReadingFollowUp({
  items,
  eligibleAnchors,
  enabled,
  mobile,
  previewMode,
  rootRef,
  scopeKey,
  onEnsureAsk,
  trackEvent,
}: Options) {
  const [state, setState] = useState(() => initialState(scopeKey));
  const stateRef = useRef(state);
  if (stateRef.current.scopeKey !== scopeKey) {
    stateRef.current = initialState(scopeKey);
  }
  const current = stateRef.current;
  const currentScopeRef = useRef({ scopeKey, generation: 0 });
  if (currentScopeRef.current.scopeKey !== scopeKey) {
    currentScopeRef.current = {
      scopeKey,
      generation: currentScopeRef.current.generation + 1,
    };
  }
  const scopeGeneration = currentScopeRef.current.generation;
  const eligible = new Set(
    items
      .filter(
        item =>
          item.type === ChatContentItemType.CONTENT &&
          item.element_bid !== 'loading' &&
          eligibleAnchors.has(item.element_bid),
      )
      .map(item => item.element_bid),
  );
  const askScope = useAskStateStore(store => store.lessonScopeKey);
  const askLists = useAskStateStore(store => store.askListByAnchorElementBid);
  const streamingAnchor =
    askScope === scopeKey
      ? Object.keys(askLists).find(
          anchor =>
            eligible.has(anchor) && hasStreamingAskMessage(askLists[anchor]),
        )
      : undefined;
  const draftAnchor =
    current.selectedAnchor &&
    eligible.has(current.selectedAnchor) &&
    current.drafts.has(current.selectedAnchor)
      ? current.selectedAnchor
      : [...current.drafts].find(anchor => eligible.has(anchor));
  const expandedAnchor =
    enabled && current.expandedAnchor && eligible.has(current.expandedAnchor)
      ? current.expandedAnchor
      : null;
  const isLocked = Boolean(expandedAnchor || draftAnchor || streamingAnchor);
  const { anchorElementBid, selectAnchor } = useReadingFollowUpPoint({
    rootRef,
    enabled,
    mobile,
    locked: isLocked,
    scopeKey,
    contentKey: [...eligible].join('|'),
  });
  const liveOptions = useRef({
    enabled,
    eligible,
    mobile,
    previewMode,
    onEnsureAsk,
    trackEvent,
    isLocked,
  });
  liveOptions.current = {
    enabled,
    eligible,
    mobile,
    previewMode,
    onEnsureAsk,
    trackEvent,
    isLocked,
  };

  const update = useCallback((next: ReadingState) => {
    stateRef.current = next;
    setState(next);
  }, []);
  const record = useCallback(
    (name: string, payload: Record<string, string>) => {
      const options = liveOptions.current;
      if (options.previewMode) return;
      try {
        void Promise.resolve(options.trackEvent(name, payload)).catch(() => {});
      } catch {}
    },
    [],
  );

  const toggle = useCallback(
    (anchor: string, entry: Entry = 'boundary') => {
      const options = liveOptions.current;
      if (
        currentScopeRef.current.generation !== scopeGeneration ||
        !options.enabled ||
        !options.eligible.has(anchor) ||
        stateRef.current.expandedAnchor === anchor
      )
        return;
      options.onEnsureAsk(anchor);
      update({
        ...stateRef.current,
        expandedAnchor: anchor,
        selectedAnchor: anchor,
      });
      record('learner_read_follow_up_opened', {
        surface: options.mobile ? 'mobile' : 'desktop',
        entry,
      });
    },
    [record, scopeGeneration, update],
  );

  const close = useCallback(
    (method: CloseMethod = 'close') => {
      const options = liveOptions.current;
      const previous = stateRef.current;
      if (
        currentScopeRef.current.generation !== scopeGeneration ||
        !options.enabled ||
        !previous.expandedAnchor ||
        !options.eligible.has(previous.expandedAnchor)
      )
        return;
      update({ ...previous, expandedAnchor: null });
      record('learner_read_follow_up_closed', {
        surface: options.mobile ? 'mobile' : 'desktop',
        method,
      });
    },
    [record, scopeGeneration, update],
  );

  const onDraftChange = useCallback(
    (anchor: string, hasDraft: boolean) => {
      if (currentScopeRef.current.generation !== scopeGeneration) return;
      const previous = stateRef.current;
      if (hasDraft && !liveOptions.current.eligible.has(anchor)) return;
      if (previous.drafts.has(anchor) === hasDraft) return;
      const drafts = new Set(previous.drafts);
      if (hasDraft) drafts.add(anchor);
      else drafts.delete(anchor);
      update({
        ...previous,
        drafts,
        selectedAnchor: hasDraft ? anchor : previous.selectedAnchor,
      });
    },
    [scopeGeneration, update],
  );

  const selectCandidate = useCallback(
    (anchor: string) => {
      const options = liveOptions.current;
      if (
        currentScopeRef.current.generation !== scopeGeneration ||
        !options.enabled ||
        options.isLocked ||
        !options.eligible.has(anchor)
      )
        return;
      selectAnchor(anchor);
    },
    [scopeGeneration, selectAnchor],
  );

  const candidate = draftAnchor || streamingAnchor || anchorElementBid;
  return {
    expandedAnchor,
    isLocked,
    selectCandidate,
    selectedAnchor: current.selectedAnchor,
    candidateAnchor:
      enabled && !expandedAnchor && candidate && eligible.has(candidate)
        ? candidate
        : null,
    toggle,
    close,
    onDraftChange,
  };
}
