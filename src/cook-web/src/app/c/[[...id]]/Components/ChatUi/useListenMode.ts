import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Reveal, { Options } from 'reveal.js';
import {
  splitContentSegments,
  type RenderSegment,
} from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import type { AudioPlayerHandle } from '@/components/audio/AudioPlayer';
import {
  buildListenUnitId,
  extractAudioPositions,
} from '@/c-utils/listen-orchestrator';
import type { ListenSlideData } from '@/c-api/studyV2';
import {
  type HtmlSandboxRootTag,
  SANDBOX_ROOT_TAGS,
  FIXED_MARKER_PATTERN,
  markdownTableToSandboxHtml,
  findFirstTextVisualBlock,
} from '@/c-utils/listen-mode';
import { useQueueManager } from '@/c-utils/listen-mode/use-queue-manager';
import type {
  QueueEvent,
  VisualQueueItem,
  AudioQueueItem,
  InteractionQueueItem,
} from '@/c-utils/listen-mode/queue-manager';

const isFixedMarkerText = (raw: string) => {
  const trimmed = (raw || '').trim();
  return Boolean(trimmed && FIXED_MARKER_PATTERN.test(trimmed));
};

const isListenModeSpeakableText = (raw: string) => {
  const trimmed = (raw || '').trim();
  if (trimmed.length < 2) {
    return false;
  }
  // Avoid synthesizing MarkdownFlow fixed marker delimiters such as `===`/`!===`.
  if (isFixedMarkerText(trimmed)) {
    return false;
  }
  return true;
};

const splitTextByVisualBlocks = (raw: string): RenderSegment[] => {
  if (!raw || !raw.trim()) {
    return [];
  }

  const block = findFirstTextVisualBlock(raw);
  if (!block) {
    return [{ type: 'text', value: raw }];
  }

  const before = raw.slice(0, block.start);
  const matched = raw.slice(block.start, block.end);
  const after = raw.slice(block.end);

  const output: RenderSegment[] = [];
  if (before.trim()) {
    output.push({ type: 'text', value: before });
  }
  if (block.kind === 'markdown-table') {
    const markdownTableSandbox = markdownTableToSandboxHtml(matched);
    if (markdownTableSandbox) {
      output.push({
        type: 'sandbox',
        value: markdownTableSandbox,
      });
    } else {
      output.push({
        type: 'markdown',
        value: matched,
      });
    }
  } else {
    if (block.kind === 'iframe') {
      output.push({
        type: 'sandbox',
        value: matched,
      });
    } else if (block.kind === 'table') {
      // In blackboard mode, IframeSandbox only mounts content extracted from
      // sandbox-root HTML blocks. Wrap bare <table> so it renders in sandbox.
      output.push({
        type: 'sandbox',
        value: `<div>${matched}</div>`,
      });
    } else {
      output.push({
        type: 'markdown',
        value: matched,
      });
    }
  }
  if (after.trim()) {
    output.push(...splitTextByVisualBlocks(after));
  }
  return output;
};

const splitSandboxByRootBoundary = (
  raw: string,
): { head: string; rest: string } | null => {
  if (!raw || !raw.trim()) {
    return null;
  }

  const trimmed = raw.trimStart();
  const lower = trimmed.toLowerCase();
  const match = lower.match(/^<([a-z0-9-]+)/);
  if (!match) {
    return null;
  }

  const tag = match[1] as HtmlSandboxRootTag;
  if (!SANDBOX_ROOT_TAGS.includes(tag)) {
    return null;
  }

  const closeTag = `</${tag}>`;
  const closeIdx =
    tag === 'iframe' ? lower.indexOf(closeTag) : lower.lastIndexOf(closeTag);
  if (closeIdx === -1) {
    return null;
  }

  let end = closeIdx + closeTag.length;
  // Keep trailing fixed markers on the same line (e.g. `</div> ===`).
  const nl = trimmed.indexOf('\n', end);
  const lineEnd = nl === -1 ? trimmed.length : nl;
  const tail = trimmed.slice(end, lineEnd);
  if (/^[\s!=]*$/.test(tail)) {
    end = nl === -1 ? trimmed.length : nl + 1;
  }

  if (end <= 0 || end >= trimmed.length) {
    return null;
  }

  const rest = trimmed.slice(end);
  if (!rest.trim()) {
    return null;
  }

  return { head: trimmed.slice(0, end), rest };
};

