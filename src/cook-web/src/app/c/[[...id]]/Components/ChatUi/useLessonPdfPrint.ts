import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from 'react';

const LESSON_PDF_PRINT_CLASS = 'lesson-pdf-print';
const PRINT_ASSET_WAIT_TIMEOUT_MS = 5000;
const PRINT_DIALOG_FALLBACK_MS = 15000;
const PRINT_DOM_MIN_SETTLE_MS = 600;
const PRINT_DOM_QUIET_MS = 250;
const PRINT_DOM_WAIT_TIMEOUT_MS = 5000;
const ASYNC_PRINT_CONTENT_SELECTOR = [
  '.mermaid-chart-container',
  '.content-render-iframe',
  '.content-render-iframe-sandbox',
  'iframe',
].join(',');

const waitForNextPaint = (signal: AbortSignal) =>
  new Promise<void>(resolve => {
    if (signal.aborted) {
      resolve();
      return;
    }

    let rafId = 0;
    function settle() {
      signal.removeEventListener('abort', handleAbort);
      resolve();
    }
    function handleAbort() {
      window.cancelAnimationFrame(rafId);
      settle();
    }
    rafId = window.requestAnimationFrame(settle);
    signal.addEventListener('abort', handleAbort, { once: true });
  });

interface LoadWaiter {
  promise: Promise<void>;
  cancel: () => void;
}

const createLoadWaiter = (element: HTMLElement): LoadWaiter => {
  let settled = false;
  let resolvePromise = () => {};

  function cleanup() {
    element.removeEventListener('load', settle);
    element.removeEventListener('error', settle);
  }
  function settle() {
    if (settled) {
      return;
    }
    settled = true;
    cleanup();
    resolvePromise();
  }
  const promise = new Promise<void>(resolve => {
    resolvePromise = resolve;
    element.addEventListener('load', settle, { once: true });
    element.addEventListener('error', settle, { once: true });
  });

  return { promise, cancel: settle };
};

const decodeImage = async (image: HTMLImageElement) => {
  if (typeof image.decode !== 'function') {
    return;
  }
  try {
    await image.decode();
  } catch {
    // A failed decode still leaves the browser's broken-image fallback printable.
  }
};

const shouldWaitForIframe = (iframe: HTMLIFrameElement) => {
  try {
    return Boolean(
      iframe.contentDocument &&
      iframe.contentDocument.readyState !== 'complete',
    );
  } catch {
    return false;
  }
};

const waitForPrintAssets = async (root: HTMLElement, signal: AbortSignal) => {
  const waiters: LoadWaiter[] = [];
  const imageReady = Array.from(root.querySelectorAll('img')).map(image => {
    if (image.complete) {
      return decodeImage(image);
    }
    const waiter = createLoadWaiter(image);
    waiters.push(waiter);
    return waiter.promise.then(() => decodeImage(image));
  });
  const iframeReady = Array.from(root.querySelectorAll('iframe'))
    .filter(shouldWaitForIframe)
    .map(iframe => {
      const waiter = createLoadWaiter(iframe);
      waiters.push(waiter);
      return waiter.promise;
    });
  const fontReady = (document.fonts?.ready ?? Promise.resolve()).catch(
    () => undefined,
  );

  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  let handleAbort = () => {};
  const result = await Promise.race([
    Promise.all([fontReady, ...imageReady, ...iframeReady]).then(
      () => 'ready' as const,
    ),
    new Promise<'timeout'>(resolve => {
      timeoutId = setTimeout(
        () => resolve('timeout'),
        PRINT_ASSET_WAIT_TIMEOUT_MS,
      );
    }),
    new Promise<'aborted'>(resolve => {
      handleAbort = () => resolve('aborted');
      signal.addEventListener('abort', handleAbort, { once: true });
    }),
  ]);

  if (timeoutId) {
    clearTimeout(timeoutId);
  }
  signal.removeEventListener('abort', handleAbort);
  waiters.forEach(waiter => waiter.cancel());

  return result;
};

