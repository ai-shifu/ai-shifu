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
const SANDBOX_IFRAME_SELECTOR =
  '.content-render-iframe-sandbox > iframe.content-render-iframe, .content-render-iframe-sandbox > iframe';
const IFRAME_PRINT_SNAPSHOT_ATTRIBUTE = 'data-lesson-print-iframe-snapshot';
const ASYNC_PRINT_CONTENT_SELECTOR = [
  '.content-render-mermaid',
  '.content-render-mermaid-inner',
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

interface SandboxIframeDocument {
  iframe: HTMLIFrameElement;
  iframeDocument: Document;
}

const getSandboxIframes = (root: HTMLElement) =>
  Array.from(root.querySelectorAll<HTMLIFrameElement>(SANDBOX_IFRAME_SELECTOR));

const getAccessibleSandboxIframeDocuments = (root: HTMLElement) =>
  getSandboxIframes(root).flatMap<SandboxIframeDocument>(iframe => {
    try {
      return iframe.contentDocument
        ? [{ iframe, iframeDocument: iframe.contentDocument }]
        : [];
    } catch {
      return [];
    }
  });

const waitForPrintAssets = async (
  root: HTMLElement,
  signal: AbortSignal,
  extraRoots: ParentNode[] = [],
) => {
  const waiters: LoadWaiter[] = [];
  const iframeDocuments = getAccessibleSandboxIframeDocuments(root);
  const assetRoots: ParentNode[] = [
    root,
    ...iframeDocuments.flatMap(({ iframeDocument }) =>
      iframeDocument.body ? [iframeDocument.body] : [],
    ),
    ...extraRoots,
  ];
  const images = Array.from(
    new Set(
      assetRoots.flatMap(assetRoot =>
        Array.from(assetRoot.querySelectorAll<HTMLImageElement>('img')),
      ),
    ),
  );
  const imageReady = images.map(image => {
    if (image.complete) {
      return decodeImage(image);
    }
    const waiter = createLoadWaiter(image);
    waiters.push(waiter);
    return waiter.promise.then(() => decodeImage(image));
  });
  const stylesheetReady = extraRoots
    .flatMap(extraRoot =>
      Array.from(
        extraRoot.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]'),
      ),
    )
    .filter(link => !link.sheet)
    .map(link => {
      const waiter = createLoadWaiter(link);
      waiters.push(waiter);
      return waiter.promise;
    });
  const iframeReady = Array.from(root.querySelectorAll('iframe'))
    .filter(shouldWaitForIframe)
    .map(iframe => {
      const waiter = createLoadWaiter(iframe);
      waiters.push(waiter);
      return waiter.promise;
    });
  const fontDocuments = [
    document,
    ...iframeDocuments.map(({ iframeDocument }) => iframeDocument),
  ];

  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  let handleAbort = () => {};
  const result = await Promise.race([
    Promise.all([...imageReady, ...stylesheetReady, ...iframeReady])
      .then(() =>
        Promise.all(
          fontDocuments.map(assetDocument =>
            (assetDocument.fonts?.ready ?? Promise.resolve()).catch(
              () => undefined,
            ),
          ),
        ),
      )
      .then(() => 'ready' as const),
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
  const iframeDocuments = getAccessibleSandboxIframeDocuments(root);
  if (
    signal.aborted ||
    (!root.querySelector(ASYNC_PRINT_CONTENT_SELECTOR) &&
      iframeDocuments.length === 0) ||
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
    const areSandboxIframesReady = () =>
      iframeDocuments.every(({ iframeDocument }) => {
        const sandboxWrapper = iframeDocument.querySelector('.sandbox-wrapper');
        return (
          sandboxWrapper !== null &&
          sandboxWrapper.getAttribute('aria-busy') !== 'true'
        );
      });
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
          now - lastMutationAt >= PRINT_DOM_QUIET_MS &&
          areSandboxIframesReady()
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
    iframeDocuments.forEach(({ iframeDocument }) => {
      if (iframeDocument.body) {
        observer.observe(iframeDocument.body, {
          attributes: true,
          characterData: true,
          childList: true,
          subtree: true,
        });
      }
    });
    signal.addEventListener('abort', handleAbort, { once: true });
    scheduleQuietCheck();
  });
};

const PRINT_SNAPSHOT_STYLES = `
  :host {
    display: block;
    width: 100%;
    max-width: 100%;
    color-scheme: light;
  }
  html,
  body {
    width: 100% !important;
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    margin: 0;
    padding: 0;
    overflow: visible !important;
  }
  #root,
  .sandbox-wrapper,
  .sandbox-container {
    width: 100% !important;
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    overflow: visible !important;
  }
  audio,
  .multi-select-confirm-button,
  .input-container > button,
  .copy-button,
  .content-render-custom-button-after-content {
    display: none !important;
  }
  img,
  svg,
  video,
  canvas,
  table {
    max-width: 100% !important;
  }
  pre {
    white-space: pre-wrap !important;
    overflow-wrap: anywhere;
  }
`;

const preparePrintAssets = (root: HTMLElement) => {
  const assetRoots: ParentNode[] = [
    root,
    ...getAccessibleSandboxIframeDocuments(root).flatMap(
      ({ iframeDocument }) =>
        iframeDocument.body ? [iframeDocument.body] : [],
    ),
  ];
  const elementStates = Array.from(
    new Set(
      assetRoots.flatMap(assetRoot =>
        Array.from(
          assetRoot.querySelectorAll<HTMLImageElement | HTMLIFrameElement>(
            'img, iframe',
          ),
        ),
      ),
    ),
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

const copySnapshotCanvasBitmaps = (
  sourceRoot: HTMLElement,
  snapshotRoot: HTMLElement,
) => {
  const sourceCanvases = Array.from(sourceRoot.querySelectorAll('canvas'));
  const snapshotCanvases = Array.from(snapshotRoot.querySelectorAll('canvas'));

  sourceCanvases.forEach((sourceCanvas, index) => {
    const snapshotCanvas = snapshotCanvases[index];
    if (!snapshotCanvas) {
      return;
    }
    try {
      snapshotCanvas.width = sourceCanvas.width;
      snapshotCanvas.height = sourceCanvas.height;
      snapshotCanvas
        .getContext('2d')
        ?.drawImage(
          sourceCanvas,
          0,
          0,
          sourceCanvas.width,
          sourceCanvas.height,
        );
    } catch {
      // Keep the cloned canvas if the browser cannot copy its current bitmap.
    }
  });
};

const copySnapshotFormState = (
  sourceRoot: HTMLElement,
  snapshotRoot: HTMLElement,
) => {
  const sourceFields = Array.from(
    sourceRoot.querySelectorAll<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >('input, textarea, select'),
  );
  const snapshotFields = Array.from(
    snapshotRoot.querySelectorAll<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >('input, textarea, select'),
  );

  sourceFields.forEach((sourceField, index) => {
    const snapshotField = snapshotFields[index];
    if (!snapshotField || sourceField.tagName !== snapshotField.tagName) {
      return;
    }
    if (sourceField.tagName === 'INPUT') {
      const sourceInput = sourceField as HTMLInputElement;
      const snapshotInput = snapshotField as HTMLInputElement;
      if (sourceInput.type !== 'file') {
        snapshotInput.value = sourceInput.value;
      }
      snapshotInput.checked = sourceInput.checked;
      return;
    }
    if (sourceField.tagName === 'TEXTAREA') {
      const sourceTextarea = sourceField as HTMLTextAreaElement;
      const snapshotTextarea = snapshotField as HTMLTextAreaElement;
      snapshotTextarea.value = sourceTextarea.value;
      snapshotTextarea.textContent = sourceTextarea.value;
      return;
    }
    if (sourceField.tagName === 'SELECT') {
      const sourceSelect = sourceField as HTMLSelectElement;
      const snapshotSelect = snapshotField as HTMLSelectElement;
      Array.from(sourceSelect.options).forEach((sourceOption, optionIndex) => {
        const snapshotOption = snapshotSelect.options[optionIndex];
        if (snapshotOption) {
          snapshotOption.selected = sourceOption.selected;
        }
      });
      if (!sourceSelect.multiple) {
        snapshotSelect.selectedIndex = sourceSelect.selectedIndex;
      }
    }
  });
};

const copyElementAttributes = (source: Element, target: Element) => {
  Array.from(source.attributes).forEach(attribute => {
    target.setAttribute(attribute.name, attribute.value);
  });
};

interface IframePrintSnapshots {
  assetRoots: ShadowRoot[];
  cleanup: () => void;
}

const createIframePrintSnapshots = (
  root: HTMLElement,
): IframePrintSnapshots | null => {
  const sandboxIframes = getSandboxIframes(root);
  const snapshots: HTMLElement[] = [];
  const assetRoots: ShadowRoot[] = [];

  sandboxIframes.forEach(iframe => {
    try {
      const iframeDocument = iframe.contentDocument;
      const iframeWindow = iframe.contentWindow;
      const iframeRoot = iframeDocument?.getElementById('root');
      const wrapper = iframe.closest<HTMLElement>(
        '.content-render-iframe-sandbox',
      );
      if (!iframeDocument || !iframeWindow || !iframeRoot || !wrapper) {
        return;
      }

      const snapshot = document.createElement('div');
      snapshot.setAttribute(IFRAME_PRINT_SNAPSHOT_ATTRIBUTE, 'true');
      const bodyStyle = iframeWindow.getComputedStyle(iframeDocument.body);
      const documentStyle = iframeWindow.getComputedStyle(
        iframeDocument.documentElement,
      );
      snapshot.style.setProperty('font-family', bodyStyle.fontFamily);
      snapshot.style.setProperty('font-size', bodyStyle.fontSize);
      snapshot.style.setProperty('line-height', bodyStyle.lineHeight);
      snapshot.style.setProperty('color', bodyStyle.color);
      Array.from(documentStyle).forEach(property => {
        if (property.startsWith('--')) {
          snapshot.style.setProperty(
            property,
            documentStyle.getPropertyValue(property),
          );
        }
      });

      const shadowRoot = snapshot.attachShadow({ mode: 'open' });
      const snapshotStyles = document.createElement('style');
      snapshotStyles.textContent = PRINT_SNAPSHOT_STYLES;
      shadowRoot.appendChild(snapshotStyles);
      iframeDocument
        .querySelectorAll('head style, head link[rel="stylesheet"]')
        .forEach(styleElement => {
          shadowRoot.appendChild(document.importNode(styleElement, true));
        });

      const snapshotRoot = document.importNode(iframeRoot, true);
      copySnapshotCanvasBitmaps(iframeRoot, snapshotRoot);
      copySnapshotFormState(iframeRoot, snapshotRoot);
      const snapshotHtml = document.createElement('html');
      const snapshotBody = document.createElement('body');
      copyElementAttributes(iframeDocument.documentElement, snapshotHtml);
      copyElementAttributes(iframeDocument.body, snapshotBody);
      snapshotBody.appendChild(snapshotRoot);
      snapshotHtml.appendChild(snapshotBody);
      shadowRoot.appendChild(snapshotHtml);
      wrapper.insertAdjacentElement('afterend', snapshot);
      snapshots.push(snapshot);
      assetRoots.push(shadowRoot);
    } catch {
      // A missing same-origin document is handled as a preparation failure.
    }
  });

  if (snapshots.length !== sandboxIframes.length) {
    snapshots.forEach(snapshot => snapshot.remove());
    return null;
  }

  return {
    assetRoots,
    cleanup: () => snapshots.forEach(snapshot => snapshot.remove()),
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
    let restorePrintAssets = () => {};
    let cleanupPrintSnapshots = () => {};

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
      cleanupPrintSnapshots();
      restorePrintAssets();

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

      restorePrintAssets = preparePrintAssets(printRoot);
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

      const iframeSnapshots = createIframePrintSnapshots(printRoot);
      if (!iframeSnapshots) {
        throw new Error('Lesson embeds could not be prepared for printing');
      }
      cleanupPrintSnapshots = iframeSnapshots.cleanup;
      if (iframeSnapshots.assetRoots.length > 0) {
        await waitForNextPaint(abortController.signal);
        if (!isOperationActive()) {
          return;
        }
        const snapshotAssetState = await waitForPrintAssets(
          printRoot,
          abortController.signal,
          iframeSnapshots.assetRoots,
        );
        if (!isOperationActive()) {
          return;
        }
        if (snapshotAssetState !== 'ready') {
          throw new Error('Lesson print snapshots did not finish loading');
        }
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