const mergeHtmlTableSegments = (segments: RenderSegment[]): RenderSegment[] => {
  if (!segments.length) {
    return segments;
  }

  const output: RenderSegment[] = [];

  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index];
    const raw = typeof segment.value === 'string' ? segment.value : '';
    if (!raw) {
      output.push(segment);
      continue;
    }
    const lower = raw.toLowerCase();
    const tableStart = lower.indexOf('<table');
    if (tableStart === -1) {
      output.push(segment);
      continue;
    }

    // If the closing tag is already present, keep the segment intact.
    // `splitTextByVisualBlocks()` will handle turning it into a visual sandbox segment.
    if (lower.indexOf('</table', tableStart) !== -1) {
      output.push(segment);
      continue;
    }

    // Merge forward to reconstruct tables that were split by other HTML/markdown
    // detectors (e.g. <img> inside <table>), otherwise the table ends up as
    // non-visual `text` and gets dropped from slides.
    let merged = raw;
    let mergedLower = lower;
    let foundClose = false;
    let nextIndex = index;

    for (let scan = index + 1; scan < segments.length; scan += 1) {
      const next = segments[scan];
      const nextValue = typeof next.value === 'string' ? next.value : '';
      const nextLower = nextValue.toLowerCase();
      merged += nextValue;
      mergedLower += nextLower;
      if (mergedLower.includes('</table')) {
        foundClose = true;
        nextIndex = scan;
        break;
      }
    }

    if (!foundClose) {
      output.push(segment);
      continue;
    }

    output.push({ ...segment, value: merged });
    index = nextIndex;
  }

  return output;
};

