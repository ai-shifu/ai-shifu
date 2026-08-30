const HISTORY_INDEX_KEY = '__ai_shifu_history_index';
const RESTORATION_TIMEOUT_MS = 1000;
const RESTORATION_MAX_ATTEMPTS = 2;
const TRAVERSAL_TIMEOUT_MS = 5000;

export type BrowserHistoryTraversal = {
  targetIndex: number | null;
  fallbackUrl: string | null;
};

type BrowserHistoryGuard = (traversal: BrowserHistoryTraversal) => void;

type HistoryEntrySnapshot = {
  index: number;
  state: unknown;
  url: string;
};

type PendingRestoration = {
  attempts: number;
  source: HistoryEntrySnapshot;
  target: HistoryEntrySnapshot;
  timeoutId: number | null;
};

type AllowedTraversal = {
  targetIndex: number | null;
  resolve: () => void;
  reject: (error: Error) => void;
  timeoutId: number;
};

type StartTraversal = () => Promise<unknown> | void;

let activeGuard: BrowserHistoryGuard | null = null;
let currentEntry: HistoryEntrySnapshot | null = null;
let pendingRestoration: PendingRestoration | null = null;
let allowedTraversal: AllowedTraversal | null = null;
let attachmentCount = 0;
let detachBridge: (() => void) | null = null;

export const getBrowserHistoryIndex = (state: unknown): number | null => {
  if (!state || typeof state !== 'object') {
    return null;
  }
  const value = (state as Record<string, unknown>)[HISTORY_INDEX_KEY];
  return Number.isSafeInteger(value) ? (value as number) : null;
};

const withBrowserHistoryIndex = (state: unknown, index: number) => ({
  ...(state && typeof state === 'object' ? state : {}),
  [HISTORY_INDEX_KEY]: index,
});

const finishAllowedTraversal = (error?: Error) => {
  const pending = allowedTraversal;
  if (!pending) {
    return;
  }
  allowedTraversal = null;
  window.clearTimeout(pending.timeoutId);
  if (error) {
    pending.reject(error);
  } else {
    pending.resolve();
  }
};

const clearPendingRestoration = () => {
  const pending = pendingRestoration;
  pendingRestoration = null;
  if (pending && pending.timeoutId !== null) {
    window.clearTimeout(pending.timeoutId);
  }
};

const installBrowserHistoryBridge = () => {
  if (typeof window === 'undefined') {
    return () => undefined;
  }
  const originalPushState = window.history.pushState.bind(window.history);
  const originalReplaceState = window.history.replaceState.bind(window.history);
  const initialIndex = getBrowserHistoryIndex(window.history.state) ?? 0;
  const initialState = withBrowserHistoryIndex(
    window.history.state,
    initialIndex,
  );
  originalReplaceState(initialState, '');
  currentEntry = {
    index: initialIndex,
    state: initialState,
    url: window.location.href,
  };

  const indexedPushState: History['pushState'] = (data, unused, url) => {
    const nextIndex = (currentEntry?.index ?? 0) + 1;
    const nextState = withBrowserHistoryIndex(data, nextIndex);
    originalPushState(nextState, unused, url);
    currentEntry = {
      index: nextIndex,
      state: nextState,
      url: window.location.href,
    };
  };
  const indexedReplaceState: History['replaceState'] = (data, unused, url) => {
    const nextIndex = currentEntry?.index ?? 0;
    const nextState = withBrowserHistoryIndex(data, nextIndex);
    originalReplaceState(nextState, unused, url);
    currentEntry = {
      index: nextIndex,
      state: nextState,
      url: window.location.href,
    };
  };
  window.history.pushState = indexedPushState;
  window.history.replaceState = indexedReplaceState;

  const completeRestorationIfAtSource = (
    pending: PendingRestoration,
  ): boolean => {
    if (
      pendingRestoration !== pending ||
      getBrowserHistoryIndex(window.history.state) !== pending.source.index
    ) {
      return false;
    }
    currentEntry = {
      index: pending.source.index,
      state: window.history.state,
      url: window.location.href,
    };
    clearPendingRestoration();
    activeGuard?.({ targetIndex: pending.target.index, fallbackUrl: null });
    return true;
  };

  const recoverFailedRestoration = (pending: PendingRestoration) => {
    if (pendingRestoration !== pending) {
      return;
    }
    clearPendingRestoration();
    try {
      const sourceState = withBrowserHistoryIndex(
        pending.source.state,
        pending.target.index,
      );
      originalReplaceState(sourceState, '', pending.source.url);
      currentEntry = {
        ...pending.source,
        index: pending.target.index,
        state: sourceState,
        url: window.location.href,
      };
    } catch {
      currentEntry = pending.target;
    }
    activeGuard?.({ targetIndex: null, fallbackUrl: pending.target.url });
  };

  const startRestoration = (pending: PendingRestoration) => {
    if (pendingRestoration !== pending) {
      return;
    }
    pending.attempts += 1;
    pending.timeoutId = window.setTimeout(() => {
      if (pendingRestoration !== pending) {
        return;
      }
      if (completeRestorationIfAtSource(pending)) {
        return;
      }
      const liveIndex = getBrowserHistoryIndex(window.history.state);
      if (liveIndex !== null) {
        currentEntry = {
          index: liveIndex,
          state: window.history.state,
          url: window.location.href,
        };
      }
      if (pending.attempts < RESTORATION_MAX_ATTEMPTS) {
        startRestoration(pending);
        return;
      }
      recoverFailedRestoration(pending);
    }, RESTORATION_TIMEOUT_MS);
    try {
      window.history.go(
        pending.source.index - (currentEntry?.index ?? pending.target.index),
      );
    } catch {
      // The bounded timer retries once, then realigns the source URL/state and
      // hands the frozen destination to the page as a route fallback.
    }
  };

  const handlePopState = (event: PopStateEvent) => {
    const targetIndex = getBrowserHistoryIndex(event.state);
    if (targetIndex === null) {
      return;
    }
    const source =
      currentEntry ??
      ({
        index: targetIndex,
        state: event.state,
        url: window.location.href,
      } satisfies HistoryEntrySnapshot);
    const target = {
      index: targetIndex,
      state: event.state,
      url: window.location.href,
    } satisfies HistoryEntrySnapshot;
    currentEntry = target;

    if (allowedTraversal) {
      if (
        allowedTraversal.targetIndex === null ||
        allowedTraversal.targetIndex === targetIndex
      ) {
        finishAllowedTraversal();
        return;
      }
      finishAllowedTraversal(
        new Error(
          'A different browser-history traversal superseded the request.',
        ),
      );
    }

    if (pendingRestoration) {
      if (targetIndex === pendingRestoration.source.index) {
        const restoredTraversal = pendingRestoration;
        clearPendingRestoration();
        activeGuard?.({
          targetIndex: restoredTraversal.target.index,
          fallbackUrl: null,
        });
        return;
      }
      event.stopImmediatePropagation();
      if (pendingRestoration.timeoutId !== null) {
        window.clearTimeout(pendingRestoration.timeoutId);
        pendingRestoration.timeoutId = null;
      }
      pendingRestoration.attempts = 0;
      startRestoration(pendingRestoration);
      return;
    }

    if (!activeGuard || source.index === targetIndex) {
      return;
    }
    event.stopImmediatePropagation();
    pendingRestoration = {
      attempts: 0,
      source,
      target,
      timeoutId: null,
    };
    startRestoration(pendingRestoration);
  };

  window.addEventListener('popstate', handlePopState);
  return () => {
    window.removeEventListener('popstate', handlePopState);
    if (window.history.pushState === indexedPushState) {
      window.history.pushState = originalPushState;
    }
    if (window.history.replaceState === indexedReplaceState) {
      window.history.replaceState = originalReplaceState;
    }
    finishAllowedTraversal(
      new Error('The browser-history bridge was removed.'),
    );
    clearPendingRestoration();
    activeGuard = null;
    currentEntry = null;
  };
};

