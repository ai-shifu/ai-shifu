import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Reveal, { Options } from 'reveal.js';
import { type RenderSegment } from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import {
  warmupSharedAudioPlayback,
  type AudioPlayerHandle,
} from '@/components/audio/AudioPlayer';
import type { AudioSegment } from '@/c-utils/audio-utils';
import {
  buildListenUnitId,
  extractAudioPositions,
} from '@/c-utils/listen-orchestrator';
import type { ListenSlideData } from '@/c-api/studyV2';
import {
  hasAnyAudioPayload,
  isListenModeSpeakableText,
  resolveListenAudioTrack,
  splitListenModeSegments,
} from '@/c-utils/listen-mode';
import { useQueueManager } from '@/c-utils/listen-mode/use-queue-manager';
import {
  buildQueueItemId,
  type QueueEvent,
  type VisualQueueItem,
  type AudioQueueItem,
  type InteractionQueueItem,
} from '@/c-utils/listen-mode/queue-manager';

const isRenderableBackendSlide = (slide: ListenSlideData): boolean => {
  if (slide.is_placeholder || slide.segment_type === 'placeholder') {
    return false;
  }
  // All finalized slides (is_placeholder=false) are renderable, regardless of segment_content.
  // Backend intentionally clears segment_content in NEW_SLIDE events (see streaming_tts.py:827-830),
  // expecting frontend to render from accumulated CONTENT stream chunks.
  // This ensures every finalized slide gets a page number and can be navigated to.
  return true;
};

const EMPTY_SANDBOX_WRAPPER_PATTERN =
  /^<div(?:\s+[^>]*)?>\s*(?:<br\s*\/?>|&nbsp;|\s)*<\/div>$/i;
const FIXED_MARKER_PATTERN = /^!?=+$/;
const EMPTY_SVG_PATTERN = /^<svg\b[^>]*>\s*(?:<!--[\s\S]*?-->\s*)*<\/svg>$/i;
const EMPTY_WRAPPED_SVG_PATTERN =
  /^<div(?:\s+[^>]*)?>\s*<svg\b[^>]*>\s*(?:<!--[\s\S]*?-->\s*)*<\/svg>\s*<\/div>$/i;
