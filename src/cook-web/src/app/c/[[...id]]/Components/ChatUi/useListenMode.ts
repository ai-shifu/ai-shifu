import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Reveal, { Options } from 'reveal.js';
import { type RenderSegment } from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import {
  warmupSharedAudioPlayback,
  type AudioPlayerHandle,
} from '@/components/audio/AudioPlayer';
import type { AudioSegment } from '@/c-utils/audio-utils';
import type { ListenSlideData } from '@/c-api/studyV2';
import {
  FIXED_MARKER_PATTERN,
  resolveListenAudioTrack,
} from '@/c-utils/listen-mode';
import {
  buildListenTimeline,
  type AudioInteractionItem,
  type ListenSlideItem,
} from '@/c-utils/listen-parse/timeline-mapper';
import { useQueueManager } from '@/c-utils/listen-mode/use-queue-manager';
import {
  buildQueueItemId,
  type QueueEvent,
  type VisualQueueItem,
  type AudioQueueItem,
  type InteractionQueueItem,
} from '@/c-utils/listen-mode/queue-manager';
import { hasInteractionResponse } from './chatUiUtils';

export type { AudioInteractionItem, ListenSlideItem };

const EMPTY_SANDBOX_WRAPPER_PATTERN =
  /^<div(?:\s+[^>]*)?>\s*(?:<br\s*\/?>|&nbsp;|\s)*<\/div>$/i;
const EMPTY_SVG_PATTERN = /^<svg\b[^>]*>\s*(?:<!--[\s\S]*?-->\s*)*<\/svg>$/i;
const EMPTY_WRAPPED_SVG_PATTERN =
  /^<div(?:\s+[^>]*)?>\s*<svg\b[^>]*>\s*(?:<!--[\s\S]*?-->\s*)*<\/svg>\s*<\/div>$/i;