const splitListenModeSegments = (raw: string): RenderSegment[] => {
  const baseSegments = mergeHtmlTableSegments(
    splitContentSegments(raw || '', true),
  );
  if (!baseSegments.length) {
    return baseSegments;
  }

  const output: RenderSegment[] = [];
  baseSegments.forEach((segment, index) => {
    if (segment.type !== 'text') {
      if (segment.type === 'sandbox') {
        const sandboxRaw =
          typeof segment.value === 'string' ? segment.value : '';
        const sandboxTrimmed = sandboxRaw.trimStart();
        if (
          /^\s*<table\b/i.test(sandboxTrimmed) &&
          /<\/table\b/i.test(sandboxTrimmed)
        ) {
          output.push({
            type: 'sandbox',
            value: `<div>${sandboxTrimmed}</div>`,
          });
          return;
        }

        const split = splitSandboxByRootBoundary(segment.value || '');
        if (split) {
          output.push({ type: 'sandbox', value: split.head });
          output.push(...splitListenModeSegments(split.rest));
          return;
        }
      }
      if (segment.type === 'markdown') {
        const markdownRaw =
          typeof segment.value === 'string' ? segment.value : '';
        const markdownTableSandbox = markdownTableToSandboxHtml(markdownRaw);
        if (markdownTableSandbox) {
          output.push({
            type: 'sandbox',
            value: markdownTableSandbox,
          });
          return;
        }

        // splitContentSegments() can return raw HTML blocks (including <table>)
        // as markdown segments. In blackboard mode, we need to wrap <table>
        // with a sandbox-root container so it renders.
        if (
          !/^\s*```/.test(markdownRaw) &&
          !/^\s*~~~/.test(markdownRaw) &&
          (/<table\b/i.test(markdownRaw) ||
            /<iframe\b/i.test(markdownRaw) ||
            /<video\b/i.test(markdownRaw))
        ) {
          output.push(...splitTextByVisualBlocks(markdownRaw));
          return;
        }
      }
      output.push(segment);
      return;
    }

    // Drop fixed marker-only segments that would otherwise become speakable.
    const next = baseSegments[index + 1];
    if (
      isFixedMarkerText(segment.value) &&
      next &&
      (next.type === 'sandbox' || next.type === 'markdown')
    ) {
      return;
    }

    output.push(...splitTextByVisualBlocks(segment.value));
  });

  return output;
};

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
const LISTEN_AUDIO_WATCHDOG_DURATION_MARGIN_MS = 4000;

const resolveListenAudioWatchdogMs = (audioDurationMs?: number) => {
  const duration = Number(audioDurationMs);
  if (Number.isFinite(duration) && duration > 0) {
    return Math.max(
      LISTEN_AUDIO_WATCHDOG_MIN_MS,
      Math.floor(duration) + LISTEN_AUDIO_WATCHDOG_DURATION_MARGIN_MS,
    );
  }
  return LISTEN_AUDIO_WATCHDOG_FALLBACK_MS;
};

const hasAnyAudioPayload = (item: ChatContentItem): boolean => {
  const hasAnySegmentedAudio = Boolean(
    (item.audios && item.audios.length > 0) ||
    (item.audioTracksByPosition &&
      Object.keys(item.audioTracksByPosition).length > 0),
  );
  const hasContractAudioPositions = Boolean(
    item.avContract?.speakable_segments &&
    item.avContract.speakable_segments.length > 0,
  );
  return Boolean(
    item.audioUrl ||
    (item.audioSegments && item.audioSegments.length > 0) ||
    item.isAudioStreaming ||
    hasAnySegmentedAudio ||
    hasContractAudioPositions,
  );
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

  const { lastInteractionBid, lastItemIsInteraction } = useMemo(() => {
    let latestInteractionBid: string | null = null;
    for (let i = items.length - 1; i >= 0; i -= 1) {
      if (items[i].type === ChatContentItemType.INTERACTION) {
        latestInteractionBid = items[i].generated_block_bid;
        break;
      }
    }
    const lastItem = items[items.length - 1];
    return {
      lastInteractionBid: latestInteractionBid,
      lastItemIsInteraction: lastItem?.type === ChatContentItemType.INTERACTION,
    };
  }, [items]);

  const ttsReadyBlockBids = useMemo(() => {
    const ready = new Set<string>();
    for (const item of items) {
      if (item.type !== ChatContentItemType.LIKE_STATUS) {
        continue;
      }
      const parentBid = item.parent_block_bid;
      if (!parentBid) {
        continue;
      }
      ready.add(parentBid);
    }
    return ready;
  }, [items]);

  const {
    slideItems,
    interactionByPage,
    audioAndInteractionList,
    audioPageByBid,
  } = useMemo(() => {
    let pageCursor = 0;
    let latestVisualPage = -1;
    const interactionMapping = new Map<number, ChatContentItem[]>();
    const audioPageByBid = new Map<string, number[]>();
    const nextSlideItems: ListenSlideItem[] = [];
    const nextAudioAndInteractionList: AudioInteractionItem[] = [];
    const audioUnitIndexById = new Map<string, number>();
    const contentItemByBid = new Map<string, ChatContentItem>();
    for (const item of items) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      if (!item.generated_block_bid || item.generated_block_bid === 'loading') {
        continue;
      }
      contentItemByBid.set(item.generated_block_bid, item);
    }

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
      segments: RenderSegment[];
      visualSegments: RenderSegment[];
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
      const visualSegments = segments.filter(
        segment => segment.type === 'markdown' || segment.type === 'sandbox',
      );
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
        if (segment.type !== 'markdown' && segment.type !== 'sandbox') {
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
        if (segment.type !== 'markdown' && segment.type !== 'sandbox') {
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

      const blockBid = item.generated_block_bid;
      if (blockBid && blockBid !== 'loading') {
        audioPageByBid.set(blockBid, pagesForAudio);
      }

      contentSegments.push({
        sourceIndex,
        item,
        segments,
        visualSegments,
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
      const queue = interactionMapping.get(interactionPage) || [];
      interactionMapping.set(interactionPage, [...queue, item]);
      nextAudioAndInteractionList.push({
        ...item,
        page: interactionPage,
      });
    });

    return {
      slideItems: nextSlideItems,
      interactionByPage: interactionMapping,
      audioAndInteractionList: nextAudioAndInteractionList,
      audioPageByBid,
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
    interactionByPage,
    audioAndInteractionList,
    audioPageByBid,
    contentByBid,
    audioContentByBid,
    ttsReadyBlockBids,
    lastInteractionBid,
    lastItemIsInteraction,
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
  interactionByPage: Map<number, ChatContentItem[]>;
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
}

export const useListenPpt = ({
  chatRef,
  deckRef,
  currentPptPageRef,
  activeBlockBidRef,
  pendingAutoNextRef,
  slideItems,
  interactionByPage,
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
}: UseListenPptParams) => {
  const prevSlidesLengthRef = useRef(0);
  const shouldSlideToFirstRef = useRef(false);
  const hasAutoSlidToLatestRef = useRef(false);
  const prevFirstSlideBidRef = useRef<string | null>(null);
  const prevSectionTitleRef = useRef<string | null>(null);
  const [currentInteraction, setCurrentInteraction] =
    useState<ChatContentItem | null>(null);
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

  const syncInteractionForCurrentPage = useCallback(
    (pageIndex?: number) => {
      const targetPage =
        typeof pageIndex === 'number' ? pageIndex : currentPptPageRef.current;
      const queue = interactionByPage.get(targetPage) || [];
      setCurrentInteraction(queue[queue.length - 1] ?? null);
    },
    [interactionByPage, currentPptPageRef],
  );

  const syncPptPageFromDeck = useCallback(() => {
    const deck = deckRef.current;
    if (!deck) {
      return;
    }
    const nextIndex = deck.getIndices()?.h ?? 0;
    if (currentPptPageRef.current === nextIndex) {
      return;
    }
    currentPptPageRef.current = nextIndex;
    syncInteractionForCurrentPage(nextIndex);
  }, [currentPptPageRef, deckRef, syncInteractionForCurrentPage]);

  useEffect(() => {
    syncInteractionForCurrentPage();
  }, [syncInteractionForCurrentPage]);

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
    return goToBlock(nextBid);
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
        console.log('Destroying Reveal instance (no content)');
        deckRef.current?.destroy();
      } catch (e) {
        console.warn('Reveal.js destroy failed.');
      } finally {
        deckRef.current = null;
        hasAutoSlidToLatestRef.current = false;
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
      } catch (e) {
        console.warn('Reveal.js destroy failed.');
      } finally {
        deckRef.current = null;
        hasAutoSlidToLatestRef.current = false;
        prevSlidesLengthRef.current = 0;
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
      const indices = deckRef.current.getIndices?.();
      const prevSlidesLength = prevSlidesLengthRef.current;
      const nextSlidesLength = slides.length;
      const lastIndex = Math.max(nextSlidesLength - 1, 0);
      const currentIndex = indices?.h ?? 0;
      const prevLastIndex = Math.max(prevSlidesLength - 1, 0);

      if (shouldSlideToFirstRef.current) {
        deckRef.current.slide(0);
        shouldSlideToFirstRef.current = false;
        hasAutoSlidToLatestRef.current = true;
        updateNavState();
        prevSlidesLengthRef.current = nextSlidesLength;
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
        prevSlidesLengthRef.current = nextSlidesLength;
        return;
      }

      hasAutoSlidToLatestRef.current = true;
      updateNavState();
      prevSlidesLengthRef.current = nextSlidesLength;
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
    goToBlock,
    chatRef,
    updateNavState,
    deckRef,
    pendingAutoNextRef,
    onResetSequence,
    resolveContentBid,
  ]);

  const goPrev = useCallback(() => {
    const deck = deckRef.current;
    if (!deck || isPrevDisabled) {
      return null;
    }
    shouldSlideToFirstRef.current = false;
    hasAutoSlidToLatestRef.current = true;
    deck.prev();
    currentPptPageRef.current = deck.getIndices().h;
    syncInteractionForCurrentPage(currentPptPageRef.current);
    updateNavState();
    return currentPptPageRef.current;
  }, [
    deckRef,
    isPrevDisabled,
    currentPptPageRef,
    syncInteractionForCurrentPage,
    updateNavState,
  ]);

  const goNext = useCallback(() => {
    const deck = deckRef.current;
    if (!deck || isNextDisabled) {
      return null;
    }
    shouldSlideToFirstRef.current = false;
    hasAutoSlidToLatestRef.current = true;
    deck.next();
    currentPptPageRef.current = deck.getIndices().h;
    syncInteractionForCurrentPage(currentPptPageRef.current);
    updateNavState();
    return currentPptPageRef.current;
  }, [
    deckRef,
    isNextDisabled,
    currentPptPageRef,
    syncInteractionForCurrentPage,
    updateNavState,
  ]);

  return {
    currentInteraction,
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
  const [activeAudioBid, setActiveAudioBid] = useState<string | null>(null);
  const [activeAudioPosition, setActiveAudioPosition] = useState(0);
  const [activeSequencePage, setActiveSequencePage] = useState(-1);
  const [sequenceInteraction, setSequenceInteraction] =
    useState<AudioInteractionItem | null>(null);
  const [isAudioSequenceActive, setIsAudioSequenceActive] = useState(false);
  const [audioSequenceToken, setAudioSequenceToken] = useState(0);
  const audioSequenceTokenRef = useRef(0);
  const hasObservedPlaybackRef = useRef(false);
  const isSequencePausedRef = useRef(false);
  // Track the last synced list length to detect new items for queue sync
  const lastSyncedListRef = useRef<AudioInteractionItem[]>([]);
  // Track synced audio state per item to avoid duplicate upsertAudio calls.
  // Key: "bid:position", value: { count: segments synced, finalized: true if is_final sent } or 'url'
  const syncedAudioStateRef = useRef<
    Map<string, { count: number; finalized: boolean } | 'url'>
  >(new Map());

  // ---------------------------------------------------------------------------
  // Helpers preserved from original
  // ---------------------------------------------------------------------------
  const hasPlayableAudioForItem = useCallback((item: AudioInteractionItem) => {
    if (item.type !== ChatContentItemType.CONTENT) {
      return true;
    }
    const position = item.audioPosition ?? 0;
    const track = item.audioTracksByPosition?.[position];
    const persisted = (item.audios || [])
      .filter(audio => Number(audio.position ?? 0) === position)
      .pop();
    const legacyForZero = position === 0;
    const hasUrl = Boolean(
      track?.audioUrl ||
      persisted?.audio_url ||
      (legacyForZero && item.audioUrl),
    );
    const hasSegments = Boolean(
      (track?.audioSegments && track.audioSegments.length > 0) ||
      (legacyForZero && item.audioSegments && item.audioSegments.length > 0),
    );
    const isStreaming = Boolean(
      track?.isAudioStreaming || (legacyForZero && item.isAudioStreaming),
    );
    return hasUrl || hasSegments || isStreaming;
  }, []);

  const syncToSequencePage = useCallback(
    (page: number) => {
      if (page < 0) {
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
      } catch (_e) {
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
      if (page >= slidesLength) {
        return false;
      }

      try {
        deck.slide(page);
      } catch (_e) {
        // Reveal.js may throw if controls are not yet initialized
        return false;
      }
      return true;
    },
    [deckRef],
  );

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
    shouldRenderEmptyPpt,
  ]);

  const endSequence = useCallback(
    (options?: { tryAdvanceToNextBlock?: boolean }) => {
      setSequenceInteraction(null);
      setActiveAudioBid(null);
      setActiveAudioPosition(0);
      setActiveSequencePage(-1);
      setIsAudioSequenceActive(false);
      isSequencePausedRef.current = false;
      if (options?.tryAdvanceToNextBlock) {
        tryAdvanceToNextBlock();
      }
    },
    [tryAdvanceToNextBlock],
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
      const list = audioAndInteractionList;

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
        const preferredSamePageIndex = list.findIndex(
          item =>
            item.type === ChatContentItemType.CONTENT &&
            item.page === page &&
            resolveContentBid(item.generated_block_bid) === preferredBid,
        );
        if (preferredSamePageIndex >= 0) {
          return preferredSamePageIndex;
        }
        const preferredAheadIndex = list.findIndex(
          item =>
            item.type === ChatContentItemType.CONTENT &&
            item.page >= page &&
            resolveContentBid(item.generated_block_bid) === preferredBid,
        );
        if (preferredAheadIndex >= 0) {
          return preferredAheadIndex;
        }
      }

      for (let i = list.length - 1; i >= 0; i -= 1) {
        const item = list[i];
        if (item.page === page && item.type === ChatContentItemType.CONTENT) {
          return i;
        }
      }
      const nextAudioIndex = list.findIndex(
        item => item.page > page && item.type === ChatContentItemType.CONTENT,
      );
      if (nextAudioIndex >= 0) {
        return nextAudioIndex;
      }
      const pageIndex = list.findIndex(item => item.page === page);
      if (pageIndex >= 0) {
        return pageIndex;
      }
      return list.findIndex(item => item.page > page);
    },
    [
      activeAudioBid,
      activeBlockBidRef,
      audioAndInteractionList,
      deckRef,
      resolveContentBid,
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
    console.log(
      `[Queue→Seq] visual:show bid=${item.generatedBlockBid} page=${item.page}`,
    );
    setActiveSequencePage(item.page);
    setIsAudioSequenceActive(true);

    const pageReady = syncToSequencePageRef.current(item.page);
    if (!pageReady) {
      console.warn(`[Queue→Seq] Slide page ${item.page} not ready for visual`);
    }

    if (!item.hasTextAfterVisual) {
      // Silent visual — queue manager handles auto-advance internally
      setSequenceInteraction(null);
      setActiveAudioBid(null);
    }
  }, []);

  const onAudioPlayHandler = useCallback((event: QueueEvent) => {
    const item = event.item as AudioQueueItem;
    console.log(
      `[Queue→Seq] audio:play bid=${item.generatedBlockBid} pos=${item.audioPosition}`,
    );
    setActiveAudioBid(item.generatedBlockBid);
    setActiveAudioPosition(item.audioPosition);
    setActiveSequencePage(item.page);
    setAudioSequenceToken(prev => prev + 1);
    setIsAudioSequenceActive(true);
  }, []);

  const onInteractionShowHandler = useCallback((event: QueueEvent) => {
    const item = event.item as InteractionQueueItem;
    console.log(`[Queue→Seq] interaction:show bid=${item.generatedBlockBid}`);
    setSequenceInteraction({
      ...item.contentItem,
      page: item.page,
    });
    setActiveAudioBid(null);
    setActiveSequencePage(item.page);
    setIsAudioSequenceActive(true);
  }, []);

  const onQueueCompletedHandler = useCallback((_event: QueueEvent) => {
    console.log('[Queue→Seq] queue:completed');
    endSequenceRef.current({ tryAdvanceToNextBlock: true });
  }, []);

  const onQueueErrorHandler = useCallback((event: QueueEvent) => {
    console.warn(`[Queue→Seq] queue:error reason=${event.reason}`, event.item);
  }, []);

  const queueActions = useQueueManager({
    enabled: true,
    audioWaitTimeout: 15000,
    onVisualShow: onVisualShowHandler,
    onAudioPlay: onAudioPlayHandler,
    onInteractionShow: onInteractionShowHandler,
    onQueueCompleted: onQueueCompletedHandler,
    onQueueError: onQueueErrorHandler,
  });

  // Ref to break circular dependency: silent visual timer → queueActions.advance
  const queueActionsRef = useRef(queueActions);
  queueActionsRef.current = queueActions;

  // ---------------------------------------------------------------------------
  // syncListToQueue — sync audioAndInteractionList into the queue
  // ---------------------------------------------------------------------------
  const syncListToQueue = useCallback(
    (list: AudioInteractionItem[]) => {
      list.forEach((item, index) => {
        const bid = item.generated_block_bid;
        if (!bid || bid === 'loading') {
          return;
        }
        const position = item.audioPosition ?? 0;

        if (item.type === ChatContentItemType.INTERACTION) {
          queueActions.enqueueInteraction({
            generatedBlockBid: bid,
            page: item.page,
            contentItem: item,
            nextIndex: index < list.length - 1 ? index + 1 : null,
          });
          return;
        }

        // CONTENT item
        if (item.isSilentVisual) {
          // Silent visual — no audio expected
          queueActions.enqueueVisual({
            generatedBlockBid: bid,
            position,
            page: item.page,
            hasTextAfterVisual: false,
          });
          return;
        }

        // Content with audio
        const hasAudio = hasPlayableAudioForItem(item);
        queueActions.enqueueVisual({
          generatedBlockBid: bid,
          position,
          page: item.page,
          hasTextAfterVisual: true,
        });

        if (hasAudio) {
          // Build audio segment data from the content item
          const track = item.audioTracksByPosition?.[position];
          const persisted = (item.audios || [])
            .filter(audio => Number(audio.position ?? 0) === position)
            .pop();
          const legacyForZero = position === 0;
          const audioUrl =
            track?.audioUrl ||
            persisted?.audio_url ||
            (legacyForZero ? item.audioUrl : undefined);
          const segments =
            track?.audioSegments ??
            (legacyForZero ? item.audioSegments : undefined);
          const isStreaming = Boolean(
            track?.isAudioStreaming || (legacyForZero && item.isAudioStreaming),
          );

          const audioKey = `${bid}:${position}`;
          const prevState = syncedAudioStateRef.current.get(audioKey);

          if (audioUrl) {
            // Only upsert URL if not already sent
            if (prevState !== 'url') {
              queueActions.upsertAudio(bid, position, {
                audio_url: audioUrl,
                is_final: !isStreaming,
              });
              syncedAudioStateRef.current.set(audioKey, 'url');
            }
          } else if (segments && segments.length > 0) {
            // Only send NEW segments (skip already-synced ones)
            const prev =
              prevState !== 'url' && prevState
                ? prevState
                : { count: 0, finalized: false };
            const newSegments = segments.length > prev.count;
            const nowFinalized = !isStreaming;

            if (newSegments) {
              for (let i = prev.count; i < segments.length; i++) {
                const seg = segments[i];
                queueActions.upsertAudio(bid, position, {
                  audio_segment:
                    typeof seg === 'string'
                      ? seg
                      : (seg as any).audioData || (seg as any).audio_segment,
                  is_final: nowFinalized && i === segments.length - 1,
                });
              }
              syncedAudioStateRef.current.set(audioKey, {
                count: segments.length,
                finalized: nowFinalized,
              });
            } else if (nowFinalized && !prev.finalized && segments.length > 0) {
              // Segments unchanged but streaming just completed — send final marker
              const lastSeg = segments[segments.length - 1];
              queueActions.upsertAudio(bid, position, {
                audio_segment:
                  typeof lastSeg === 'string'
                    ? lastSeg
                    : (lastSeg as any).audioData ||
                      (lastSeg as any).audio_segment,
                is_final: true,
              });
              syncedAudioStateRef.current.set(audioKey, {
                count: segments.length,
                finalized: true,
              });
            }
          } else if (isStreaming && prevState === undefined) {
            // Streaming but no segments yet; upsert a placeholder (only once)
            queueActions.upsertAudio(bid, position, {
              is_final: false,
            });
            syncedAudioStateRef.current.set(audioKey, {
              count: 0,
              finalized: false,
            });
          }
        }
      });

      // Check for isSilentVisual flips: items that were previously silent
      // but now have audio
      const prevList = lastSyncedListRef.current;
      if (prevList.length > 0) {
        list.forEach(item => {
          const bid = item.generated_block_bid;
          if (!bid || bid === 'loading') {
            return;
          }
          if (item.type !== ChatContentItemType.CONTENT) {
            return;
          }
          const position = item.audioPosition ?? 0;
          const prevItem = prevList.find(
            prev =>
              prev.generated_block_bid === bid &&
              (prev.audioPosition ?? 0) === position,
          );
          if (prevItem?.isSilentVisual && !item.isSilentVisual) {
            // Was silent, now has audio — update queue expectation
            queueActions.updateVisualExpectation(bid, position, true);
            // Also upsert audio data if available
            if (hasPlayableAudioForItem(item)) {
              const track = item.audioTracksByPosition?.[position];
              const persisted = (item.audios || [])
                .filter(audio => Number(audio.position ?? 0) === position)
                .pop();
              const legacyForZero = position === 0;
              const audioUrl =
                track?.audioUrl ||
                persisted?.audio_url ||
                (legacyForZero ? item.audioUrl : undefined);
              if (audioUrl) {
                const flipKey = `${bid}:${position}`;
                if (syncedAudioStateRef.current.get(flipKey) !== 'url') {
                  queueActions.upsertAudio(bid, position, {
                    audio_url: audioUrl,
                    is_final: true,
                  });
                  syncedAudioStateRef.current.set(flipKey, 'url');
                }
              }
            }
          }
        });
      }

      lastSyncedListRef.current = list;
    },
    [hasPlayableAudioForItem, queueActions],
  );

  // ---------------------------------------------------------------------------
  // Effects — sync list to queue, bootstrap, and cleanup
  // ---------------------------------------------------------------------------

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
      if (state && !state.isPlaying && !state.isLoading && !state.isPaused) {
        console.log('[Queue→Seq] Explicit play fallback triggered');
        audioPlayerRef.current?.play();
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [audioSequenceToken, activeAudioBid]);

  // Reset when list empties
  useEffect(() => {
    if (audioAndInteractionList.length) {
      return;
    }
    audioPlayerRef.current?.pause({
      traceId: 'sequence-reset',
      keepAutoPlay: true,
    });
    queueActions.reset();
    syncedAudioStateRef.current.clear();
    endSequence();
  }, [audioAndInteractionList.length, endSequence, queueActions]);

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

    const currentPage =
      deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
    const startIndex = resolveSequenceStartIndex(currentPage);
    if (startIndex < 0) {
      return;
    }

    shouldStartSequenceRef.current = false;
    // Sync list to queue first to ensure all items are enqueued
    syncListToQueue(audioAndInteractionList);
    queueActions.startFromIndex(startIndex);
  }, [
    audioAndInteractionList,
    currentPptPageRef,
    deckRef,
    queueActions,
    resolveSequenceStartIndex,
    shouldStartSequenceRef,
    syncListToQueue,
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
    return (
      contentByBid.get(activeAudioBlockBid) ??
      audioContentByBid.get(activeAudioBlockBid)
    );
  }, [activeAudioBlockBid, audioContentByBid, contentByBid]);

  const activeAudioDurationMs = useMemo(() => {
    if (!activeContentItem) {
      return undefined;
    }

    const track =
      activeContentItem.audioTracksByPosition?.[activeAudioPosition];
    const persisted = (activeContentItem.audios || [])
      .filter(audio => Number(audio.position ?? 0) === activeAudioPosition)
      .pop();
    const fallbackDuration =
      activeAudioPosition === 0 ? activeContentItem.audioDurationMs : undefined;

    const explicitDuration =
      track?.audioDurationMs ?? persisted?.duration_ms ?? fallbackDuration;
    if (Number.isFinite(explicitDuration) && (explicitDuration || 0) > 0) {
      return explicitDuration;
    }

    const segments =
      track?.audioSegments ??
      (activeAudioPosition === 0 ? activeContentItem.audioSegments : undefined);
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
  }, [activeAudioPosition, activeContentItem]);

  const audioWatchdogTimeoutMs = useMemo(
    () => resolveListenAudioWatchdogMs(activeAudioDurationMs),
    [activeAudioDurationMs],
  );

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
      queueActions.advance();
    },
    [queueActions],
  );

  const handleAudioError = useCallback(
    (token?: number) => {
      if (
        typeof token === 'number' &&
        token !== audioSequenceTokenRef.current
      ) {
        return;
      }
      isSequencePausedRef.current = true;
      queueActions.pause();
      setIsAudioPlaying(false);
    },
    [queueActions, setIsAudioPlaying],
  );

  const handlePlay = useCallback(() => {
    if (previewMode) {
      return;
    }
    isSequencePausedRef.current = false;

    if (sequenceInteraction) {
      // Keep sequence blocked until learner explicitly submits interaction.
      return;
    }

    if (!activeAudioBid && audioAndInteractionList.length) {
      // No active audio — start/resume the queue
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
      const startIndex = resolveSequenceStartIndex(currentPage);
      if (startIndex >= 0) {
        syncListToQueue(audioAndInteractionList);
        queueActions.startFromIndex(startIndex);
      } else {
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
    previewMode,
    queueActions,
    resolveSequenceStartIndex,
    sequenceInteraction,
    syncListToQueue,
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
      syncListToQueue(audioAndInteractionList);
      queueActions.startFromIndex(index);
    },
    [audioAndInteractionList, queueActions, syncListToQueue],
  );

  const startSequenceFromPage = useCallback(
    (page: number) => {
      const startIndex = resolveSequenceStartIndex(page);
      if (startIndex < 0) {
        return;
      }
      startSequenceFromIndex(startIndex);
    },
    [resolveSequenceStartIndex, startSequenceFromIndex],
  );

  // ---------------------------------------------------------------------------
  // Audio watchdog — same as original
  // ---------------------------------------------------------------------------
  useEffect(() => {
    hasObservedPlaybackRef.current = false;
    setIsAudioPlaying(false);
  }, [audioSequenceToken, setIsAudioPlaying]);

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
      console.warn(
        '[Queue→Seq] Audio watchdog: no playback observed, auto-advancing',
      );
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
  // Return — identical interface to original
  // ---------------------------------------------------------------------------
  return {
    audioPlayerRef,
    activeContentItem,
    activeAudioBlockBid,
    activeAudioPosition,
    activeSequencePage,
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
  };
};