const MALFORMED_EMPTY_SVG_PATTERN = /<svg<|<\/svg<>/i;
const VISUAL_HTML_TAG_PATTERN = /<(svg|table|iframe|img|video)\b/i;
const MARKDOWN_IMAGE_PATTERN = /!\[[^\]]*]\([^)]+\)/;
const MERMAID_CODE_FENCE_PATTERN = /```[\t ]*mermaid\b/i;
const RUNTIME_EMPTY_SVG_CONTAINER_SELECTOR = '.content-render-svg';
const RUNTIME_VISUAL_CONTENT_SELECTOR = 'svg,table,img,video,canvas,.mermaid';
const RUNTIME_SANDBOX_IFRAME_SELECTOR =
  '.content-render-iframe-sandbox > iframe';
const RUNTIME_SANDBOX_CONTAINER_SELECTOR = '.sandbox-container';
const RUNTIME_SANDBOX_VISUAL_CONTENT_SELECTOR =
  'svg,table,img,video,canvas,.mermaid,iframe[src],iframe[srcdoc],iframe[data-url],iframe[data-tag],object,embed';
const RUNTIME_PRUNED_SLIDE_CLASS = 'listen-runtime-pruned-slide';
const RUNTIME_PRUNED_SLIDE_ATTR = 'data-runtime-pruned';

const normalizeRuntimeTextContent = (
  value: string | null | undefined,
): string =>
  (value || '')
    .replace(/\u00a0/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const isRuntimePrunableSandboxIframe = (
  iframe: HTMLIFrameElement,
): boolean | null => {
  const iframeDocument = iframe.contentDocument;
  if (!iframeDocument) {
    return null;
  }

  const sandboxContainer = iframeDocument.querySelector(
    RUNTIME_SANDBOX_CONTAINER_SELECTOR,
  );
  // NOTE:
  // sandboxContainer lives in iframeDocument (different JS realm).
  // Cross-realm `instanceof HTMLElement` checks fail, so rely on nodeType/tagName.
  if (!sandboxContainer || sandboxContainer.nodeType !== Node.ELEMENT_NODE) {
    return null;
  }
  const sandboxElement = sandboxContainer as Element;

  if (sandboxElement.querySelector(RUNTIME_SANDBOX_VISUAL_CONTENT_SELECTOR)) {
    return false;
  }

  if (normalizeRuntimeTextContent(sandboxElement.textContent).length > 0) {
    return false;
  }

  const hasRenderableElement = Array.from(sandboxElement.childNodes).some(
    node => {
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
      return (
        normalizeRuntimeTextContent(elementNode.textContent).length > 0 ||
        elementNode.childElementCount > 0
      );
    },
  );

  return !hasRenderableElement;
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

  const sandboxIframes = Array.from(
    slide.querySelectorAll(RUNTIME_SANDBOX_IFRAME_SELECTOR),
  );
  if (sandboxIframes.length > 0) {
    let inspectedSandboxIframe = 0;
    for (const node of sandboxIframes) {
      if (!(node instanceof HTMLIFrameElement)) {
        continue;
      }
      const isPrunableSandbox = isRuntimePrunableSandboxIframe(node);
      if (isPrunableSandbox === null) {
        continue;
      }
      inspectedSandboxIframe += 1;
      if (!isPrunableSandbox) {
        return false;
      }
    }
    if (inspectedSandboxIframe > 0) {
      return true;
    }
  }

  const hasEmptySvgContainer = Boolean(
    slide.querySelector(RUNTIME_EMPTY_SVG_CONTAINER_SELECTOR),
  );
  if (!hasEmptySvgContainer) {
    return false;
  }

  if (slide.querySelector(RUNTIME_VISUAL_CONTENT_SELECTOR)) {
    return false;
  }
  const textContent = normalizeRuntimeTextContent(slide.textContent);
  if (textContent.length > 0) {
    return false;
  }
  return hasEmptySvgContainer;
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

const buildRuntimePageRemap = (slides: unknown[]): Map<number, number> => {
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
    slides.forEach((_, page) => {
      remap.set(page, page);
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

export type AudioInteractionItem = ChatContentItem & {
  page: number;
  audioPosition?: number;
  audioSlideId?: string;
  /** Content block with visual slides but no audio to play. */
  isSilentVisual?: boolean;
};

export type ListenSlideItem = {
  item: ChatContentItem;
  segments: RenderSegment[];
};

const LISTEN_AUDIO_WATCHDOG_MIN_MS = 8000;
const LISTEN_AUDIO_WATCHDOG_FALLBACK_MS = 20000;
const LISTEN_AUDIO_WATCHDOG_DURATION_MULTIPLIER = 2;
const LISTEN_PENDING_GROWTH_WAIT_MS = 10000;

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

  const { slideItems, audioAndInteractionList } = useMemo(() => {
    let pageCursor = 0;
    let latestVisualPage = -1;
    const nextSlideItems: ListenSlideItem[] = [];
    const nextAudioAndInteractionList: AudioInteractionItem[] = [];
    const audioUnitIndexById = new Map<string, number>();

    const normalizedBackendSlides = (backendSlides || [])
      .filter(
        slide =>
          Boolean(slide?.slide_id) &&
          Boolean(slide?.generated_block_bid) &&
          Number.isFinite(Number(slide?.slide_index)),
      )
      .sort((a, b) => Number(a.slide_index) - Number(b.slide_index));
    // Backend sends NEW_SLIDE events as lightweight timeline signals without
    // segment_content (streaming_tts.py:827-830 clears it intentionally).
    // Therefore backend slides are used ONLY for position-to-page mapping and
    // slide-ID binding.  Rendering always uses local parsing of the accumulated
    // CONTENT stream (nextSlideItems).
    const backendPageByBlockPosition = new Map<string, number>();
    const backendSlideIdByBlockPosition = new Map<string, string>();
    let latestRenderableBackendPage = -1;
    normalizedBackendSlides.forEach(slide => {
      const blockBid = slide.generated_block_bid || '';
      const audioPosition = Number(slide.audio_position ?? 0);
      const key = `${blockBid}:${audioPosition}`;
      backendSlideIdByBlockPosition.set(key, slide.slide_id);
      if (isRenderableBackendSlide(slide)) {
        // Only visual boundary slides (iframe, svg, table, etc.) get their own
        // page.  Text-only slides share the page of the nearest visual so that
        // page numbering aligns with local visual-segment parsing.
        const isVisualBoundary = Boolean(
          slide.visual_kind &&
          slide.visual_kind !== '' &&
          slide.visual_kind !== 'placeholder',
        );
        if (isVisualBoundary) {
          latestRenderableBackendPage += 1;
        }
        backendPageByBlockPosition.set(
          key,
          Math.max(latestRenderableBackendPage, 0),
        );
        return;
      }
      // Non-renderable placeholder slides should not create extra pages.
      // Anchor their audio positions to the latest renderable page when possible.
      if (latestRenderableBackendPage >= 0) {
        backendPageByBlockPosition.set(key, latestRenderableBackendPage);
      }
    });
    let fallbackPlaceholderItem: ChatContentItem | null = null;
    type SegmentTuple = {
      sourceIndex: number;
      item: ChatContentItem;
      firstVisualPage: number;
      lastVisualPage: number;
      pagesForAudio: number[];
    };
    const contentSegments: SegmentTuple[] = [];

    items.forEach((item, sourceIndex) => {
      if (item.type !== ChatContentItemType.CONTENT) {
        return;
      }

      const segments = item.content
        ? splitListenModeSegments(item.content || '')
        : [];
      const previousVisualPageBeforeBlock = latestVisualPage;
      const visualSegments = segments.filter(isRenderableVisualSegment);
      if (!fallbackPlaceholderItem && visualSegments.length === 0) {
        const hasSpeakableText = segments.some(segment => {
          if (segment.type !== 'text') {
            return false;
          }
          const raw = typeof segment.value === 'string' ? segment.value : '';
          return isListenModeSpeakableText(raw);
        });
        if (hasSpeakableText) {
          fallbackPlaceholderItem = item;
        }
      }
      const visualPageBySegmentIndex = new Map<number, number>();
      let localVisualOffset = 0;
      segments.forEach((segment, segmentIndex) => {
        if (!isRenderableVisualSegment(segment)) {
          return;
        }
        visualPageBySegmentIndex.set(
          segmentIndex,
          pageCursor + localVisualOffset,
        );
        localVisualOffset += 1;
      });

      const firstVisualPage = visualSegments.length > 0 ? pageCursor : -1;
      const lastVisualPage =
        visualSegments.length > 0
          ? pageCursor + visualSegments.length - 1
          : latestVisualPage;
      if (visualSegments.length > 0) {
        nextSlideItems.push({
          item,
          segments: visualSegments,
        });
      }

      const pagesForAudioLocal: number[] = [];
      let windowHasSpeakableText = false;
      segments.forEach((segment, segmentIndex) => {
        if (segment.type === 'text') {
          const raw = typeof segment.value === 'string' ? segment.value : '';
          if (isListenModeSpeakableText(raw)) {
            windowHasSpeakableText = true;
          }
          return;
        }
        if (!isRenderableVisualSegment(segment)) {
          return;
        }
        if (windowHasSpeakableText) {
          pagesForAudioLocal.push(latestVisualPage);
          windowHasSpeakableText = false;
        }
        const pageForVisual = visualPageBySegmentIndex.get(segmentIndex);
        if (typeof pageForVisual === 'number') {
          latestVisualPage = pageForVisual;
        }
      });
      if (windowHasSpeakableText) {
        pagesForAudioLocal.push(latestVisualPage);
      }

      let pagesForAudio = pagesForAudioLocal;
      const contractSpeakable = item.avContract?.speakable_segments || [];
      const contractBoundaries = item.avContract?.visual_boundaries || [];
      if (contractSpeakable.length > 0) {
        const normalizedBoundaries = contractBoundaries
          .map(boundary => {
            const position = Number((boundary as any).position ?? -1);
            const sourceSpan = Array.isArray((boundary as any).source_span)
              ? ((boundary as any).source_span as number[])
              : [];
            const end = Number(sourceSpan[1] ?? -1);
            if (Number.isNaN(position) || Number.isNaN(end)) {
              return null;
            }
            return { position, end };
          })
          .filter(
            (boundary): boundary is { position: number; end: number } =>
              boundary !== null,
          )
          .sort((a, b) => a.position - b.position);
        const contractPages: number[] = [];
        contractSpeakable.forEach(segment => {
          const position = Number((segment as any).position ?? -1);
          const sourceSpan = Array.isArray((segment as any).source_span)
            ? ((segment as any).source_span as number[])
            : [];
          const sourceStart = Number(sourceSpan[0] ?? -1);
          if (Number.isNaN(position) || position < 0) {
            return;
          }
          const precedingBoundary =
            !Number.isNaN(sourceStart) && sourceStart >= 0
              ? normalizedBoundaries
                  .filter(boundary => boundary.end <= sourceStart)
                  .sort((a, b) => a.end - b.end)
                  .pop()
              : undefined;
          if (!precedingBoundary) {
            contractPages[position] = previousVisualPageBeforeBlock;
            return;
          }
          if (
            precedingBoundary.position >= visualSegments.length ||
            firstVisualPage < 0
          ) {
            // eslint-disable-next-line no-console
            console.warn('[listen-timeline] boundary/slide mismatch', {
              generated_block_bid: item.generated_block_bid,
              boundaryPosition: precedingBoundary.position,
              visualSlides: visualSegments.length,
              firstVisualPage,
            });
            contractPages[position] = previousVisualPageBeforeBlock;
            return;
          }
          contractPages[position] =
            firstVisualPage + precedingBoundary.position;
        });
        if (contractPages.some(page => typeof page === 'number')) {
          pagesForAudio = contractPages;
        }
      }

      contentSegments.push({
        sourceIndex,
        item,
        firstVisualPage,
        lastVisualPage,
        pagesForAudio,
      });

      pageCursor += visualSegments.length;
    });

    // Keep at least one renderable listen slide when a chapter contains only
    // plain text (no markdown/sandbox visual segments).
    if (!nextSlideItems.length && fallbackPlaceholderItem) {
      nextSlideItems.push({
        item: fallbackPlaceholderItem,
        segments: [{ type: 'sandbox', value: '<div></div>' }],
      });
    }

    const contentBySourceIndex = new Map<number, SegmentTuple>();
    contentSegments.forEach(contentSegment => {
      contentBySourceIndex.set(contentSegment.sourceIndex, contentSegment);
    });

    let activeTimelinePage = -1;
    items.forEach((item, sourceIndex) => {
      if (item.type === ChatContentItemType.CONTENT) {
        const contentSegment = contentBySourceIndex.get(sourceIndex);
        if (!contentSegment) {
          return;
        }
        const {
          item: contentItem,
          pagesForAudio,
          firstVisualPage,
          lastVisualPage,
        } = contentSegment;

        if (firstVisualPage >= 0) {
          activeTimelinePage = firstVisualPage;
        }
        if (!hasAnyAudioPayload(contentItem)) {
          // Show visual segments as silent-visual entries.
          // Two scenarios reach here:
          // 1. avContract present with empty speakable_segments → truly no audio
          // 2. avContract not yet received (still streaming) → provisionally
          //    silent; when the avContract arrives the list rebuilds via
          //    LIST_UPDATED and these entries will be replaced by audio entries.
          if (firstVisualPage >= 0 && lastVisualPage >= 0) {
            for (
              let vPage = firstVisualPage;
              vPage <= lastVisualPage;
              vPage++
            ) {
              nextAudioAndInteractionList.push({
                ...contentItem,
                page: vPage,
                isSilentVisual: true,
              });
            }
            activeTimelinePage = lastVisualPage;
          } else if (normalizedBackendSlides.length > 0) {
            const backendPagesForBlock = normalizedBackendSlides
              .filter(
                slide =>
                  slide.generated_block_bid === contentItem.generated_block_bid,
              )
              .map(slide =>
                backendPageByBlockPosition.get(
                  `${slide.generated_block_bid}:${Number(slide.audio_position ?? 0)}`,
                ),
              )
              .filter((page): page is number => typeof page === 'number');
            if (backendPagesForBlock.length > 0) {
              activeTimelinePage =
                backendPagesForBlock[backendPagesForBlock.length - 1];
            }
          } else if (lastVisualPage >= 0) {
            activeTimelinePage = lastVisualPage;
          }
          return;
        }

        const availablePositions = extractAudioPositions(contentItem);
        const hasMultiplePositions =
          availablePositions.length > 1 ||
          availablePositions.some(position => position > 0);
        const positions = hasMultiplePositions
          ? availablePositions.length
            ? availablePositions
            : [0]
          : [0];

        const fallbackPage =
          // When a position cannot be mapped to a concrete slide, anchor it to
          // the latest visual page of the current block so downstream
          // interactions stay on the page the learner most recently sees.
          (lastVisualPage >= 0 ? lastVisualPage : null) ??
          (firstVisualPage >= 0 ? firstVisualPage : null) ??
          (activeTimelinePage >= 0 ? activeTimelinePage : null) ??
          0;

        const coveredPages = new Set<number>();
        positions.forEach(position => {
          const mappedPage = pagesForAudio[position];
          const backendPage = backendPageByBlockPosition.get(
            `${contentItem.generated_block_bid}:${position}`,
          );
          const resolvedPage =
            typeof backendPage === 'number' && backendPage >= 0
              ? backendPage
              : typeof mappedPage === 'number' && mappedPage >= 0
                ? mappedPage
                : fallbackPage;
          coveredPages.add(resolvedPage);
          const audioSlideId =
            contentItem.audioSlideIdByPosition?.[position] ||
            backendSlideIdByBlockPosition.get(
              `${contentItem.generated_block_bid}:${position}`,
            );
          const timelineItem: AudioInteractionItem = {
            ...contentItem,
            page: resolvedPage,
            audioPosition: hasMultiplePositions ? position : undefined,
            audioSlideId,
          };
          const unitId = buildListenUnitId({
            type: ChatContentItemType.CONTENT,
            generatedBlockBid: contentItem.generated_block_bid,
            position,
            slideId: audioSlideId,
            fallbackIndex: sourceIndex,
          });
          const existingIndex = audioUnitIndexById.get(unitId);
          if (existingIndex !== undefined) {
            // Late-arriving audio/metadata updates for the same unit should patch
            // the existing queue slot rather than append a duplicate.
            nextAudioAndInteractionList[existingIndex] = timelineItem;
          } else {
            audioUnitIndexById.set(unitId, nextAudioAndInteractionList.length);
            nextAudioAndInteractionList.push(timelineItem);
          }
          activeTimelinePage = resolvedPage;
        });

        // Enqueue visual pages that have no associated audio as silent visuals.
        // This covers visual boundaries (e.g. tables, images) at the end of a
        // block where the backend produced no speakable segment after them.
        if (firstVisualPage >= 0 && lastVisualPage >= 0) {
          for (let vPage = firstVisualPage; vPage <= lastVisualPage; vPage++) {
            if (!coveredPages.has(vPage)) {
              nextAudioAndInteractionList.push({
                ...contentItem,
                page: vPage,
                isSilentVisual: true,
              });
              activeTimelinePage = vPage;
            }
          }
        }

        pagesForAudio.forEach((mappedPage, mappedPosition) => {
          if (mappedPage < 0) {
            return;
          }
          if (!positions.includes(mappedPosition)) {
            // eslint-disable-next-line no-console
            console.warn('[listen-timeline] slide exists but no position', {
              generated_block_bid: contentItem.generated_block_bid,
              position: mappedPosition,
              mappedPage,
            });
          }
        });
        return;
      }

      if (item.type !== ChatContentItemType.INTERACTION) {
        return;
      }
      const interactionPage = activeTimelinePage >= 0 ? activeTimelinePage : 0;
      nextAudioAndInteractionList.push({
        ...item,
        page: interactionPage,
      });
    });

    return {
      slideItems: nextSlideItems,
      audioAndInteractionList: nextAudioAndInteractionList,
    };
  }, [backendSlides, items]);

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
  onResetSequence?: () => void;
  getNextContentBid: (currentBid: string | null) => string | null;
  goToBlock: (blockBid: string) => boolean;
  resolveContentBid: (blockBid: string | null) => string | null;
  resolveRuntimeSequencePage: (page: number) => number;
  refreshRuntimePageRemap: () => boolean;
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
        onResetSequence?.();
      }
    } else if (prevFirstSlideBidRef.current !== firstSlideBid) {
      if (canResetToFirst) {
        shouldSlideToFirstRef.current = true;
        onResetSequence?.();
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
        onResetSequence?.();
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

    const handleSlideChanged = () => {
      syncActiveBlockFromDeck();
      syncPptPageFromDeck();
      updateNavState();
    };

    deck.on('slidechanged', handleSlideChanged as unknown as EventListener);
    deck.on('ready', handleSlideChanged as unknown as EventListener);

    return () => {
      deck.off('slidechanged', handleSlideChanged as unknown as EventListener);
      deck.off('ready', handleSlideChanged as unknown as EventListener);
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
          onResetSequence?.();
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
  const setIsAudioPlayingRef = useRef(setIsAudioPlaying);
  setIsAudioPlayingRef.current = setIsAudioPlaying;
  const bootstrapDrivenCycleRef = useRef(false);
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
      : Array.from(slides as unknown as ArrayLike<HTMLElement>);
  }, [deckRef]);

  const refreshRuntimePageRemap = useCallback(() => {
    const slides = collectDeckSlides();
    const nextMap = buildRuntimePageRemap(slides);
    if (arePageRemapMapsEqual(runtimePageRemapRef.current, nextMap)) {
      return false;
    }
    runtimePageRemapRef.current = nextMap;
    setRuntimePageRemapVersion(version => version + 1);
    return true;
  }, [collectDeckSlides]);

  const syncToSequencePage = useCallback(
    (page: number) => {
      if (page < 0) {
        return false;
      }
      refreshRuntimePageRemap();
      const resolvedPage = resolveRuntimeSequencePage(page);
      if (resolvedPage < 0) {
        return false;
      }
      const deck = deckRef.current;
      if (!deck) {
        return true;
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
        return true;
      }
      if (resolvedPage >= slidesLength) {
        return false;
      }

      try {
        deck.slide(resolvedPage);
      } catch {
        // Reveal.js may throw if controls are not yet initialized
        return false;
      }
      return true;
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
      return true;
    }
    if (resolveContentBid(activeBlockBidRef.current) !== currentBid) {
      activeBlockBidRef.current = currentBid;
    }
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      pendingAutoNextRef.current = true;
      return true;
    }

    const moved = goToBlock(nextBid);
    if (moved) {
      // Hint upcoming sequence resolution to the target block immediately.
      // Reveal's slidechanged callback can lag behind this call.
      activeBlockBidRef.current = nextBid;
      // Signal the bootstrap effect to auto-start the queue once new content
      // for the next block streams in and audioAndInteractionList rebuilds.
      shouldStartSequenceRef.current = true;
      return true;
    }

    if (shouldRenderEmptyPpt) {
      activeBlockBidRef.current = `empty-ppt-${nextBid}`;
      return true;
    }

    pendingAutoNextRef.current = true;
    return true;
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
          // The target block has not streamed into the list yet.
          // Avoid falling back to stale items from the previous block.
          return -1;
        }

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
  // Stable refs for queue event handlers to avoid re-subscription cycles
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
      setIsAudioPlayingRef.current(false);
      setActiveAudioBid(item.generatedBlockBid);
      setActiveAudioPosition(item.audioPosition);
      setActiveQueueAudioId(item.id);
      setAudioSequenceToken(prev => prev + 1);
      setIsAudioSequenceActive(true);
      syncToSequencePageRef.current(item.page);
    },
    [pendingAutoNextRef],
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
    const listLengthBeforeCompletion = audioAndInteractionList.length;
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

    pendingAutoNextRef.current = false;
    pendingQueueGrowthAnchorRef.current = null;
    shouldStartSequenceRef.current = false;
    clearPendingGrowthWaitTimer();
    lastAdvanceCauseRef.current = 'other';
    bootstrapDrivenCycleRef.current = false;
  }, [
    activeBlockBidRef,
    audioAndInteractionList.length,
    bootstrapDrivenCycleRef,
    clearPendingGrowthWaitTimer,
    effectiveStartAnchorIndexRef,
    lastAdvanceCauseRef,
    pendingQueueGrowthAnchorRef,
    pendingAutoNextRef,
    pendingGrowthWaitTimerRef,
    resolveContentBid,
    setIsAudioSequenceActive,
    shouldStartSequenceRef,
  ]);

  const queueActions = useQueueManager({
    audioWaitTimeout: 15000,
    onVisualShow: onVisualShowHandler,
    onAudioPlay: onAudioPlayHandler,
    onInteractionShow: onInteractionShowHandler,
    onQueueCompleted: onQueueCompletedHandler,
  });

  // Ref to break circular dependency: silent visual timer → queueActions.advance
  const queueActionsRef = useRef(queueActions);
  queueActionsRef.current = queueActions;

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

  const toQueueAudioSegmentValue = useCallback((segment: unknown) => {
    if (typeof segment === 'string') {
      return segment;
    }
    return (segment as any).audioData || (segment as any).audio_segment;
  }, []);

  const upsertQueueAudioUrlIfNeeded = useCallback(
    (bid: string, position: number, audioUrl?: string, isFinal = true) => {
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
      } = resolvedTrack;
      const audioKey = `${bid}:${position}`;
      const prevState = syncedAudioStateRef.current.get(audioKey);

      if (audioUrl) {
        // URL source supersedes segmented updates.
        upsertQueueAudioUrlIfNeeded(bid, position, audioUrl, !isAudioStreaming);
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
    [queueActions, toQueueAudioSegmentValue, upsertQueueAudioUrlIfNeeded],
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
      if (
        item.status === 'completed' ||
        item.status === 'timeout' ||
        item.status === 'error'
      ) {
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

    const slidesRoot =
      (typeof (deck as { getSlidesElement?: unknown }).getSlidesElement ===
      'function'
        ? (
            deck as unknown as {
              getSlidesElement: () => Element | null;
            }
          ).getSlidesElement()
        : null) ||
      (typeof (deck as { getRevealElement?: unknown }).getRevealElement ===
      'function'
        ? (
            deck as unknown as {
              getRevealElement: () => Element | null;
            }
          ).getRevealElement()
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

  // Keep audioSequenceTokenRef in sync
  useEffect(() => {
    audioSequenceTokenRef.current = audioSequenceToken;
  }, [audioSequenceToken]);

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
  useEffect(() => {
    audioAndInteractionLengthRef.current = audioAndInteractionList.length;
  }, [audioAndInteractionList.length]);

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
      bootstrapDrivenCycleRef.current = false;
      endSequence();
    }, 800);
    return () => clearTimeout(timer);
  }, [
    audioAndInteractionList.length,
    endSequence,
    bootstrapDrivenCycleRef,
    clearPendingGrowthWaitTimer,
    effectiveStartAnchorIndexRef,
    pendingQueueGrowthAnchorRef,
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
      if (pendingResumeIndex < 0) {
        return;
      }
      queueActions.startFromIndex(pendingResumeIndex);
      pendingQueueGrowthAnchorRef.current = null;
      clearPendingGrowthWaitTimer();
      shouldStartSequenceRef.current = false;
      bootstrapDrivenCycleRef.current = true;
      return;
    }

    const currentPage =
      deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
    const startIndex = resolvePlaybackStartIndex(currentPage);
    if (startIndex < 0) {
      return;
    }
    const started = startQueueFromListIndex(startIndex, { resyncOnMiss: true });
    if (!started) {
      return;
    }
    shouldStartSequenceRef.current = false;
    bootstrapDrivenCycleRef.current = true;
  }, [
    audioAndInteractionList,
    bootstrapDrivenCycleRef,
    clearPendingGrowthWaitTimer,
    currentPptPageRef,
    deckRef,
    pendingQueueGrowthAnchorRef,
    queueActions,
    resolvePendingResumeQueueIndex,
    resolvePlaybackStartIndex,
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
            durationMs: 0,
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

    const fallbackTrack = resolveListenAudioTrack(
      activeContentItem,
      activeAudioPosition,
    );
    const normalizedFallbackTrack = {
      audioUrl: fallbackTrack.audioUrl,
      streamingSegments: fallbackTrack.audioSegments ?? [],
      isStreaming: fallbackTrack.isAudioStreaming,
      durationMs: fallbackTrack.audioDurationMs,
    };
    if (hasPlayableResolvedTrack(fallbackTrack)) {
      return normalizedFallbackTrack;
    }

    return queueTrack ?? normalizedFallbackTrack;
  }, [
    activeQueueAudioId,
    activeAudioBid,
    activeAudioPosition,
    activeContentItem,
    hasPlayableResolvedTrack,
    queueActions,
  ]);

  const activeAudioDurationMs = useMemo(() => {
    if (Number.isFinite(activeAudioTrack?.durationMs)) {
      const duration = Number(activeAudioTrack?.durationMs);
      if (duration > 0) {
        return duration;
      }
    }

    if (!activeContentItem) {
      return undefined;
    }

    const resolvedTrack = resolveListenAudioTrack(
      activeContentItem,
      activeAudioPosition,
    );
    const explicitDuration = resolvedTrack.audioDurationMs;
    if (Number.isFinite(explicitDuration) && (explicitDuration || 0) > 0) {
      return explicitDuration;
    }

    const segments = resolvedTrack.audioSegments;
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
  }, [activeAudioPosition, activeAudioTrack?.durationMs, activeContentItem]);

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
            queueItem.status !== 'completed' &&
            queueItem.status !== 'timeout' &&
            queueItem.status !== 'error',
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
      // Keep runtime consistent with sequence expectations: audio errors pause
      // progression and require an explicit user resume/next action.
      isSequencePausedRef.current = true;
      setIsAudioPlaying(false);
      queueActions.pause();
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
      // Keep sequence blocked until learner explicitly submits interaction.
      return;
    }

    if (!activeAudioBid && audioAndInteractionList.length) {
      if (pendingAutoNextRef.current) {
        // The sequence is waiting for the next block to stream in.
        // Avoid replaying the current block while auto-next is pending.
        const pendingResumeIndex = resolvePendingResumeQueueIndex();
        if (pendingResumeIndex >= 0) {
          pendingQueueGrowthAnchorRef.current = null;
          clearPendingGrowthWaitTimer();
          queueActions.startFromIndex(pendingResumeIndex);
          shouldStartSequenceRef.current = false;
          setIsAudioSequenceActive(true);
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
        queueActions.resume();
        return;
      }
      bootstrapDrivenCycleRef.current = false;
      if (!startQueueFromListIndex(startIndex, { resyncOnMiss: true })) {
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
    bootstrapDrivenCycleRef,
    clearPendingGrowthWaitTimer,
    currentPptPageRef,
    deckRef,
    pendingAutoNextRef,
    pendingQueueGrowthAnchorRef,
    previewMode,
    queueActions,
    resolvePendingResumeQueueIndex,
    resolvePlaybackStartIndex,
    setIsAudioSequenceActive,
    sequenceInteraction,
    startQueueFromListIndex,
    shouldStartSequenceRef,
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

  const handleUserPrev = useCallback(() => {
    if (previewMode) {
      return;
    }
  }, [previewMode]);

  const handleUserNext = useCallback(() => {
    if (previewMode) {
      return;
    }
  }, [previewMode]);

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
      bootstrapDrivenCycleRef.current = false;
      syncListToQueue(audioAndInteractionList);
      startQueueFromListIndex(index);
    },
    [
      audioAndInteractionList,
      bootstrapDrivenCycleRef,
      clearPendingGrowthWaitTimer,
      effectiveStartAnchorIndexRef,
      pendingQueueGrowthAnchorRef,
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
      queueActionsRef.current?.advance();
    }, audioWatchdogTimeoutMs);
    return () => clearTimeout(timer);
  }, [
    isAudioSequenceActive,
    activeAudioBid,
    isAudioPlaying,
    isAudioPlayerBusy,
    audioWatchdogTimeoutMs,
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
      queueActionsRef.current?.advance();
    }, maxMs);
    return () => clearTimeout(timer);
  }, [
    isAudioSequenceActive,
    isAudioPlaying,
    activeAudioDurationMs,
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
    handleUserPrev,
    handleUserNext,
    continueAfterInteraction,
    startSequenceFromIndex,
    startSequenceFromPage,
    resolveRuntimeSequencePage,
    refreshRuntimePageRemap,
  };
};