export const attachBrowserHistoryGuardBridge = () => {
  attachmentCount += 1;
  if (!detachBridge) {
    detachBridge = installBrowserHistoryBridge();
  }
  return () => {
    attachmentCount = Math.max(0, attachmentCount - 1);
    if (attachmentCount === 0 && detachBridge) {
      const detach = detachBridge;
      detachBridge = null;
      detach();
    }
  };
};

export const registerBrowserHistoryGuard = (guard: BrowserHistoryGuard) => {
  activeGuard = guard;
  return () => {
    if (activeGuard === guard) {
      activeGuard = null;
    }
  };
};

export const isBrowserHistoryBridgeTraversing = () =>
  Boolean(pendingRestoration || allowedTraversal);

export const resumeBrowserHistoryTraversal = (
  targetIndex: number | null,
  startTraversal?: StartTraversal,
): Promise<void> => {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('Browser history is unavailable.'));
  }
  if (allowedTraversal) {
    return Promise.reject(
      new Error('A browser-history traversal is already in progress.'),
    );
  }
  if (!detachBridge && !startTraversal) {
    return Promise.reject(
      new Error('The browser-history bridge is unavailable.'),
    );
  }
  if (targetIndex === null && !startTraversal) {
    return Promise.reject(
      new Error('The browser-history traversal target is unavailable.'),
    );
  }
  const liveIndex = getBrowserHistoryIndex(window.history.state);
  if (liveIndex !== null) {
    currentEntry = {
      index: liveIndex,
      state: window.history.state,
      url: window.location.href,
    };
  }
  if (
    targetIndex !== null &&
    targetIndex === (liveIndex ?? currentEntry?.index)
  ) {
    return Promise.resolve();
  }

  return new Promise<void>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      const pending = allowedTraversal;
      const reachedIndex = getBrowserHistoryIndex(window.history.state);
      if (
        pending &&
        pending.targetIndex !== null &&
        reachedIndex === pending.targetIndex
      ) {
        currentEntry = {
          index: reachedIndex,
          state: window.history.state,
          url: window.location.href,
        };
        finishAllowedTraversal();
        return;
      }
      finishAllowedTraversal(
        new Error('The browser-history traversal did not complete.'),
      );
    }, TRAVERSAL_TIMEOUT_MS);
    allowedTraversal = { targetIndex, resolve, reject, timeoutId };
    try {
      const started = startTraversal
        ? startTraversal()
        : window.history.go(
            (targetIndex ?? liveIndex ?? currentEntry?.index ?? 0) -
              (liveIndex ?? currentEntry?.index ?? 0),
          );
      if (started) {
        void Promise.resolve(started).then(
          () => {
            // A Navigation API traversal may resolve `finished` before its
            // classic `popstate` is delivered. Keep the one-shot bypass alive
            // until that event so the still-mounted dirty guard cannot bounce
            // the accepted traversal back to its source. Component tests that
            // call this helper without the root bridge retain promise-only
            // completion.
            if (!detachBridge) {
              finishAllowedTraversal();
            }
          },
          () =>
            finishAllowedTraversal(
              new Error('The browser-history traversal failed.'),
            ),
        );
      }
    } catch {
      finishAllowedTraversal(
        new Error('The browser-history traversal failed.'),
      );
    }
  });
};