const MALFORMED_EMPTY_SVG_PATTERN = /<svg<|<\/svg<>/i;
const VISUAL_HTML_TAG_PATTERN = /<(svg|table|iframe|img|video)\b/i;
const MARKDOWN_IMAGE_PATTERN = /!\[[^\]]*]\([^)]+\)/;
const MERMAID_CODE_FENCE_PATTERN = /```[\t ]*mermaid\b/i;
const RUNTIME_VISUAL_CONTENT_SELECTOR =
  'svg,table,img,video,canvas,.mermaid,iframe[src],iframe[srcdoc],iframe[data-url],iframe[data-tag],object,embed';
const RUNTIME_SANDBOX_CONTAINER_SELECTOR = '.sandbox-container';
const RUNTIME_PRUNED_SLIDE_CLASS = 'listen-runtime-pruned-slide';
const RUNTIME_PRUNED_SLIDE_ATTR = 'data-runtime-pruned';

const normalizeRuntimeTextContent = (
  value: string | null | undefined,
): string =>
  (value || '')
    .replace(/\u00a0/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const isRuntimePrunableElementTree = (root: Element): boolean => {
  if (root.querySelector(RUNTIME_VISUAL_CONTENT_SELECTOR)) {
    return false;
  }

  if (normalizeRuntimeTextContent(root.textContent).length > 0) {
    return false;
  }

  const hasRenderableElement = Array.from(root.childNodes).some(node => {
    if (node.nodeType === Node.TEXT_NODE) {
      return normalizeRuntimeTextContent(node.textContent).length > 0;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return false;
    }
    const elementNode = node as Element;
    const tagName = elementNode.tagName.toLowerCase();
    if (tagName === 'br') {
      return false;
    }
    if (tagName === 'iframe') {
      return Boolean(
        elementNode.getAttribute('src') ||
        elementNode.getAttribute('srcdoc') ||
        elementNode.getAttribute('data-url') ||
        elementNode.getAttribute('data-tag'),
      );
    }
    if (normalizeRuntimeTextContent(elementNode.textContent).length > 0) {
      return true;
    }
    if (elementNode.childElementCount === 0) {
      return false;
    }
    // Recurse for wrapper-only trees (for example <div><div></div></div>)
    // so empty nested containers do not count as renderable visuals.
    return !isRuntimePrunableElementTree(elementNode);
  });

  return !hasRenderableElement;
};

const isRuntimePrunableSandboxIframe = (
  iframe: HTMLIFrameElement,
): boolean | null => {
  const iframeDocument = iframe.contentDocument;
  if (!iframeDocument) {
    const hasSourceHint = Boolean(
      iframe.getAttribute('src') ||
      iframe.getAttribute('srcdoc') ||
      iframe.getAttribute('data-url') ||
      iframe.getAttribute('data-tag'),
    );
    // src-less sandbox iframes without a document are typically transient empty
    // placeholders and should not reserve a visual page.
    return hasSourceHint ? null : true;
  }

  const sandboxContainer = iframeDocument.querySelector(
    RUNTIME_SANDBOX_CONTAINER_SELECTOR,
  );
  // NOTE:
  // sandboxContainer lives in iframeDocument (different JS realm).
  // Cross-realm `instanceof HTMLElement` checks fail, so rely on nodeType/tagName.
  if (sandboxContainer && sandboxContainer.nodeType === Node.ELEMENT_NODE) {
    return isRuntimePrunableElementTree(sandboxContainer as Element);
  }

  // Some renderer variants mount directly into body without sandbox-container.
  // If the iframe document exists but has no renderable content, prune it.
  const iframeBody = iframeDocument.body;
  if (!iframeBody || iframeBody.nodeType !== Node.ELEMENT_NODE) {
    return true;
  }
  return isRuntimePrunableElementTree(iframeBody as Element);
};

const isRenderableVisualSegment = (segment: RenderSegment): boolean => {
  if (segment.type !== 'markdown' && segment.type !== 'sandbox') {
    return false;
  }

  const raw = typeof segment.value === 'string' ? segment.value.trim() : '';
  if (!raw) {
    return false;
  }
  if (FIXED_MARKER_PATTERN.test(raw)) {
    return false;
  }
  if (EMPTY_SANDBOX_WRAPPER_PATTERN.test(raw)) {
    return false;
  }
  if (EMPTY_SVG_PATTERN.test(raw) || EMPTY_WRAPPED_SVG_PATTERN.test(raw)) {
    return false;
  }
  if (MALFORMED_EMPTY_SVG_PATTERN.test(raw)) {
    return false;
  }
  if (VISUAL_HTML_TAG_PATTERN.test(raw)) {
    return true;
  }

  if (segment.type === 'markdown') {
    return (
      MARKDOWN_IMAGE_PATTERN.test(raw) || MERMAID_CODE_FENCE_PATTERN.test(raw)
    );
  }

  const textContent = raw
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/gi, '')
    .trim();
  return textContent.length > 0;
};

const isRuntimePrunableVisualSlide = (slide: unknown): boolean => {
  if (
    !slide ||
    typeof HTMLElement === 'undefined' ||
    !(slide instanceof HTMLElement)
  ) {
    return false;
  }

  const slideIframes = Array.from(slide.querySelectorAll('iframe'));
  if (slideIframes.length > 0) {
    let hasPrunableIframe = false;
    for (const node of slideIframes) {
      if (!(node instanceof HTMLIFrameElement)) {
        continue;
      }
      const isPrunableSandbox = isRuntimePrunableSandboxIframe(node);
      if (isPrunableSandbox === null) {
        continue;
      }
      if (!isPrunableSandbox) {
        return false;
      }
      hasPrunableIframe = true;
    }
    if (hasPrunableIframe && isRuntimePrunableElementTree(slide)) {
      return true;
    }
  }

  // Some renderer edge-cases may emit an empty <section> with no iframe/text.
  // Treat these as runtime-prunable blank pages to keep reveal navigation stable.
  if (slide.childElementCount === 0) {
    return normalizeRuntimeTextContent(slide.textContent).length === 0;
  }

  if (slide.querySelector(RUNTIME_VISUAL_CONTENT_SELECTOR)) {
    return false;
  }

  return isRuntimePrunableElementTree(slide);
};

const applyRuntimePrunedSlideState = (
  slide: unknown,
  shouldPrune: boolean,
): void => {
  if (typeof HTMLElement === 'undefined' || !(slide instanceof HTMLElement)) {
    return;
  }

  if (shouldPrune) {
    slide.classList.add(RUNTIME_PRUNED_SLIDE_CLASS);
    slide.setAttribute(RUNTIME_PRUNED_SLIDE_ATTR, '1');
    slide.setAttribute('aria-hidden', 'true');
    return;
  }

  slide.classList.remove(RUNTIME_PRUNED_SLIDE_CLASS);
  slide.removeAttribute(RUNTIME_PRUNED_SLIDE_ATTR);
  slide.removeAttribute('aria-hidden');
};

const buildRuntimePageRemap = (
  slides: unknown[],
  preferredPage?: number,
): Map<number, number> => {
  const remap = new Map<number, number>();
  if (!slides.length) {
    return remap;
  }

  const prunableByPage = slides.map(isRuntimePrunableVisualSlide);
  slides.forEach((slide, page) => {
    applyRuntimePrunedSlideState(slide, prunableByPage[page]);
  });

  const playablePages: number[] = [];
  prunableByPage.forEach((shouldPrune, page) => {
    if (!shouldPrune) {
      playablePages.push(page);
    }
  });

  if (!playablePages.length) {
    // Keep exactly one fallback slide visible when runtime content is still
    // streaming; otherwise Reveal can get stuck showing a fully pruned deck.
    const fallbackPage =
      Number.isFinite(preferredPage) &&
      typeof preferredPage === 'number' &&
      preferredPage >= 0 &&
      preferredPage < slides.length
        ? preferredPage
        : 0;
    slides.forEach((slide, page) => {
      applyRuntimePrunedSlideState(slide, page !== fallbackPage);
      remap.set(page, fallbackPage);
    });
    return remap;
  }

  slides.forEach((_, page) => {
    if (!prunableByPage[page]) {
      remap.set(page, page);
      return;
    }

    let nextPlayablePage = -1;
    for (let i = 0; i < playablePages.length; i += 1) {
      if (playablePages[i] > page) {
        nextPlayablePage = playablePages[i];
        break;
      }
    }

    if (nextPlayablePage >= 0) {
      remap.set(page, nextPlayablePage);
      return;
    }

    let previousPlayablePage = -1;
    for (let i = playablePages.length - 1; i >= 0; i -= 1) {
      if (playablePages[i] < page) {
        previousPlayablePage = playablePages[i];
        break;
      }
    }
    remap.set(
      page,
      previousPlayablePage >= 0 ? previousPlayablePage : playablePages[0],
    );
  });

  return remap;
};

const arePageRemapMapsEqual = (
  currentMap: Map<number, number>,
  nextMap: Map<number, number>,
): boolean => {
  if (currentMap.size !== nextMap.size) {
    return false;
  }
  for (const [page, mappedPage] of nextMap.entries()) {
    if (currentMap.get(page) !== mappedPage) {
      return false;
    }
  }
  return true;
};

const LISTEN_AUDIO_WATCHDOG_MIN_MS = 8000;
const LISTEN_AUDIO_WATCHDOG_FALLBACK_MS = 20000;
const LISTEN_AUDIO_WATCHDOG_DURATION_MULTIPLIER = 2;
const LISTEN_PENDING_GROWTH_WAIT_MS = 10000;
const LISTEN_PENDING_AUTO_NEXT_GRACE_MS = 90000;

const resolveListenAudioWatchdogMs = (audioDurationMs?: number) => {
  const duration = Number(audioDurationMs);
  if (Number.isFinite(duration) && duration > 0) {
    return Math.max(
      LISTEN_AUDIO_WATCHDOG_MIN_MS,
      Math.floor(duration * LISTEN_AUDIO_WATCHDOG_DURATION_MULTIPLIER),
    );
  }
  return LISTEN_AUDIO_WATCHDOG_FALLBACK_MS;
};

export const useListenContentData = (
  items: ChatContentItem[],
  backendSlides?: ListenSlideData[],
) => {
  const orderedContentBlockBids = useMemo(() => {
    const seen = new Set<string>();
    const bids: string[] = [];
    for (const item of items) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      const bid = item.generated_block_bid;
      if (!bid || bid === 'loading') {
        continue;
      }
      if (seen.has(bid)) {
        continue;
      }
      seen.add(bid);
      bids.push(bid);
    }
    return bids;
  }, [items]);

  const { slideItems, audioAndInteractionList } = useMemo(
    () =>
      buildListenTimeline({
        items,
        backendSlides,
        isRenderableVisualSegment,
      }),
    [backendSlides, items],
  );

  const contentByBid = useMemo(() => {
    const mapping = new Map<string, ChatContentItem>();
    for (const item of items) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      const bid = item.generated_block_bid;
      if (!bid || bid === 'loading') {
        continue;
      }
      mapping.set(bid, item);
    }
    return mapping;
  }, [items]);

  const audioContentByBid = useMemo(() => {
    const mapping = new Map<string, ChatContentItem>();
    for (const item of audioAndInteractionList) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      const bid = item.generated_block_bid;
      if (!bid || bid === 'loading') {
        continue;
      }
      mapping.set(bid, item);
    }
    return mapping;
  }, [audioAndInteractionList]);

  const firstContentItem = useMemo(() => {
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (
        item.type === ChatContentItemType.CONTENT &&
        item.generated_block_bid &&
        item.generated_block_bid !== 'loading'
      ) {
        return item;
      }
    }
    return null;
  }, [items]);

  return {
    orderedContentBlockBids,
    slideItems,
    audioAndInteractionList,
    contentByBid,
    audioContentByBid,
    firstContentItem,
  };
};

interface UseListenPptParams {
  chatRef: React.RefObject<HTMLDivElement>;
  deckRef: React.MutableRefObject<Reveal.Api | null>;
  currentPptPageRef: React.MutableRefObject<number>;
  activeBlockBidRef: React.MutableRefObject<string | null>;
  pendingAutoNextRef: React.MutableRefObject<boolean>;
  slideItems: ListenSlideItem[];
  sectionTitle?: string;
  isLoading: boolean;
  isAudioPlaying: boolean;
  isAudioSequenceActive: boolean;
  isAudioPlayerBusy: () => boolean;
  shouldRenderEmptyPpt: boolean;
  onResetSequence: () => void;
  getNextContentBid: (currentBid: string | null) => string | null;
  goToBlock: (blockBid: string) => boolean;
  resolveContentBid: (blockBid: string | null) => string | null;
  resolveRuntimeSequencePage: (page: number) => number;
  refreshRuntimePageRemap: () => void;
}

export const useListenPpt = ({
  chatRef,
  deckRef,
  currentPptPageRef,
  activeBlockBidRef,
  pendingAutoNextRef,
  slideItems,
  sectionTitle,
  isLoading,
  isAudioPlaying,
  isAudioSequenceActive,
  isAudioPlayerBusy,
  shouldRenderEmptyPpt,
  onResetSequence,
  getNextContentBid,
  goToBlock,
  resolveContentBid,
  resolveRuntimeSequencePage,
  refreshRuntimePageRemap,
}: UseListenPptParams) => {
  const shouldSlideToFirstRef = useRef(false);
  const prevFirstSlideBidRef = useRef<string | null>(null);
  const prevSectionTitleRef = useRef<string | null>(null);
  const [isPrevDisabled, setIsPrevDisabled] = useState(true);
  const [isNextDisabled, setIsNextDisabled] = useState(true);

  const firstSlideBid = useMemo(
    () => slideItems[0]?.item.generated_block_bid ?? null,
    [slideItems],
  );

  useEffect(() => {
    if (!firstSlideBid) {
      prevFirstSlideBidRef.current = null;
      return;
    }
    const canResetToFirst =
      !isAudioSequenceActive && !isAudioPlaying && !isAudioPlayerBusy();
    if (!prevFirstSlideBidRef.current) {
      if (canResetToFirst) {
        shouldSlideToFirstRef.current = true;
        onResetSequence();
      }
    } else if (prevFirstSlideBidRef.current !== firstSlideBid) {
      if (canResetToFirst) {
        shouldSlideToFirstRef.current = true;
        onResetSequence();
      }
    }
    prevFirstSlideBidRef.current = firstSlideBid;
  }, [
    firstSlideBid,
    isAudioPlayerBusy,
    isAudioPlaying,
    isAudioSequenceActive,
    onResetSequence,
  ]);

  useEffect(() => {
    if (!sectionTitle) {
      prevSectionTitleRef.current = null;
      return;
    }
    const canResetToFirst =
      !isAudioSequenceActive && !isAudioPlaying && !isAudioPlayerBusy();
    if (
      prevSectionTitleRef.current &&
      prevSectionTitleRef.current !== sectionTitle
    ) {
      if (canResetToFirst) {
        shouldSlideToFirstRef.current = true;
        onResetSequence();
      }
    }
    prevSectionTitleRef.current = sectionTitle;
  }, [
    isAudioPlayerBusy,
    isAudioPlaying,
    isAudioSequenceActive,
    onResetSequence,
    sectionTitle,
  ]);

  const resolveRuntimePptPage = useCallback(
    (page: number) => {
      refreshRuntimePageRemap();
      const mappedPage = resolveRuntimeSequencePage(page);
      if (!Number.isFinite(mappedPage) || mappedPage < 0) {
        return page;
      }
      return mappedPage;
    },
    [refreshRuntimePageRemap, resolveRuntimeSequencePage],
  );

  const syncPptPageFromDeck = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }
    const rawIndex = deck.getIndices()?.h ?? 0;
    const nextIndex = resolveRuntimePptPage(rawIndex);
    if (nextIndex !== rawIndex) {
      try {
        deck.slide(nextIndex);
      } catch {
        // ignore reveal transition errors while pruning runtime-empty pages
      }
      return;
    }
    if (currentPptPageRef.current === nextIndex) {
      return;
    }
    currentPptPageRef.current = nextIndex;
  }, [currentPptPageRef, deckRef, resolveRuntimePptPage]);

  const getBlockBidFromSlide = useCallback((slide: HTMLElement | null) => {
    if (!slide) {
      return null;
    }
    return slide.getAttribute('data-generated-block-bid') || null;
  }, []);

  const syncActiveBlockFromDeck = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }
    const slide = deck.getCurrentSlide?.() as HTMLElement | undefined;
    const nextBid = getBlockBidFromSlide(slide ?? null);
    if (!nextBid || nextBid === activeBlockBidRef.current) {
      return;
    }
    if (shouldRenderEmptyPpt) {
      if (!activeBlockBidRef.current?.startsWith('empty-ppt-')) {
        activeBlockBidRef.current = nextBid;
      }
      return;
    }
    activeBlockBidRef.current = nextBid;
  }, [activeBlockBidRef, deckRef, getBlockBidFromSlide, shouldRenderEmptyPpt]);

  const updateNavState = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      setIsPrevDisabled(true);
      setIsNextDisabled(true);
      return;
    }
    const totalSlides =
      typeof deck.getTotalSlides === 'function' ? deck.getTotalSlides() : 0;
    const indices = deck.getIndices?.();
    const currentIndex = indices?.h ?? 0;
    const isFirstSlide =
      typeof deck.isFirstSlide === 'function'
        ? deck.isFirstSlide()
        : totalSlides <= 1 || currentIndex <= 0;
    const isLastSlide =
      typeof deck.isLastSlide === 'function'
        ? deck.isLastSlide()
        : totalSlides <= 1 || currentIndex >= Math.max(totalSlides - 1, 0);
    setIsPrevDisabled(isFirstSlide);
    setIsNextDisabled(isLastSlide);
  }, [deckRef]);

  const goToNextBlock = useCallback(() => {
    const currentBid = resolveContentBid(activeBlockBidRef.current);
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      return false;
    }
    const moved = goToBlock(nextBid);
    if (moved) {
      activeBlockBidRef.current = nextBid;
    }
    return moved;
  }, [activeBlockBidRef, getNextContentBid, goToBlock, resolveContentBid]);

  useEffect(() => {
    if (!chatRef.current || deckRef.current || isLoading) {
      return;
    }

    if (!slideItems.length) {
      return;
    }

    const slideNodes = chatRef.current.querySelectorAll('.slides > section');
    if (!slideNodes.length) {
      return;
    }

    const revealOptions: Options = {
      width: '100%',
      height: '100%',
      margin: 0,
      minScale: 1,
      maxScale: 1,
      transition: 'slide',
      slideNumber: false,
      progress: false,
      controls: false,
      hideInactiveCursor: false,
      center: false,
      disableLayout: true,
      view: null,
      scrollActivationWidth: 0,
      scrollProgress: false,
      scrollSnap: false,
    };

    deckRef.current = new Reveal(chatRef.current, revealOptions);

    deckRef.current.initialize().then(() => {
      syncActiveBlockFromDeck();
      syncPptPageFromDeck();
      updateNavState();
    });
  }, [
    chatRef,
    deckRef,
    slideItems.length,
    isLoading,
    syncActiveBlockFromDeck,
    syncPptPageFromDeck,
    updateNavState,
  ]);

  useEffect(() => {
    if (!slideItems.length && deckRef.current) {
      try {
        deckRef.current?.destroy();
      } catch {
        // ignore reveal destroy failure
      } finally {
        deckRef.current = null;
        setIsPrevDisabled(true);
        setIsNextDisabled(true);
      }
    }
  }, [deckRef, slideItems.length]);

  useEffect(() => {
    return () => {
      if (!deckRef.current) {
        return;
      }
      try {
        deckRef.current?.destroy();
      } catch {
        // ignore reveal destroy failure
      } finally {
        deckRef.current = null;
      }
    };
  }, [deckRef]);

  useEffect(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }

    const handleSlideChanged: EventListener = () => {
      syncActiveBlockFromDeck();
      syncPptPageFromDeck();
      updateNavState();
    };

    deck.on('slidechanged', handleSlideChanged);
    deck.on('ready', handleSlideChanged);

    return () => {
      deck.off('slidechanged', handleSlideChanged);
      deck.off('ready', handleSlideChanged);
    };
  }, [deckRef, syncActiveBlockFromDeck, syncPptPageFromDeck, updateNavState]);

  useEffect(() => {
    if (!deckRef.current || isLoading) {
      return;
    }
    if (typeof deckRef.current.sync !== 'function') {
      return;
    }
    const slides =
      typeof deckRef.current.getSlides === 'function'
        ? deckRef.current.getSlides()
        : Array.from(
            chatRef.current?.querySelectorAll('.slides > section') || [],
          );
    if (!slides.length) {
      return;
    }
    try {
      deckRef.current.sync();
      deckRef.current.layout();
      // Keep nav state in sync with newly appended slides even while
      // sequence playback is active.
      updateNavState();

      if (shouldSlideToFirstRef.current) {
        deckRef.current.slide(0);
        shouldSlideToFirstRef.current = false;
        updateNavState();
        return;
      }

      if (pendingAutoNextRef.current) {
        const moved = goToNextBlock();
        pendingAutoNextRef.current = !moved;
        if (moved) {
          onResetSequence();
        }
      }

      // During listen sequence playback/preparation/waiting, slide progression
      // should be controlled by the sequence mapping only. Auto-following newly
      // appended slides here causes premature visual jumps.
      if (isAudioSequenceActive || isAudioPlaying || isAudioPlayerBusy()) {
        return;
      }
    } catch {
      // Ignore reveal sync errors
    }
  }, [
    slideItems,
    isAudioSequenceActive,
    isAudioPlaying,
    isAudioPlayerBusy,
    isLoading,
    goToNextBlock,
    chatRef,
    updateNavState,
    deckRef,
    pendingAutoNextRef,
    onResetSequence,
  ]);

  const goPrev = useCallback(() => {
    const deck = deckRef.current;
    if (!deck || isPrevDisabled) {
      return null;
    }
    shouldSlideToFirstRef.current = false;
    deck.prev();
    let nextPage = deck.getIndices().h;
    const resolvedPage = resolveRuntimePptPage(nextPage);
    if (resolvedPage !== nextPage) {
      try {
        deck.slide(resolvedPage);
      } catch {
        return null;
      }
      nextPage = resolvedPage;
    }
    currentPptPageRef.current = nextPage;
    updateNavState();
    return nextPage;
  }, [
    deckRef,
    isPrevDisabled,
    currentPptPageRef,
    resolveRuntimePptPage,
    updateNavState,
  ]);

  const goNext = useCallback(() => {
    const deck = deckRef.current;
    if (!deck || isNextDisabled) {
      return null;
    }
    shouldSlideToFirstRef.current = false;
    deck.next();
    let nextPage = deck.getIndices().h;
    const resolvedPage = resolveRuntimePptPage(nextPage);
    if (resolvedPage !== nextPage) {
      try {
        deck.slide(resolvedPage);
      } catch {
        return null;
      }
      nextPage = resolvedPage;
    }
    currentPptPageRef.current = nextPage;
    updateNavState();
    return nextPage;
  }, [
    deckRef,
    isNextDisabled,
    currentPptPageRef,
    resolveRuntimePptPage,
    updateNavState,
  ]);

  return {
    isPrevDisabled,
    isNextDisabled,
    goPrev,
    goNext,
  };
};

interface UseListenAudioSequenceParams {
  audioAndInteractionList: AudioInteractionItem[];
  deckRef: React.MutableRefObject<Reveal.Api | null>;
  currentPptPageRef: React.MutableRefObject<number>;
  activeBlockBidRef: React.MutableRefObject<string | null>;
  pendingAutoNextRef: React.MutableRefObject<boolean>;
  shouldStartSequenceRef: React.MutableRefObject<boolean>;
  enableInitialAutoStart?: boolean;
  sequenceStartAnchorIndexRef?: React.MutableRefObject<number | null>;
  contentByBid: Map<string, ChatContentItem>;
  audioContentByBid: Map<string, ChatContentItem>;
  previewMode: boolean;
  shouldRenderEmptyPpt: boolean;
  getNextContentBid: (currentBid: string | null) => string | null;
  goToBlock: (blockBid: string) => boolean;
  resolveContentBid: (blockBid: string | null) => string | null;
  isAudioPlaying: boolean;
  setIsAudioPlaying: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useListenAudioSequence = ({
  audioAndInteractionList,
  deckRef,
  currentPptPageRef,
  activeBlockBidRef,
  pendingAutoNextRef,
  shouldStartSequenceRef,
  enableInitialAutoStart = false,
  sequenceStartAnchorIndexRef,
  contentByBid,
  audioContentByBid,
  previewMode,
  shouldRenderEmptyPpt,
  getNextContentBid,
  goToBlock,
  resolveContentBid,
  isAudioPlaying,
  setIsAudioPlaying,
}: UseListenAudioSequenceParams) => {
  // ---------------------------------------------------------------------------
  // React state — preserved from original, same external interface
  // ---------------------------------------------------------------------------
  const audioPlayerRef = useRef<AudioPlayerHandle | null>(null);
  const internalStartAnchorIndexRef = useRef<number | null>(null);
  const effectiveStartAnchorIndexRef =
    sequenceStartAnchorIndexRef || internalStartAnchorIndexRef;
  const [activeAudioBid, setActiveAudioBid] = useState<string | null>(null);
  const [activeAudioPosition, setActiveAudioPosition] = useState(0);
  const [activeQueueAudioId, setActiveQueueAudioId] = useState<string | null>(
    null,
  );
  const [sequenceInteraction, setSequenceInteraction] =
    useState<AudioInteractionItem | null>(null);
  const [isAudioSequenceActive, setIsAudioSequenceActive] = useState(false);
  const [audioSequenceToken, setAudioSequenceToken] = useState(0);
  const audioSequenceTokenRef = useRef(0);
  audioSequenceTokenRef.current = audioSequenceToken;
  const hasObservedPlaybackRef = useRef(false);
  const isSequencePausedRef = useRef(false);
  // Track the last synced list length to detect new items for queue sync
  const lastSyncedListRef = useRef<AudioInteractionItem[]>([]);
  // Track synced audio state per item to avoid duplicate upsertAudio calls.
  // Key: "bid:position", value: { count: segments synced, finalized: true if is_final sent } or 'url'
  const syncedAudioStateRef = useRef<
    Map<string, { count: number; finalized: boolean } | 'url'>
  >(new Map());
  const pendingQueueGrowthAnchorRef = useRef<number | null>(null);
  const pendingGrowthWaitTimerRef = useRef<ReturnType<
    typeof setTimeout
  > | null>(null);
  const hasInitialAutoStartAttemptedRef = useRef(false);
  const lastAdvanceCauseRef = useRef<
    'audio-ended' | 'interaction-resolved' | 'other'
  >('other');
  const runtimePageRemapRef = useRef<Map<number, number>>(new Map());
  const [runtimePageRemapVersion, setRuntimePageRemapVersion] = useState(0);

  // ---------------------------------------------------------------------------
  // Helpers preserved from original
  // ---------------------------------------------------------------------------
  const hasPlayableResolvedTrack = useCallback(
    (resolvedTrack: ReturnType<typeof resolveListenAudioTrack>) => {
      const hasUrl = Boolean(resolvedTrack.audioUrl);
      const hasSegments = Boolean(
        resolvedTrack.audioSegments && resolvedTrack.audioSegments.length > 0,
      );
      return hasUrl || hasSegments || resolvedTrack.isAudioStreaming;
    },
    [],
  );

  const resolveRuntimeSequencePage = useCallback((page: number) => {
    if (!Number.isFinite(page) || page < 0) {
      return page;
    }
    const mappedPage = runtimePageRemapRef.current.get(page);
    if (typeof mappedPage === 'number' && mappedPage >= 0) {
      return mappedPage;
    }
    return page;
  }, []);

  const collectDeckSlides = useCallback((): unknown[] => {
    const deck = deckRef.current;
    if (!deck || typeof deck.getSlides !== 'function') {
      return [];
    }
    const slides = deck.getSlides();
    if (!slides) {
      return [];
    }
    return Array.isArray(slides)
      ? (slides as HTMLElement[])
      : Array.from(slides as ArrayLike<HTMLElement>);
  }, [deckRef]);

  const refreshRuntimePageRemap = useCallback(() => {
    const slides = collectDeckSlides();
    const currentDeckPage = deckRef.current?.getIndices?.().h;
    const nextMap = buildRuntimePageRemap(slides, currentDeckPage);
    if (arePageRemapMapsEqual(runtimePageRemapRef.current, nextMap)) {
      return;
    }
    runtimePageRemapRef.current = nextMap;
    setRuntimePageRemapVersion(version => version + 1);
  }, [collectDeckSlides, deckRef]);

  const syncToSequencePage = useCallback(
    (page: number) => {
      if (page < 0) {
        return;
      }
      refreshRuntimePageRemap();
      const resolvedPage = resolveRuntimeSequencePage(page);
      if (resolvedPage < 0) {
        return;
      }
      const deck = deckRef.current;
      if (!deck) {
        return;
      }

      try {
        if (typeof deck.sync === 'function') {
          deck.sync();
        }
        if (typeof deck.layout === 'function') {
          deck.layout();
        }
      } catch {
        // ignore
      }

      const slidesLength =
        typeof deck.getSlides === 'function'
          ? deck.getSlides().length
          : typeof deck.getTotalSlides === 'function'
            ? deck.getTotalSlides()
            : 0;

      if (slidesLength <= 0) {
        return;
      }
      if (resolvedPage >= slidesLength) {
        return;
      }

      try {
        deck.slide(resolvedPage);
      } catch {
        // Reveal.js may throw if controls are not yet initialized
        return;
      }
    },
    [deckRef, refreshRuntimePageRemap, resolveRuntimeSequencePage],
  );

  const clearPendingGrowthWaitTimer = useCallback(() => {
    if (pendingGrowthWaitTimerRef.current) {
      clearTimeout(pendingGrowthWaitTimerRef.current);
      pendingGrowthWaitTimerRef.current = null;
    }
  }, []);

  const tryAdvanceToNextBlock = useCallback(() => {
    const currentBid =
      resolveContentBid(activeBlockBidRef.current) ||
      resolveContentBid(activeAudioBid);
    if (!currentBid) {
      pendingAutoNextRef.current = true;
      return;
    }
    if (resolveContentBid(activeBlockBidRef.current) !== currentBid) {
      activeBlockBidRef.current = currentBid;
    }
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      pendingAutoNextRef.current = true;
      return;
    }

    const moved = goToBlock(nextBid);
    if (moved) {
      // Hint upcoming sequence resolution to the target block immediately.
      // Reveal's slidechanged callback can lag behind this call.
      activeBlockBidRef.current = nextBid;
      // Signal the bootstrap effect to auto-start the queue once new content
      // for the next block streams in and audioAndInteractionList rebuilds.
      shouldStartSequenceRef.current = true;
      return;
    }

    if (shouldRenderEmptyPpt) {
      activeBlockBidRef.current = `empty-ppt-${nextBid}`;
      return;
    }

    pendingAutoNextRef.current = true;
  }, [
    activeAudioBid,
    activeBlockBidRef,
    getNextContentBid,
    goToBlock,
    pendingAutoNextRef,
    resolveContentBid,
    shouldStartSequenceRef,
    shouldRenderEmptyPpt,
  ]);

  const endSequence = useCallback(
    (options?: { tryAdvanceToNextBlock?: boolean }) => {
      setSequenceInteraction(null);
      setActiveAudioBid(null);
      setActiveAudioPosition(0);
      setActiveQueueAudioId(null);
      setIsAudioSequenceActive(false);
      setIsAudioPlaying(false);
      isSequencePausedRef.current = false;
      if (options?.tryAdvanceToNextBlock) {
        tryAdvanceToNextBlock();
      }
    },
    [setIsAudioPlaying, tryAdvanceToNextBlock],
  );

  const isAudioPlayerBusy = useCallback(() => {
    const state = audioPlayerRef.current?.getPlaybackState?.();
    if (!state) {
      return false;
    }
    return Boolean(
      state.isPlaying || state.isLoading || state.isWaitingForSegment,
    );
  }, []);

  const resolveSequenceStartIndex = useCallback(
    (page: number) => {
      if (!audioAndInteractionList.length) {
        return -1;
      }
      refreshRuntimePageRemap();
      const targetPage = resolveRuntimeSequencePage(page);
      const list = audioAndInteractionList;
      const isContentItem = (item: AudioInteractionItem) =>
        item.type === ChatContentItemType.CONTENT;
      const isAudibleContentItem = (item: AudioInteractionItem) =>
        isContentItem(item) && !item.isSilentVisual;
      const getItemPage = (item: AudioInteractionItem) =>
        resolveRuntimeSequencePage(item.page);

      const currentSlide =
        (deckRef.current?.getCurrentSlide?.() as
          | HTMLElement
          | null
          | undefined) || null;
      const deckCurrentBid = resolveContentBid(
        currentSlide?.getAttribute?.('data-generated-block-bid') || null,
      );
      const preferredBid =
        deckCurrentBid ||
        resolveContentBid(activeBlockBidRef.current) ||
        resolveContentBid(activeAudioBid);

      if (preferredBid) {
        const hasPreferredContent = list.some(
          item =>
            item.type === ChatContentItemType.CONTENT &&
            resolveContentBid(item.generated_block_bid) === preferredBid,
        );
        if (!hasPreferredContent) {
          // Pending auto-next means the target block is expected but not yet in
          // the timeline. Keep waiting instead of replaying stale entries.
          if (pendingAutoNextRef.current) {
            return -1;
          }
        } else {
          const preferredSamePageIndex = list.findIndex(
            item =>
              isAudibleContentItem(item) &&
              getItemPage(item) === targetPage &&
              resolveContentBid(item.generated_block_bid) === preferredBid,
          );
          if (preferredSamePageIndex >= 0) {
            return preferredSamePageIndex;
          }
          const preferredSamePageAnyContentIndex = list.findIndex(
            item =>
              isContentItem(item) &&
              getItemPage(item) === targetPage &&
              resolveContentBid(item.generated_block_bid) === preferredBid,
          );
          if (preferredSamePageAnyContentIndex >= 0) {
            return preferredSamePageAnyContentIndex;
          }
          const preferredAheadIndex = list.findIndex(
            item =>
              isAudibleContentItem(item) &&
              getItemPage(item) >= targetPage &&
              resolveContentBid(item.generated_block_bid) === preferredBid,
          );
          if (preferredAheadIndex >= 0) {
            return preferredAheadIndex;
          }
          const preferredAheadAnyContentIndex = list.findIndex(
            item =>
              isContentItem(item) &&
              getItemPage(item) >= targetPage &&
              resolveContentBid(item.generated_block_bid) === preferredBid,
          );
          if (preferredAheadAnyContentIndex >= 0) {
            return preferredAheadAnyContentIndex;
          }
        }
      }

      for (let i = list.length - 1; i >= 0; i -= 1) {
        const item = list[i];
        if (getItemPage(item) === targetPage && isAudibleContentItem(item)) {
          return i;
        }
      }
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const item = list[i];
        if (getItemPage(item) === targetPage && isContentItem(item)) {
          return i;
        }
      }
      const nextAudioIndex = list.findIndex(
        item => getItemPage(item) > targetPage && isAudibleContentItem(item),
      );
      if (nextAudioIndex >= 0) {
        return nextAudioIndex;
      }
      const nextContentIndex = list.findIndex(
        item => getItemPage(item) > targetPage && isContentItem(item),
      );
      if (nextContentIndex >= 0) {
        return nextContentIndex;
      }
      const pageIndex = list.findIndex(
        item => getItemPage(item) === targetPage,
      );
      if (pageIndex >= 0) {
        return pageIndex;
      }
      return list.findIndex(item => getItemPage(item) > targetPage);
    },
    [
      activeAudioBid,
      activeBlockBidRef,
      audioAndInteractionList,
      deckRef,
      refreshRuntimePageRemap,
      resolveContentBid,
      resolveRuntimeSequencePage,
      pendingAutoNextRef,
    ],
  );

  const resolveAnchoredSequenceStartIndex = useCallback(
    (anchorIndex: number) => {
      if (!audioAndInteractionList.length) {
        return -1;
      }
      const list = audioAndInteractionList;
      const normalizedAnchor = Math.max(0, anchorIndex);
      // The timeline list may be rebuilt after reset/interaction submit.
      // If the anchor points beyond the rebuilt list, fall back to scanning
      // from the beginning instead of getting stuck forever at -1.
      const startCursor =
        normalizedAnchor >= list.length ? 0 : normalizedAnchor;
      for (let i = startCursor; i < list.length; i += 1) {
        const item = list[i];
        if (
          item.type === ChatContentItemType.CONTENT &&
          !item.isSilentVisual &&
          item.generated_block_bid &&
          item.generated_block_bid !== 'loading'
        ) {
          return i;
        }
      }
      for (let i = startCursor; i < list.length; i += 1) {
        const item = list[i];
        if (
          item.type === ChatContentItemType.CONTENT &&
          item.generated_block_bid &&
          item.generated_block_bid !== 'loading'
        ) {
          return i;
        }
      }
      return -1;
    },
    [audioAndInteractionList],
  );

  const resolvePlaybackStartIndex = useCallback(
    (page: number) => {
      const anchorIndex = effectiveStartAnchorIndexRef.current;
      if (typeof anchorIndex === 'number' && anchorIndex >= 0) {
        const anchoredIndex = resolveAnchoredSequenceStartIndex(anchorIndex);
        if (anchoredIndex >= 0) {
          effectiveStartAnchorIndexRef.current = null;
          return anchoredIndex;
        }
        return -1;
      }
      return resolveSequenceStartIndex(page);
    },
    [
      effectiveStartAnchorIndexRef,
      resolveAnchoredSequenceStartIndex,
      resolveSequenceStartIndex,
    ],
  );

  // ---------------------------------------------------------------------------
  // Queue Manager — event-driven approach
  // ---------------------------------------------------------------------------
  // Stable refs for queue event handlers to avoid re-subscription windows.
  const endSequenceRef = useRef(endSequence);
  endSequenceRef.current = endSequence;
  const syncToSequencePageRef = useRef(syncToSequencePage);
  syncToSequencePageRef.current = syncToSequencePage;

  // Queue event handler refs — defined once, stable identity
  const onVisualShowHandler = useCallback((event: QueueEvent) => {
    const item = event.item as VisualQueueItem;
    setIsAudioSequenceActive(true);
    setActiveAudioBid(null);
    setActiveQueueAudioId(null);

    syncToSequencePageRef.current(item.page);

    if (!item.hasTextAfterVisual) {
      // Silent visual — queue manager handles auto-advance internally
      setSequenceInteraction(null);
    }
  }, []);

  const onAudioPlayHandler = useCallback(
    (event: QueueEvent) => {
      const item = event.item as AudioQueueItem;
      // Reset playback markers for the upcoming audio unit before the player
      // emits the next play-state callback.
      hasObservedPlaybackRef.current = false;
      pendingAutoNextRef.current = false;
      setIsAudioPlaying(false);
      setActiveAudioBid(item.generatedBlockBid);
      setActiveAudioPosition(item.audioPosition);
      setActiveQueueAudioId(item.id);
      setAudioSequenceToken(prev => prev + 1);
      setIsAudioSequenceActive(true);
      syncToSequencePageRef.current(item.page);
    },
    [pendingAutoNextRef, setIsAudioPlaying],
  );

  const onInteractionShowHandler = useCallback((event: QueueEvent) => {
    const item = event.item as InteractionQueueItem;
    setSequenceInteraction({
      ...item.contentItem,
      page: item.page,
    });
    setActiveAudioBid(null);
    setActiveQueueAudioId(null);
    setIsAudioSequenceActive(true);
  }, []);

  const onQueueCompletedHandler = useCallback(() => {
    const listLengthBeforeCompletion = audioAndInteractionLengthRef.current;
    const hadChapterAnchorBeforeCompletion = Boolean(
      resolveContentBid(activeBlockBidRef.current),
    );
    endSequenceRef.current({ tryAdvanceToNextBlock: true });

    const shouldWaitForGrowth =
      pendingAutoNextRef.current &&
      (hadChapterAnchorBeforeCompletion ||
        lastAdvanceCauseRef.current === 'interaction-resolved');

    if (shouldWaitForGrowth) {
      // Keep sequence in a short waiting state for late-arriving units.
      // This avoids hard-stopping immediately when SSE is still streaming.
      effectiveStartAnchorIndexRef.current = listLengthBeforeCompletion;
      pendingQueueGrowthAnchorRef.current = listLengthBeforeCompletion;
      shouldStartSequenceRef.current = true;
      setIsAudioSequenceActive(true);
      clearPendingGrowthWaitTimer();
      pendingGrowthWaitTimerRef.current = setTimeout(() => {
        if (pendingAutoNextRef.current) {
          setIsAudioSequenceActive(false);
        }
      }, LISTEN_PENDING_GROWTH_WAIT_MS);
      lastAdvanceCauseRef.current = 'other';
      return;
    }

    if (pendingAutoNextRef.current) {
      // Keep a short grace window for late-arriving next-block units even when
      // we are not in explicit growth-wait mode. This allows useListenPpt's
      // pendingAutoNext handoff to jump once the next block appears.
      pendingQueueGrowthAnchorRef.current = null;
      shouldStartSequenceRef.current = false;
      clearPendingGrowthWaitTimer();
      pendingGrowthWaitTimerRef.current = setTimeout(() => {
        pendingAutoNextRef.current = false;
      }, LISTEN_PENDING_AUTO_NEXT_GRACE_MS);
      lastAdvanceCauseRef.current = 'other';
      return;
    }

    pendingAutoNextRef.current = false;
    pendingQueueGrowthAnchorRef.current = null;
    shouldStartSequenceRef.current = false;
    clearPendingGrowthWaitTimer();
    lastAdvanceCauseRef.current = 'other';
  }, [
    activeBlockBidRef,
    clearPendingGrowthWaitTimer,
    effectiveStartAnchorIndexRef,
    pendingAutoNextRef,
    resolveContentBid,
    shouldStartSequenceRef,
  ]);

  const queueActions = useQueueManager({
    onVisualShow: onVisualShowHandler,
    onAudioPlay: onAudioPlayHandler,
    onInteractionShow: onInteractionShowHandler,
    onQueueCompleted: onQueueCompletedHandler,
  });

  useEffect(() => {
    queueActions.remapPages(page => resolveRuntimeSequencePage(page));
  }, [queueActions, resolveRuntimeSequencePage, runtimePageRemapVersion]);

  useEffect(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }
    const currentPage = deck.getIndices?.().h ?? -1;
    if (currentPage < 0) {
      return;
    }
    const mappedPage = resolveRuntimeSequencePage(currentPage);
    if (
      !Number.isFinite(mappedPage) ||
      mappedPage < 0 ||
      mappedPage === currentPage
    ) {
      return;
    }
    try {
      deck.slide(mappedPage);
      currentPptPageRef.current = mappedPage;
    } catch {
      // ignore reveal transition errors while jumping pruned pages
    }
  }, [
    currentPptPageRef,
    deckRef,
    resolveRuntimeSequencePage,
    runtimePageRemapVersion,
  ]);

  const toQueueAudioSegmentValue = useCallback(
    (segment: string | { audioData?: string; audio_segment?: string }) => {
      if (typeof segment === 'string') {
        return segment;
      }
      return segment.audioData || segment.audio_segment;
    },
    [],
  );

  const toQueueAudioDurationMs = useCallback(
    (segment: string | { durationMs?: number; duration_ms?: number }) => {
      if (typeof segment === 'string') {
        return undefined;
      }
      const value = Number(segment.durationMs ?? segment.duration_ms ?? 0);
      if (!Number.isFinite(value) || value <= 0) {
        return undefined;
      }
      return Math.floor(value);
    },
    [],
  );

  const upsertQueueAudioUrlIfNeeded = useCallback(
    (
      bid: string,
      position: number,
      audioUrl?: string,
      isFinal = true,
      durationMs?: number,
    ) => {
      if (!audioUrl) {
        return;
      }
      const audioKey = `${bid}:${position}`;
      if (syncedAudioStateRef.current.get(audioKey) === 'url') {
        return;
      }
      queueActions.upsertAudio(bid, position, {
        audio_url: audioUrl,
        is_final: isFinal,
        duration_ms:
          Number.isFinite(durationMs) && (durationMs || 0) > 0
            ? Number(durationMs)
            : undefined,
      });
      syncedAudioStateRef.current.set(audioKey, 'url');
    },
    [queueActions],
  );

  const syncQueueAudioTrack = useCallback(
    (
      bid: string,
      position: number,
      resolvedTrack: ReturnType<typeof resolveListenAudioTrack>,
    ) => {
      const {
        audioUrl,
        audioSegments: segments,
        isAudioStreaming,
        audioDurationMs,
      } = resolvedTrack;
      const audioKey = `${bid}:${position}`;
      const prevState = syncedAudioStateRef.current.get(audioKey);

      if (audioUrl) {
        // URL source supersedes segmented updates.
        upsertQueueAudioUrlIfNeeded(
          bid,
          position,
          audioUrl,
          !isAudioStreaming,
          audioDurationMs,
        );
        return;
      }

      if (segments && segments.length > 0) {
        // Only send NEW segments (skip already-synced ones)
        const prev =
          prevState !== 'url' && prevState
            ? prevState
            : { count: 0, finalized: false };
        const newSegments = segments.length > prev.count;
        const nowFinalized = !isAudioStreaming;

        if (newSegments) {
          for (let i = prev.count; i < segments.length; i++) {
            queueActions.upsertAudio(bid, position, {
              audio_segment: toQueueAudioSegmentValue(segments[i]),
              is_final: nowFinalized && i === segments.length - 1,
              duration_ms: toQueueAudioDurationMs(segments[i]),
            });
          }
          syncedAudioStateRef.current.set(audioKey, {
            count: segments.length,
            finalized: nowFinalized,
          });
          return;
        }

        if (nowFinalized && !prev.finalized && segments.length > 0) {
          // Segments unchanged but streaming just completed — send final marker
          queueActions.upsertAudio(bid, position, {
            audio_segment: toQueueAudioSegmentValue(
              segments[segments.length - 1],
            ),
            is_final: true,
            duration_ms: toQueueAudioDurationMs(segments[segments.length - 1]),
          });
          syncedAudioStateRef.current.set(audioKey, {
            count: segments.length,
            finalized: true,
          });
        }
        return;
      }

      if (isAudioStreaming && prevState === undefined) {
        // Streaming but no segments yet; upsert a placeholder (only once)
        queueActions.upsertAudio(bid, position, {
          is_final: false,
        });
        syncedAudioStateRef.current.set(audioKey, {
          count: 0,
          finalized: false,
        });
      }
    },
    [
      queueActions,
      toQueueAudioDurationMs,
      toQueueAudioSegmentValue,
      upsertQueueAudioUrlIfNeeded,
    ],
  );

  // ---------------------------------------------------------------------------
  // syncListToQueue — sync audioAndInteractionList into the queue
  // ---------------------------------------------------------------------------
  const syncListToQueue = useCallback(
    (list: AudioInteractionItem[]) => {
      refreshRuntimePageRemap();
      const existingQueueIds = new Set(
        queueActions.getQueueSnapshot().map(queueItem => queueItem.id),
      );
      const prevContentByKey = new Map<string, AudioInteractionItem>();
      lastSyncedListRef.current.forEach(prevItem => {
        const prevBid = prevItem.generated_block_bid;
        if (
          !prevBid ||
          prevBid === 'loading' ||
          prevItem.type !== ChatContentItemType.CONTENT
        ) {
          return;
        }
        const prevPosition = prevItem.audioPosition ?? 0;
        prevContentByKey.set(`${prevBid}:${prevPosition}`, prevItem);
      });

      list.forEach(item => {
        const bid = item.generated_block_bid;
        if (!bid || bid === 'loading') {
          return;
        }
        const position = item.audioPosition ?? 0;
        const mappedPage = resolveRuntimeSequencePage(item.page);

        if (item.type === ChatContentItemType.INTERACTION) {
          const interactionId = buildQueueItemId({
            type: 'interaction',
            bid,
          });
          if (!existingQueueIds.has(interactionId)) {
            queueActions.enqueueInteraction({
              generatedBlockBid: bid,
              page: mappedPage,
              contentItem: item,
            });
            existingQueueIds.add(interactionId);
          }
          return;
        }

        const visualId = buildQueueItemId({
          type: 'visual',
          bid,
          position,
        });
        const contentKey = `${bid}:${position}`;
        const prevContent = prevContentByKey.get(contentKey);

        // CONTENT item
        if (item.isSilentVisual) {
          // Silent visual — no audio expected
          if (!existingQueueIds.has(visualId)) {
            queueActions.enqueueVisual({
              generatedBlockBid: bid,
              position,
              page: mappedPage,
              hasTextAfterVisual: false,
            });
            existingQueueIds.add(visualId);
          }
          return;
        }

        // Content with audio
        if (!existingQueueIds.has(visualId)) {
          queueActions.enqueueVisual({
            generatedBlockBid: bid,
            position,
            page: mappedPage,
            hasTextAfterVisual: true,
          });
          existingQueueIds.add(visualId);
        }

        // Was silent, now has audio — update queue expectation for existing visual.
        if (prevContent?.isSilentVisual && !item.isSilentVisual) {
          queueActions.updateVisualExpectation(bid, position, true);
        }

        const resolvedTrack = resolveListenAudioTrack(item, position);
        const hasAudio = hasPlayableResolvedTrack(resolvedTrack);
        if (hasAudio) {
          syncQueueAudioTrack(bid, position, resolvedTrack);
        }
      });

      lastSyncedListRef.current = list;
    },
    [
      hasPlayableResolvedTrack,
      queueActions,
      refreshRuntimePageRemap,
      resolveRuntimeSequencePage,
      syncQueueAudioTrack,
    ],
  );

  const resolveQueueStartIndexFromListIndex = useCallback(
    (
      listIndex: number,
      list: AudioInteractionItem[] = audioAndInteractionList,
    ) => {
      if (listIndex < 0 || listIndex >= list.length) {
        return -1;
      }
      const target = list[listIndex];
      const bid = target.generated_block_bid;
      if (!bid || bid === 'loading') {
        return -1;
      }

      const queueSnapshot = queueActions.getQueueSnapshot();
      const queueIds =
        target.type === ChatContentItemType.INTERACTION
          ? [buildQueueItemId({ type: 'interaction', bid })]
          : [
              buildQueueItemId({
                type: 'audio',
                bid,
                position: target.audioPosition ?? 0,
              }),
              buildQueueItemId({
                type: 'visual',
                bid,
                position: target.audioPosition ?? 0,
              }),
            ];

      for (const queueId of queueIds) {
        const idx = queueSnapshot.findIndex(item => item.id === queueId);
        if (idx >= 0) {
          return idx;
        }
      }

      // Fallback for partially-synced queue snapshots.
      return queueSnapshot.findIndex(item => item.generatedBlockBid === bid);
    },
    [audioAndInteractionList, queueActions],
  );

  const resolvePendingResumeQueueIndex = useCallback(() => {
    const queueSnapshot = queueActions.getQueueSnapshot();
    const startIndex = Math.max(queueActions.getCurrentIndex(), 0);
    for (let index = startIndex; index < queueSnapshot.length; index += 1) {
      const item = queueSnapshot[index];
      if (item.status === 'completed' || item.status === 'timeout') {
        continue;
      }
      return index;
    }
    return -1;
  }, [queueActions]);

  const startQueueFromListIndex = useCallback(
    (listIndex: number, options?: { resyncOnMiss?: boolean }) => {
      let queueIndex = resolveQueueStartIndexFromListIndex(listIndex);
      if (queueIndex >= 0) {
        queueActions.startFromIndex(queueIndex);
        hasInitialAutoStartAttemptedRef.current = true;
        return true;
      }

      if (options?.resyncOnMiss) {
        syncListToQueue(audioAndInteractionList);
        queueIndex = resolveQueueStartIndexFromListIndex(
          listIndex,
          audioAndInteractionList,
        );
        if (queueIndex >= 0) {
          queueActions.startFromIndex(queueIndex);
          hasInitialAutoStartAttemptedRef.current = true;
          return true;
        }
      }

      return false;
    },
    [
      audioAndInteractionList,
      queueActions,
      resolveQueueStartIndexFromListIndex,
      syncListToQueue,
    ],
  );

  const startFromPendingResumeIndex = useCallback(
    (
      pendingResumeIndex: number,
      options?: {
        clearGrowthAnchor?: boolean;
        markSequenceActive?: boolean;
      },
    ) => {
      if (pendingResumeIndex < 0) {
        return false;
      }
      if (options?.clearGrowthAnchor) {
        pendingQueueGrowthAnchorRef.current = null;
        clearPendingGrowthWaitTimer();
      }
      queueActions.startFromIndex(pendingResumeIndex);
      hasInitialAutoStartAttemptedRef.current = true;
      shouldStartSequenceRef.current = false;
      if (options?.markSequenceActive) {
        setIsAudioSequenceActive(true);
      }
      return true;
    },
    [clearPendingGrowthWaitTimer, queueActions, shouldStartSequenceRef],
  );

  // ---------------------------------------------------------------------------
  // Effects — sync list to queue, bootstrap, and cleanup
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    let cancelled = false;
    let rafA: number | null = null;
    let rafB: number | null = null;
    const timerA = window.setTimeout(() => {
      if (!cancelled) {
        refreshRuntimePageRemap();
      }
    }, 120);
    const timerB = window.setTimeout(() => {
      if (!cancelled) {
        refreshRuntimePageRemap();
      }
    }, 400);

    rafA = window.requestAnimationFrame(() => {
      if (cancelled) {
        return;
      }
      refreshRuntimePageRemap();
      rafB = window.requestAnimationFrame(() => {
        if (!cancelled) {
          refreshRuntimePageRemap();
        }
      });
    });

    return () => {
      cancelled = true;
      window.clearTimeout(timerA);
      window.clearTimeout(timerB);
      if (rafA !== null) {
        window.cancelAnimationFrame(rafA);
      }
      if (rafB !== null) {
        window.cancelAnimationFrame(rafB);
      }
    };
  }, [audioAndInteractionList, refreshRuntimePageRemap]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const deck = deckRef.current;
    if (!deck) {
      return;
    }

    let rafId: number | null = null;
    const trackedIframes = new Set<HTMLIFrameElement>();

    const scheduleRefresh = () => {
      if (rafId !== null) {
        return;
      }
      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        refreshRuntimePageRemap();
      });
    };

    const bindIframeLoadListeners = () => {
      const slides = collectDeckSlides();
      slides.forEach(slide => {
        if (
          typeof HTMLElement === 'undefined' ||
          !(slide instanceof HTMLElement)
        ) {
          return;
        }
        const iframeNodes = slide.querySelectorAll('iframe');
        iframeNodes.forEach(node => {
          const iframe = node as HTMLIFrameElement;
          if (trackedIframes.has(iframe)) {
            return;
          }
          trackedIframes.add(iframe);
          iframe.addEventListener('load', scheduleRefresh);
        });
      });
    };

    bindIframeLoadListeners();
    scheduleRefresh();

    const deckWithElements = deck as {
      getSlidesElement?: () => Element | null;
      getRevealElement?: () => Element | null;
    };
    const slidesRoot =
      (typeof deckWithElements.getSlidesElement === 'function'
        ? deckWithElements.getSlidesElement()
        : null) ||
      (typeof deckWithElements.getRevealElement === 'function'
        ? deckWithElements.getRevealElement()
        : null);

    const observer =
      typeof MutationObserver === 'undefined' || !slidesRoot
        ? null
        : new MutationObserver(() => {
            bindIframeLoadListeners();
            scheduleRefresh();
          });
    if (observer && slidesRoot) {
      observer.observe(slidesRoot, {
        childList: true,
        subtree: true,
      });
    }

    return () => {
      if (observer) {
        observer.disconnect();
      }
      trackedIframes.forEach(iframe => {
        iframe.removeEventListener('load', scheduleRefresh);
      });
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
      }
    };
  }, [
    audioAndInteractionList.length,
    collectDeckSlides,
    deckRef,
    refreshRuntimePageRemap,
  ]);

  // Sync audioAndInteractionList → queue whenever it changes
  useEffect(() => {
    syncListToQueue(audioAndInteractionList);
  }, [audioAndInteractionList, syncListToQueue]);

  // When the queue had already started once and new units arrive later
  // (common for long multi-position streaming blocks), auto-resume so playback
  // continues without requiring another manual Play.
  useEffect(() => {
    if (previewMode) {
      return;
    }
    if (isSequencePausedRef.current) {
      return;
    }
    if (!hasInitialAutoStartAttemptedRef.current) {
      return;
    }
    if (!audioAndInteractionList.length) {
      return;
    }
    if (activeAudioBid || sequenceInteraction) {
      return;
    }

    const queueSnapshot = queueActions.getQueueSnapshot();
    if (!queueSnapshot.length) {
      return;
    }
    const currentQueueIndex = queueActions.getCurrentIndex();
    const scanStartIndex = currentQueueIndex < 0 ? 0 : currentQueueIndex;
    const hasActionableQueueUnit = queueSnapshot
      .slice(scanStartIndex)
      .some(
        queueItem =>
          queueItem.status !== 'completed' && queueItem.status !== 'timeout',
      );
    if (!hasActionableQueueUnit) {
      return;
    }

    setIsAudioSequenceActive(true);
    queueActions.resume();
  }, [
    activeAudioBid,
    audioAndInteractionList,
    previewMode,
    queueActions,
    sequenceInteraction,
    setIsAudioSequenceActive,
  ]);

  // Explicit play fallback: if AudioPlayer doesn't auto-play, trigger play() manually
  useEffect(() => {
    if (!activeAudioBid || isSequencePausedRef.current) {
      return;
    }
    // Give AudioPlayer time to mount and autoPlay
    const timer = setTimeout(() => {
      if (isSequencePausedRef.current) return;
      const state = audioPlayerRef.current?.getPlaybackState?.();
      const shouldManualPlay = !state || (!state.isPlaying && !state.isLoading);
      if (shouldManualPlay) {
        audioPlayerRef.current?.play();
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [audioSequenceToken, activeAudioBid]);

  const audioAndInteractionLengthRef = useRef(audioAndInteractionList.length);
  audioAndInteractionLengthRef.current = audioAndInteractionList.length;

  useEffect(() => {
    if (!enableInitialAutoStart || previewMode) {
      return;
    }
    if (!audioAndInteractionList.length) {
      hasInitialAutoStartAttemptedRef.current = false;
      return;
    }
    if (hasInitialAutoStartAttemptedRef.current) {
      return;
    }
    if (isSequencePausedRef.current) {
      return;
    }
    if (isAudioSequenceActive || activeAudioBid) {
      return;
    }
    let cancelled = false;
    let attemptCount = 0;
    const maxAttempts = 60;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const tryInitialAutoStart = () => {
      if (cancelled || hasInitialAutoStartAttemptedRef.current) {
        return;
      }
      if (
        isSequencePausedRef.current ||
        isAudioSequenceActive ||
        activeAudioBid
      ) {
        return;
      }
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
      const startIndex = resolvePlaybackStartIndex(currentPage);
      if (startIndex < 0) {
        return;
      }
      const started = startQueueFromListIndex(startIndex, {
        resyncOnMiss: true,
      });
      if (!started) {
        return;
      }
      shouldStartSequenceRef.current = false;
      hasInitialAutoStartAttemptedRef.current = true;
    };

    const scheduleRetry = () => {
      if (cancelled || hasInitialAutoStartAttemptedRef.current) {
        return;
      }
      if (attemptCount >= maxAttempts) {
        return;
      }
      attemptCount += 1;
      tryInitialAutoStart();
      if (hasInitialAutoStartAttemptedRef.current) {
        return;
      }
      retryTimer = setTimeout(scheduleRetry, 150);
    };

    scheduleRetry();

    return () => {
      cancelled = true;
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
    };
  }, [
    audioAndInteractionList,
    activeAudioBid,
    currentPptPageRef,
    deckRef,
    enableInitialAutoStart,
    isAudioSequenceActive,
    previewMode,
    resolvePlaybackStartIndex,
    startQueueFromListIndex,
    shouldStartSequenceRef,
  ]);

  // Reset when list empties — debounced to avoid resetting during transient
  // block transitions where audioAndInteractionList is momentarily empty.
  useEffect(() => {
    if (audioAndInteractionList.length) {
      return;
    }
    const timer = setTimeout(() => {
      // Skip reset if new items already arrived during debounce.
      if (audioAndInteractionLengthRef.current > 0) {
        return;
      }
      // Skip reset while auto-navigation is waiting for the next block stream.
      if (shouldStartSequenceRef.current || pendingAutoNextRef.current) {
        return;
      }
      audioPlayerRef.current?.pause({
        traceId: 'sequence-reset',
        keepAutoPlay: true,
      });
      queueActions.reset();
      syncedAudioStateRef.current.clear();
      pendingAutoNextRef.current = false;
      lastAdvanceCauseRef.current = 'other';
      effectiveStartAnchorIndexRef.current = null;
      pendingQueueGrowthAnchorRef.current = null;
      clearPendingGrowthWaitTimer();
      endSequence();
    }, 800);
    return () => clearTimeout(timer);
  }, [
    audioAndInteractionList.length,
    endSequence,
    clearPendingGrowthWaitTimer,
    effectiveStartAnchorIndexRef,
    pendingAutoNextRef,
    queueActions,
    shouldStartSequenceRef,
  ]);

  // Bootstrap: start sequence when shouldStartSequenceRef is set
  useEffect(() => {
    if (!shouldStartSequenceRef.current) {
      return;
    }
    if (!audioAndInteractionList.length) {
      return;
    }
    if (isSequencePausedRef.current) {
      return;
    }

    const pendingResumeIndex = resolvePendingResumeQueueIndex();
    if (pendingQueueGrowthAnchorRef.current !== null) {
      if (
        startFromPendingResumeIndex(pendingResumeIndex, {
          clearGrowthAnchor: true,
        })
      ) {
        return;
      }
      return;
    }

    const currentPage =
      deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
    const startIndex = resolvePlaybackStartIndex(currentPage);
    if (startIndex < 0) {
      const hasStartAnchor =
        typeof effectiveStartAnchorIndexRef.current === 'number' &&
        effectiveStartAnchorIndexRef.current >= 0;
      if (hasStartAnchor) {
        startFromPendingResumeIndex(pendingResumeIndex);
      }
      return;
    }
    const started = startQueueFromListIndex(startIndex, { resyncOnMiss: true });
    if (!started) {
      return;
    }
    shouldStartSequenceRef.current = false;
  }, [
    audioAndInteractionList,
    currentPptPageRef,
    deckRef,
    effectiveStartAnchorIndexRef,
    resolvePendingResumeQueueIndex,
    resolvePlaybackStartIndex,
    startFromPendingResumeIndex,
    startQueueFromListIndex,
    shouldStartSequenceRef,
  ]);

  // ---------------------------------------------------------------------------
  // Derived values — same as original
  // ---------------------------------------------------------------------------
  const activeAudioBlockBid = useMemo(() => {
    if (!activeAudioBid) {
      return null;
    }
    return resolveContentBid(activeAudioBid);
  }, [activeAudioBid, resolveContentBid]);

  const activeContentItem = useMemo(() => {
    if (!activeAudioBlockBid) {
      return undefined;
    }
    const targetPosition = activeAudioPosition ?? 0;
    const resolvedFromTimeline = audioAndInteractionList.find(item => {
      if (item.type !== ChatContentItemType.CONTENT) {
        return false;
      }
      if (item.isSilentVisual) {
        return false;
      }
      return (
        resolveContentBid(item.generated_block_bid) === activeAudioBlockBid &&
        (item.audioPosition ?? 0) === targetPosition
      );
    });
    if (resolvedFromTimeline) {
      return resolvedFromTimeline;
    }

    const fallbackSameBidFromTimeline = audioAndInteractionList.find(item => {
      if (item.type !== ChatContentItemType.CONTENT) {
        return false;
      }
      if (item.isSilentVisual) {
        return false;
      }
      return (
        resolveContentBid(item.generated_block_bid) === activeAudioBlockBid
      );
    });
    if (fallbackSameBidFromTimeline) {
      return fallbackSameBidFromTimeline;
    }

    return (
      audioContentByBid.get(activeAudioBlockBid) ??
      contentByBid.get(activeAudioBlockBid)
    );
  }, [
    activeAudioBlockBid,
    activeAudioPosition,
    audioAndInteractionList,
    audioContentByBid,
    contentByBid,
    resolveContentBid,
  ]);

  const activeAudioTrack = useMemo(() => {
    if (!activeAudioBid) {
      return null;
    }

    const queueSnapshot = queueActions.getQueueSnapshot();
    const expectedAudioId =
      activeQueueAudioId ||
      buildQueueItemId({
        type: 'audio',
        bid: activeAudioBid,
        position: activeAudioPosition,
      });

    let queueAudioItem = queueSnapshot.find(
      item => item.id === expectedAudioId && item.type === 'audio',
    ) as AudioQueueItem | undefined;

    if (!queueAudioItem) {
      queueAudioItem = queueSnapshot.find(
        item =>
          item.type === 'audio' &&
          item.generatedBlockBid === activeAudioBid &&
          item.audioPosition === activeAudioPosition,
      ) as AudioQueueItem | undefined;
    }

    const queueSegments =
      queueAudioItem?.segments
        .map((segment, index) => {
          if (!segment.audio_segment) {
            return null;
          }
          return {
            segmentIndex: index,
            audioData: segment.audio_segment,
            durationMs:
              Number.isFinite(segment.duration_ms) &&
              Number(segment.duration_ms) > 0
                ? Number(segment.duration_ms)
                : 0,
            isFinal: Boolean(segment.is_final),
          } satisfies AudioSegment;
        })
        .filter((segment): segment is AudioSegment => Boolean(segment)) ?? [];

    const queueTrack = queueAudioItem
      ? {
          audioUrl: queueAudioItem.audioUrl,
          streamingSegments: queueSegments,
          isStreaming: queueAudioItem.isStreaming,
          durationMs: queueAudioItem.durationMs,
        }
      : null;

    const queueHasPlayablePayload =
      Boolean(queueTrack?.audioUrl) || queueSegments.length > 0;
    if (queueTrack && queueHasPlayablePayload) {
      return queueTrack;
    }

    if (!activeContentItem) {
      return queueTrack;
    }

    const resolvedContentTrack = resolveListenAudioTrack(
      activeContentItem,
      activeAudioPosition,
    );
    const normalizedResolvedContentTrack = {
      audioUrl: resolvedContentTrack.audioUrl,
      streamingSegments: resolvedContentTrack.audioSegments ?? [],
      isStreaming: resolvedContentTrack.isAudioStreaming,
      durationMs: resolvedContentTrack.audioDurationMs,
    };
    if (hasPlayableResolvedTrack(resolvedContentTrack)) {
      return normalizedResolvedContentTrack;
    }

    return queueTrack ?? normalizedResolvedContentTrack;
  }, [
    activeQueueAudioId,
    activeAudioBid,
    activeAudioPosition,
    activeContentItem,
    hasPlayableResolvedTrack,
    queueActions,
  ]);

  const resolvedActiveContentTrack = useMemo(() => {
    if (!activeContentItem) {
      return null;
    }
    return resolveListenAudioTrack(activeContentItem, activeAudioPosition);
  }, [activeAudioPosition, activeContentItem]);

  const activeAudioDurationMs = useMemo(() => {
    if (Number.isFinite(activeAudioTrack?.durationMs)) {
      const duration = Number(activeAudioTrack?.durationMs);
      if (duration > 0) {
        return duration;
      }
    }

    if (!resolvedActiveContentTrack) {
      return undefined;
    }

    const explicitDuration = resolvedActiveContentTrack.audioDurationMs;
    if (Number.isFinite(explicitDuration) && (explicitDuration || 0) > 0) {
      return explicitDuration;
    }

    const segments = resolvedActiveContentTrack.audioSegments;
    if (!segments || !segments.length) {
      return undefined;
    }

    const sumDuration = segments.reduce((total, segment) => {
      const next = Number(segment.durationMs);
      if (!Number.isFinite(next) || next <= 0) {
        return total;
      }
      return total + next;
    }, 0);
    if (sumDuration > 0) {
      return sumDuration;
    }
    return undefined;
  }, [activeAudioTrack?.durationMs, resolvedActiveContentTrack]);

  const audioWatchdogTimeoutMs = useMemo(
    () => resolveListenAudioWatchdogMs(activeAudioDurationMs),
    [activeAudioDurationMs],
  );

  const resolveMappedPageForActiveUnit = useCallback(() => {
    if (!activeAudioBid) {
      return null;
    }
    const resolvedBid = resolveContentBid(activeAudioBid) || activeAudioBid;
    for (let i = audioAndInteractionList.length - 1; i >= 0; i -= 1) {
      const item = audioAndInteractionList[i];
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      if (resolveContentBid(item.generated_block_bid) !== resolvedBid) {
        continue;
      }
      if ((item.audioPosition ?? 0) !== activeAudioPosition) {
        continue;
      }
      return resolveRuntimeSequencePage(item.page);
    }
    return null;
  }, [
    activeAudioBid,
    activeAudioPosition,
    audioAndInteractionList,
    resolveContentBid,
    resolveRuntimeSequencePage,
  ]);

  // ---------------------------------------------------------------------------
  // Event handlers — adapted to use queue actions
  // ---------------------------------------------------------------------------
  const handleAudioEnded = useCallback(
    (token?: number) => {
      if (
        typeof token === 'number' &&
        token !== audioSequenceTokenRef.current
      ) {
        return;
      }
      if (isSequencePausedRef.current) {
        return;
      }
      lastAdvanceCauseRef.current = 'audio-ended';

      const mappedPage = resolveMappedPageForActiveUnit();
      if (typeof mappedPage === 'number' && mappedPage >= 0) {
        syncToSequencePage(mappedPage);
      }

      const queueSnapshot = queueActions.getQueueSnapshot();
      const currentQueueIndex = queueActions.getCurrentIndex();
      const hasFutureUnits = queueSnapshot
        .slice(currentQueueIndex + 1)
        .some(
          queueItem =>
            queueItem.status !== 'completed' && queueItem.status !== 'timeout',
        );
      if (!hasFutureUnits) {
        const deck = deckRef.current;
        const currentPage = deck?.getIndices?.().h ?? currentPptPageRef.current;
        const totalSlides =
          typeof deck?.getSlides === 'function'
            ? deck.getSlides().length
            : typeof deck?.getTotalSlides === 'function'
              ? deck.getTotalSlides()
              : 0;
        if (
          totalSlides > 0 &&
          currentPage >= 0 &&
          currentPage < totalSlides - 1 &&
          (typeof mappedPage !== 'number' || mappedPage <= currentPage)
        ) {
          syncToSequencePage(currentPage + 1);
        }
      }

      queueActions.advance();
    },
    [
      currentPptPageRef,
      deckRef,
      queueActions,
      resolveMappedPageForActiveUnit,
      syncToSequencePage,
    ],
  );

  const handleAudioError = useCallback(
    (token?: number) => {
      if (
        typeof token === 'number' &&
        token !== audioSequenceTokenRef.current
      ) {
        return;
      }
      // Skip failed audio units so listen mode keeps progressing automatically.
      setIsAudioPlaying(false);
      queueActions.advance();
    },
    [queueActions, setIsAudioPlaying],
  );

  const handlePlay = useCallback(() => {
    if (previewMode) {
      return;
    }

    // Pre-warm audio systems during user gesture to bypass browser autoplay policy.
    // This must happen synchronously inside the click handler.
    warmupSharedAudioPlayback?.();
    audioPlayerRef.current?.warmup?.();

    isSequencePausedRef.current = false;

    if (sequenceInteraction) {
      if (hasInteractionResponse(sequenceInteraction)) {
        lastAdvanceCauseRef.current = 'interaction-resolved';
        setSequenceInteraction(null);
        queueActions.advance();
      }
      // Keep sequence blocked until learner explicitly submits interaction.
      return;
    }

    if (!activeAudioBid && audioAndInteractionList.length) {
      const pendingResumeIndex = resolvePendingResumeQueueIndex();
      if (pendingAutoNextRef.current) {
        // The sequence is waiting for the next block to stream in.
        // Avoid replaying the current block while auto-next is pending.
        if (
          startFromPendingResumeIndex(pendingResumeIndex, {
            clearGrowthAnchor: true,
            markSequenceActive: true,
          })
        ) {
          return;
        }
        queueActions.resume();
        return;
      }
      // No active audio — start/resume the queue
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
      const startIndex = resolvePlaybackStartIndex(currentPage);
      if (startIndex < 0) {
        if (
          startFromPendingResumeIndex(pendingResumeIndex, {
            clearGrowthAnchor: true,
            markSequenceActive: true,
          })
        ) {
          return;
        }
        queueActions.resume();
        return;
      }
      if (!startQueueFromListIndex(startIndex, { resyncOnMiss: true })) {
        if (
          startFromPendingResumeIndex(pendingResumeIndex, {
            clearGrowthAnchor: true,
            markSequenceActive: true,
          })
        ) {
          return;
        }
        queueActions.resume();
      }
      return;
    }

    // Audio is active — resume player
    queueActions.resume();
    audioPlayerRef.current?.play();
  }, [
    activeAudioBid,
    audioAndInteractionList,
    currentPptPageRef,
    deckRef,
    pendingAutoNextRef,
    previewMode,
    queueActions,
    resolvePendingResumeQueueIndex,
    resolvePlaybackStartIndex,
    sequenceInteraction,
    startFromPendingResumeIndex,
    startQueueFromListIndex,
  ]);

  const handlePause = useCallback(
    (traceId?: string) => {
      if (previewMode) {
        return;
      }
      isSequencePausedRef.current = true;
      queueActions.pause();
      audioPlayerRef.current?.pause({ traceId });
    },
    [previewMode, queueActions],
  );

  const continueAfterInteraction = useCallback(() => {
    if (previewMode) {
      return;
    }
    isSequencePausedRef.current = false;
    lastAdvanceCauseRef.current = 'interaction-resolved';
    setSequenceInteraction(null);
    queueActions.advance();
  }, [previewMode, queueActions]);

  const startSequenceFromIndex = useCallback(
    (index: number) => {
      isSequencePausedRef.current = false;
      audioPlayerRef.current?.pause({
        traceId: 'sequence-start',
        keepAutoPlay: true,
      });
      queueActions.reset();
      syncedAudioStateRef.current.clear();
      effectiveStartAnchorIndexRef.current = null;
      pendingQueueGrowthAnchorRef.current = null;
      clearPendingGrowthWaitTimer();
      syncListToQueue(audioAndInteractionList);
      startQueueFromListIndex(index);
    },
    [
      audioAndInteractionList,
      clearPendingGrowthWaitTimer,
      effectiveStartAnchorIndexRef,
      queueActions,
      startQueueFromListIndex,
      syncListToQueue,
    ],
  );

  const startSequenceFromPage = useCallback(
    (page: number) => {
      const startIndex = resolvePlaybackStartIndex(page);
      if (startIndex < 0) {
        return;
      }
      startSequenceFromIndex(startIndex);
    },
    [resolvePlaybackStartIndex, startSequenceFromIndex],
  );

  // ---------------------------------------------------------------------------
  // Audio watchdog — same as original
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (isAudioPlaying || isAudioPlayerBusy()) {
      hasObservedPlaybackRef.current = true;
    }
  }, [isAudioPlayerBusy, isAudioPlaying]);

  useEffect(() => {
    if (
      !isAudioSequenceActive ||
      !activeAudioBid ||
      isSequencePausedRef.current
    ) {
      return;
    }
    if (isAudioPlaying) {
      hasObservedPlaybackRef.current = true;
      return;
    }
    if (isAudioPlayerBusy()) {
      hasObservedPlaybackRef.current = true;
      return;
    }
    if (hasObservedPlaybackRef.current) {
      return;
    }
    const timer = setTimeout(() => {
      if (isSequencePausedRef.current || hasObservedPlaybackRef.current) {
        return;
      }
      if (isAudioPlayerBusy()) {
        hasObservedPlaybackRef.current = true;
        return;
      }
      // Auto-advance past failed audio instead of pausing the queue
      queueActions.advance();
    }, audioWatchdogTimeoutMs);
    return () => clearTimeout(timer);
  }, [
    isAudioSequenceActive,
    activeAudioBid,
    isAudioPlaying,
    isAudioPlayerBusy,
    audioWatchdogTimeoutMs,
    queueActions,
  ]);

  // ---------------------------------------------------------------------------
  // Stuck-audio watchdog — auto-advance when audio starts but never ends.
  // The previous watchdog handles "never started"; this handles "started but
  // onEnded never fires" (e.g. network stall, GC, or browser quirk).
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (
      !isAudioSequenceActive ||
      !isAudioPlaying ||
      isSequencePausedRef.current
    ) {
      return;
    }
    // Generous timeout: 2x known duration (min 10s) or 30s fallback.
    const knownMs = activeAudioDurationMs;
    const maxMs = knownMs ? Math.max(knownMs * 2, knownMs + 10000) : 30000;
    const timer = setTimeout(() => {
      if (isSequencePausedRef.current) {
        return;
      }
      // Double-check the player is still genuinely playing
      const state = audioPlayerRef.current?.getPlaybackState?.();
      if (state && !state.isPlaying) {
        return;
      }
      setIsAudioPlaying(false);
      queueActions.advance();
    }, maxMs);
    return () => clearTimeout(timer);
  }, [
    isAudioSequenceActive,
    isAudioPlaying,
    activeAudioDurationMs,
    queueActions,
    setIsAudioPlaying,
  ]);

  useEffect(
    () => () => {
      clearPendingGrowthWaitTimer();
    },
    [clearPendingGrowthWaitTimer],
  );

  // ---------------------------------------------------------------------------
  // Return — identical interface to original
  // ---------------------------------------------------------------------------
  return {
    audioPlayerRef,
    activeAudioTrack,
    activeAudioBlockBid,
    activeAudioPosition,
    sequenceInteraction,
    isAudioSequenceActive,
    isAudioPlayerBusy,
    audioSequenceToken,
    handleAudioEnded,
    handleAudioError,
    handlePlay,
    handlePause,
    continueAfterInteraction,
    startSequenceFromIndex,
    startSequenceFromPage,
    resolveRuntimeSequencePage,
    refreshRuntimePageRemap,
  };
};