const waitForPrintDomToSettle = (root: HTMLElement, signal: AbortSignal) => {
  if (
    signal.aborted ||
    !root.querySelector(ASYNC_PRINT_CONTENT_SELECTOR) ||
    typeof MutationObserver === 'undefined'
  ) {
    return Promise.resolve(signal.aborted ? 'aborted' : 'ready');
  }

  return new Promise<'ready' | 'timeout' | 'aborted'>(resolve => {
    const startedAt = Date.now();
    let lastMutationAt = startedAt;
    let quietTimer: ReturnType<typeof setTimeout> | undefined;
    let settled = false;

    const cleanup = () => {
      observer.disconnect();
      if (quietTimer) {
        clearTimeout(quietTimer);
      }
      if (timeoutTimer) {
        clearTimeout(timeoutTimer);
      }
      signal.removeEventListener('abort', handleAbort);
    };
    const finish = (result: 'ready' | 'timeout' | 'aborted') => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve(result);
    };
    const scheduleQuietCheck = () => {
      if (quietTimer) {
        clearTimeout(quietTimer);
      }
      const elapsed = Date.now() - startedAt;
      const waitMs = Math.max(
        PRINT_DOM_QUIET_MS,
        PRINT_DOM_MIN_SETTLE_MS - elapsed,
      );
      quietTimer = setTimeout(() => {
        const now = Date.now();
        if (
          now - startedAt >= PRINT_DOM_MIN_SETTLE_MS &&
          now - lastMutationAt >= PRINT_DOM_QUIET_MS
        ) {
          finish('ready');
          return;
        }
        scheduleQuietCheck();
      }, waitMs);
    };
    const observer = new MutationObserver(() => {
      lastMutationAt = Date.now();
      scheduleQuietCheck();
    });
    const handleAbort = () => finish('aborted');
    const timeoutTimer = setTimeout(
      () => finish('timeout'),
      PRINT_DOM_WAIT_TIMEOUT_MS,
    );

    observer.observe(root, {
      attributes: true,
      characterData: true,
      childList: true,
      subtree: true,
    });
    signal.addEventListener('abort', handleAbort, { once: true });
    scheduleQuietCheck();
  });
};

const preparePrintEmbeds = (root: HTMLElement) => {
  const elementStates = Array.from(
    root.querySelectorAll<HTMLImageElement | HTMLIFrameElement>('img, iframe'),
  ).map(element => ({
    element,
    loading: element.getAttribute('loading'),
  }));

  elementStates.forEach(({ element }) => {
    element.setAttribute('loading', 'eager');
  });

  return () => {
    elementStates.forEach(({ element, loading }) => {
      if (loading === null) {
        element.removeAttribute('loading');
        return;
      }
      element.setAttribute('loading', loading);
    });
  };
};

const waitForPrintDialogToClose = (signal: AbortSignal) =>
  new Promise<void>(resolve => {
    let settled = false;
    let printMediaSeen = false;
    const printMedia =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('print')
        : null;
    const supportsModernMediaListener = Boolean(
      printMedia && typeof printMedia.addEventListener === 'function',
    );

    const cleanup = () => {
      window.removeEventListener('afterprint', settle);
      signal.removeEventListener('abort', settle);
      if (supportsModernMediaListener) {
        printMedia?.removeEventListener('change', handlePrintMediaChange);
      } else {
        printMedia?.removeListener?.(handlePrintMediaChange);
      }
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
    const settle = () => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve();
    };
    const handlePrintMediaChange = (event: MediaQueryListEvent) => {
      if (event.matches) {
        printMediaSeen = true;
        return;
      }
      if (printMediaSeen) {
        settle();
      }
    };
    const timeoutId = setTimeout(settle, PRINT_DIALOG_FALLBACK_MS);

    window.addEventListener('afterprint', settle, { once: true });
    signal.addEventListener('abort', settle, { once: true });
    if (supportsModernMediaListener) {
      printMedia?.addEventListener('change', handlePrintMediaChange);
    } else {
      printMedia?.addListener?.(handlePrintMediaChange);
    }
  });

const sanitizeTitlePart = (value: string) =>
  value
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, ' ')
    .trim();

const buildPrintTitle = (courseName: string, lessonTitle: string) =>
  [courseName, lessonTitle].map(sanitizeTitlePart).filter(Boolean).join(' - ');

interface UseLessonPdfPrintOptions {
  printRootRef: RefObject<HTMLElement | null>;
  lessonId: string;
  courseName: string;
  lessonTitle: string;
  onError: () => void;
}

export const useLessonPdfPrint = ({
  printRootRef,
  lessonId,
  courseName,
  lessonTitle,
  onError,
}: UseLessonPdfPrintOptions) => {
  const [isPreparing, setIsPreparing] = useState(false);
  const inProgressRef = useRef(false);
  const mountedRef = useRef(true);
  const operationSerialRef = useRef(0);
  const cleanupRef = useRef<(() => void) | null>(null);
  const printIdentity = `${lessonId}\u0000${courseName}\u0000${lessonTitle}`;
  const previousPrintIdentityRef = useRef(printIdentity);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cleanupRef.current?.();
    };
  }, []);

  useEffect(() => {
    if (previousPrintIdentityRef.current !== printIdentity) {
      cleanupRef.current?.();
      previousPrintIdentityRef.current = printIdentity;
    }
  }, [printIdentity]);

  const printLessonPdf = useCallback(async () => {
    if (inProgressRef.current || typeof window === 'undefined') {
      return;
    }

    const operationId = operationSerialRef.current + 1;
    operationSerialRef.current = operationId;
    const abortController = new AbortController();
    inProgressRef.current = true;
    setIsPreparing(true);

    const originalTitle = document.title;
    let printStateApplied = false;
    let cleaned = false;
    let restorePrintEmbeds = () => {};

    const isOperationActive = () =>
      mountedRef.current &&
      !cleaned &&
      !abortController.signal.aborted &&
      operationSerialRef.current === operationId;

    const cleanup = () => {
      if (cleaned) {
        return;
      }
      cleaned = true;
      abortController.abort();

      if (printStateApplied) {
        document.documentElement.classList.remove(LESSON_PDF_PRINT_CLASS);
        document.title = originalTitle;
      }
      restorePrintEmbeds();

      if (cleanupRef.current === cleanup) {
        cleanupRef.current = null;
      }
      if (operationSerialRef.current === operationId) {
        operationSerialRef.current += 1;
      }
      inProgressRef.current = false;
      if (mountedRef.current) {
        setIsPreparing(false);
      }
    };

    cleanupRef.current = cleanup;

    try {
      // Give React time to reveal every collapsed follow-up before waiting for
      // MarkdownFlow's asynchronous diagrams and embeds.
      await waitForNextPaint(abortController.signal);
      await waitForNextPaint(abortController.signal);
      if (!isOperationActive()) {
        return;
      }

      const printRoot = printRootRef.current;
      if (!printRoot || typeof window.print !== 'function') {
        throw new Error('Lesson print view is unavailable');
      }

      const printTitle = buildPrintTitle(courseName, lessonTitle);
      if (printTitle) {
        document.title = printTitle;
      }
      document.documentElement.classList.add(LESSON_PDF_PRINT_CLASS);
      printStateApplied = true;

      const initialDomState = await waitForPrintDomToSettle(
        printRoot,
        abortController.signal,
      );
      if (!isOperationActive()) {
        return;
      }
      if (initialDomState !== 'ready') {
        throw new Error('Lesson content did not finish rendering');
      }

      restorePrintEmbeds = preparePrintEmbeds(printRoot);
      const assetState = await waitForPrintAssets(
        printRoot,
        abortController.signal,
      );
      if (!isOperationActive()) {
        return;
      }
      if (assetState !== 'ready') {
        throw new Error('Lesson assets did not finish loading');
      }

      const finalDomState = await waitForPrintDomToSettle(
        printRoot,
        abortController.signal,
      );
      if (!isOperationActive()) {
        return;
      }
      if (finalDomState !== 'ready') {
        throw new Error('Lesson content did not stabilize');
      }

      const printDialogClosed = waitForPrintDialogToClose(
        abortController.signal,
      );
      window.print();
      await printDialogClosed;
    } catch {
      if (isOperationActive()) {
        onError();
      }
    } finally {
      cleanup();
    }
  }, [courseName, lessonTitle, onError, printRootRef]);

  return {
    isPreparing,
    printLessonPdf,
  };
};
