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
  type ListenSequenceMode =
    | 'idle'
    | 'waiting_audio'
    | 'playing'
    | 'interaction_blocked'
    | 'paused';

  type ListenSequenceEvent =
    | { type: 'START_FROM_INDEX'; index: number }
    | { type: 'START_FROM_PAGE'; page: number }
    | {
        type: 'RESOLVE_INDEX';
        index: number;
        retryCount?: number;
        reason: string;
      }
    | { type: 'AUDIO_ENDED' }
    | { type: 'AUDIO_ERROR' }
    | {
        type: 'INTERACTION_OPENED';
        item: AudioInteractionItem;
        nextIndex: number | null;
      }
    | { type: 'INTERACTION_RESOLVED'; interactionBid?: string }
    | { type: 'PLAY' }
    | { type: 'PAUSE'; traceId?: string }
    | { type: 'RESET' }
    | { type: 'LIST_UPDATED' };

  const audioPlayerRef = useRef<AudioPlayerHandle | null>(null);
  const audioSequenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const audioSequenceListRef = useRef<AudioInteractionItem[]>([]);
  const sequenceModeRef = useRef<ListenSequenceMode>('idle');
  const sequenceIndexRef = useRef(-1);
  const sequenceUnitIdRef = useRef<string | null>(null);
  const resumeAfterUnitIdRef = useRef<string | null>(null);
  const isSequencePausedRef = useRef(false);
  // When a silent-visual at the tail of the list finishes its display but
  // the list hasn't grown yet (content still streaming), this ref stores the
  // next index we want to reach.  The LIST_UPDATED handler checks this and
  // auto-resumes once the list grows to include that index.
  const waitingForListGrowthRef = useRef<{
    nextIdx: number;
    since: number;
  } | null>(null);
  const interactionNextIndexRef = useRef<number | null>(null);
  const [activeAudioBid, setActiveAudioBid] = useState<string | null>(null);
  const [activeAudioPosition, setActiveAudioPosition] = useState(0);
  const [activeSequencePage, setActiveSequencePage] = useState(-1);
  const [sequenceInteraction, setSequenceInteraction] =
    useState<AudioInteractionItem | null>(null);
  const [isAudioSequenceActive, setIsAudioSequenceActive] = useState(false);
  const [audioSequenceToken, setAudioSequenceToken] = useState(0);
  const audioSequenceTokenRef = useRef(0);
  const hasObservedPlaybackRef = useRef(false);
  const dispatchSequenceEventRef = useRef<(event: ListenSequenceEvent) => void>(
    () => undefined,
  );

  const setSequenceMode = useCallback((mode: ListenSequenceMode) => {
    sequenceModeRef.current = mode;
    setIsAudioSequenceActive(mode !== 'idle');
  }, []);

  const clearAudioSequenceTimer = useCallback(() => {
    if (audioSequenceTimerRef.current) {
      clearTimeout(audioSequenceTimerRef.current);
      audioSequenceTimerRef.current = null;
    }
  }, []);

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

  const getItemUnitId = useCallback(
    (item: AudioInteractionItem | undefined, index: number) =>
      buildListenUnitId({
        type: item?.type || 'unknown',
        generatedBlockBid: item?.generated_block_bid,
        position: item?.audioPosition ?? 0,
        slideId: item?.audioSlideId,
        fallbackIndex: index,
        resolveContentBid,
      }),
    [resolveContentBid],
  );

  const resolveCurrentSequenceIndex = useCallback(
    (list: AudioInteractionItem[]) => {
      const unitId = sequenceUnitIdRef.current;
      if (!unitId) {
        return sequenceIndexRef.current;
      }
      const nextIndex = list.findIndex((item, index) => {
        return getItemUnitId(item, index) === unitId;
      });
      if (nextIndex >= 0) {
        sequenceIndexRef.current = nextIndex;
        return nextIndex;
      }

      // Fallback recovery: when unit id no longer matches after stream patches,
      // attempt to recover by active audio identity.
      if (activeAudioBid) {
        const resolvedActiveBid =
          resolveContentBid(activeAudioBid) || activeAudioBid;
        const recoveredIndex = list.findIndex(
          item =>
            item.type === ChatContentItemType.CONTENT &&
            (resolveContentBid(item.generated_block_bid) ||
              item.generated_block_bid) === resolvedActiveBid &&
            (item.audioPosition ?? 0) === activeAudioPosition,
        );
        if (recoveredIndex >= 0) {
          sequenceIndexRef.current = recoveredIndex;
          sequenceUnitIdRef.current = getItemUnitId(
            list[recoveredIndex],
            recoveredIndex,
          );
          return recoveredIndex;
        }
      }
      return -1;
    },
    [activeAudioBid, activeAudioPosition, getItemUnitId, resolveContentBid],
  );

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
      } catch (e) {}

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

      const currentIndex = deck.getIndices?.().h ?? 0;

      // Always call deck.slide() to ensure Reveal.js re-renders the slide content.
      // This is critical when multiple audio positions share the same page number
      // (e.g., during streaming when not all slides have arrived yet).
      // Calling slide() even when already on the target page forces Reveal.js to
      // sync DOM and re-render, ensuring the latest content is displayed.
      deck.slide(page);
      return true;
    },
    [deckRef],
  );

  const resolveSequenceStartIndex = useCallback(
    (page: number) => {
      const list = audioSequenceListRef.current;
      if (!list.length) {
        return -1;
      }

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
    [activeAudioBid, activeBlockBidRef, deckRef, resolveContentBid],
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
      clearAudioSequenceTimer();
      sequenceIndexRef.current = -1;
      sequenceUnitIdRef.current = null;
      resumeAfterUnitIdRef.current = null;
      interactionNextIndexRef.current = null;
      waitingForListGrowthRef.current = null;
      setSequenceInteraction(null);
      setActiveAudioBid(null);
      setActiveAudioPosition(0);
      setActiveSequencePage(-1);
      setSequenceMode('idle');
      if (options?.tryAdvanceToNextBlock) {
        tryAdvanceToNextBlock();
      }
    },
    [clearAudioSequenceTimer, setSequenceMode, tryAdvanceToNextBlock],
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

  const resolveIndex = useCallback(
    (index: number, retryCount = 0, reason = 'resolve-index') => {
      if (isSequencePausedRef.current && !reason.startsWith('start')) {
        return;
      }

      clearAudioSequenceTimer();
      const list = audioSequenceListRef.current;
      const nextItem = list[index];

      if (!nextItem) {
        endSequence();
        return;
      }

      sequenceIndexRef.current = index;
      sequenceUnitIdRef.current = getItemUnitId(nextItem, index);
      setIsAudioSequenceActive(true);
      setActiveSequencePage(nextItem.page);

      // Silent visual items have slide content but no audio.  Show the slide
      // for a brief viewing period and then auto-advance to the next item.
      if (nextItem.isSilentVisual) {
        const pageReady = syncToSequencePage(nextItem.page);
        if (!pageReady) {
          // Slide not rendered yet – retry shortly.
          audioSequenceTimerRef.current = setTimeout(() => {
            dispatchSequenceEventRef.current({
              type: 'RESOLVE_INDEX',
              index,
              retryCount: retryCount + 1,
              reason: 'silent-visual-wait-slide',
            });
          }, 120);
          return;
        }
        setSequenceInteraction(null);
        setActiveAudioBid(null);
        setSequenceMode('playing');
        // Auto-advance after a viewing period (5 s per visual slide).
        const viewMs = 5000;
        audioSequenceTimerRef.current = setTimeout(() => {
          const nextIdx = index + 1;
          const latestList = audioSequenceListRef.current;
          if (nextIdx < latestList.length) {
            resolveIndex(nextIdx, 0, 'silent-visual-auto-advance');
            return;
          }
          // The block's content may still be streaming, so the list may
          // not yet include subsequent visual pages.  Poll briefly for
          // the list to grow before ending the sequence.
          let pollCount = 0;
          const pollForNextItem = () => {
            const refreshed = audioSequenceListRef.current;
            if (nextIdx < refreshed.length) {
              resolveIndex(nextIdx, 0, 'silent-visual-auto-advance');
              return;
            }
            pollCount++;
            if (pollCount >= 10) {
              // Content may still be streaming.  Instead of ending the
              // sequence, hand off to the LIST_UPDATED handler which will
              // resume once the list grows to include nextIdx.
              waitingForListGrowthRef.current = {
                nextIdx,
                since: Date.now(),
              };
              setSequenceMode('waiting_audio');
              return;
            }
            audioSequenceTimerRef.current = setTimeout(pollForNextItem, 300);
          };
          pollForNextItem();
        }, viewMs);
        return;
      }

      if (
        nextItem.type === ChatContentItemType.CONTENT &&
        !hasPlayableAudioForItem(nextItem)
      ) {
        syncToSequencePage(nextItem.page);
        setSequenceInteraction(null);
        setActiveAudioBid(null);
        setActiveAudioPosition(nextItem.audioPosition ?? 0);
        setSequenceMode('waiting_audio');
        const waitMs = retryCount < 80 ? 120 : 500;
        audioSequenceTimerRef.current = setTimeout(() => {
          dispatchSequenceEventRef.current({
            type: 'RESOLVE_INDEX',
            index,
            retryCount: retryCount + 1,
            reason: 'wait-audio',
          });
        }, waitMs);
        return;
      }

      const pageReady = syncToSequencePage(nextItem.page);

      if (!pageReady) {
        setSequenceMode('waiting_audio');
        audioSequenceTimerRef.current = setTimeout(() => {
          dispatchSequenceEventRef.current({
            type: 'RESOLVE_INDEX',
            index,
            retryCount: retryCount + 1,
            reason: 'wait-slide',
          });
        }, 120);
        return;
      }

      if (nextItem.type === ChatContentItemType.INTERACTION) {
        dispatchSequenceEventRef.current({
          type: 'INTERACTION_OPENED',
          item: nextItem,
          nextIndex: index >= list.length - 1 ? null : index + 1,
        });
        return;
      }

      interactionNextIndexRef.current = null;
      setSequenceInteraction(null);
      setActiveAudioBid(nextItem.generated_block_bid);
      setActiveAudioPosition(nextItem.audioPosition ?? 0);
      setAudioSequenceToken(prev => prev + 1);
      setSequenceMode('playing');
    },
    [
      clearAudioSequenceTimer,
      endSequence,
      getItemUnitId,
      hasPlayableAudioForItem,
      setSequenceMode,
      syncToSequencePage,
    ],
  );

  const dispatchSequenceEvent = useCallback(
    (event: ListenSequenceEvent) => {
      if (event.type === 'RESET') {
        isSequencePausedRef.current = false;
        clearAudioSequenceTimer();
        audioPlayerRef.current?.pause({
          traceId: 'sequence-reset',
          keepAutoPlay: true,
        });
        endSequence();
        return;
      }

      if (event.type === 'START_FROM_INDEX') {
        const listLength = audioSequenceListRef.current.length;
        if (!listLength) {
          return;
        }
        const maxIndex = Math.max(listLength - 1, 0);
        const nextIndex = Math.min(Math.max(event.index, 0), maxIndex);
        isSequencePausedRef.current = false;
        clearAudioSequenceTimer();
        audioPlayerRef.current?.pause({
          traceId: 'sequence-start',
          keepAutoPlay: true,
        });
        endSequence();
        resolveIndex(nextIndex, 0, 'start-from-index');
        return;
      }

      if (event.type === 'START_FROM_PAGE') {
        const startIndex = resolveSequenceStartIndex(event.page);
        if (startIndex < 0) {
          return;
        }
        dispatchSequenceEventRef.current({
          type: 'START_FROM_INDEX',
          index: startIndex,
        });
        return;
      }

      if (event.type === 'RESOLVE_INDEX') {
        resolveIndex(event.index, event.retryCount ?? 0, event.reason);
        return;
      }

      if (event.type === 'AUDIO_ERROR') {
        clearAudioSequenceTimer();
        isSequencePausedRef.current = true;
        setSequenceMode('paused');
        setIsAudioPlaying(false);
        return;
      }

      if (event.type === 'INTERACTION_OPENED') {
        setSequenceMode('interaction_blocked');
        setSequenceInteraction(event.item);
        setActiveAudioBid(null);
        setActiveSequencePage(event.item.page);
        interactionNextIndexRef.current = event.nextIndex;
        return;
      }

      if (event.type === 'INTERACTION_RESOLVED') {
        if (previewMode) {
          return;
        }
        if (
          event.interactionBid &&
          sequenceInteraction?.generated_block_bid &&
          sequenceInteraction.generated_block_bid !== event.interactionBid
        ) {
          return;
        }
        clearAudioSequenceTimer();
        isSequencePausedRef.current = false;
        setSequenceInteraction(null);
        // Do not rely on the stored numeric index here: the list can shift while
        // the interaction is open (streaming patches, history merge, etc.).
        // Instead, locate the current interaction unit id in the latest list and
        // advance relative to it.
        interactionNextIndexRef.current = null;

        const list = audioSequenceListRef.current;
        if (!list.length) {
          endSequence({ tryAdvanceToNextBlock: true });
          return;
        }

        const currentIndex = resolveCurrentSequenceIndex(list);
        if (currentIndex < 0) {
          endSequence();
          return;
        }

        const computedNextIndex = currentIndex + 1;
        if (computedNextIndex >= list.length) {
          // When the interaction is the last known unit, the next content might
          // still be streaming. Keep the sequence alive and resume once the list
          // grows to include the next unit.
          resumeAfterUnitIdRef.current = sequenceUnitIdRef.current;
          setActiveAudioBid(null);
          setActiveAudioPosition(0);
          setSequenceMode('waiting_audio');
          return;
        }

        resumeAfterUnitIdRef.current = null;
        resolveIndex(computedNextIndex, 0, 'interaction-resolved');
        return;
      }

      if (event.type === 'AUDIO_ENDED') {
        if (isSequencePausedRef.current) {
          return;
        }
        const list = audioSequenceListRef.current;
        if (!list.length) {
          endSequence({ tryAdvanceToNextBlock: true });
          return;
        }

        const currentIndex = resolveCurrentSequenceIndex(list);
        if (currentIndex < 0) {
          endSequence();
          return;
        }

        const nextIndex = currentIndex + 1;
        const currentItem = list[currentIndex];
        const nextItem = list[nextIndex];
        const currentPage = currentItem?.page ?? currentPptPageRef.current;
        const deckCurrentPage =
          deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
        const nextPage = nextItem?.page ?? null;
        const currentBid =
          currentItem?.type === ChatContentItemType.CONTENT
            ? resolveContentBid(currentItem.generated_block_bid)
            : null;
        const nextBid =
          nextItem?.type === ChatContentItemType.CONTENT
            ? resolveContentBid(nextItem.generated_block_bid)
            : null;

        if (
          typeof currentPage === 'number' &&
          typeof nextPage === 'number' &&
          nextPage > currentPage + 1
        ) {
          const targetPage = nextPage;
          const moved = syncToSequencePage(targetPage);
          if (!moved) {
            // Page sync failed (e.g. page index exceeds slide count).
            // Fall through to resolveIndex instead of retrying forever.
          }
          resolveIndex(nextIndex, 0, 'audio-ended-skip-ahead');
          return;
        }

        if (currentBid && nextBid && currentBid === nextBid) {
          resolveIndex(nextIndex, 0, 'audio-ended-same-block');
          return;
        }

        if (!nextItem) {
          const deck = deckRef.current;
          const totalSlides =
            deck && typeof deck.getSlides === 'function'
              ? deck.getSlides().length
              : deck && typeof deck.getTotalSlides === 'function'
                ? deck.getTotalSlides()
                : 0;
          if (totalSlides > deckCurrentPage + 1) {
            const targetPage = deckCurrentPage + 1;
            const moved = syncToSequencePage(targetPage);
            if (!moved) {
              clearAudioSequenceTimer();
              audioSequenceTimerRef.current = setTimeout(() => {
                dispatchSequenceEventRef.current({ type: 'AUDIO_ENDED' });
              }, 120);
              return;
            }
            endSequence();
            return;
          }
        }

        if (nextIndex >= list.length) {
          // Content blocks may still be streaming via SSE, so the list can
          // grow shortly after the current tail item finishes.  Wait briefly
          // for the next item to appear before ending the sequence.
          waitingForListGrowthRef.current = {
            nextIdx: nextIndex,
            since: Date.now(),
          };
          setSequenceMode('waiting_audio');
          // Fallback: if no LIST_UPDATED events arrive within 10 s, end.
          clearAudioSequenceTimer();
          audioSequenceTimerRef.current = setTimeout(() => {
            if (waitingForListGrowthRef.current) {
              waitingForListGrowthRef.current = null;
              endSequence({ tryAdvanceToNextBlock: true });
            }
          }, 10_000);
          return;
        }

        resolveIndex(nextIndex, 0, 'audio-ended-next');
        return;
      }

      if (event.type === 'PLAY') {
        if (previewMode) {
          return;
        }
        isSequencePausedRef.current = false;
        if (sequenceInteraction) {
          // Keep sequence blocked until learner explicitly submits interaction.
          setSequenceMode('interaction_blocked');
          return;
        }
        if (!activeAudioBid && audioSequenceListRef.current.length) {
          const list = audioSequenceListRef.current;
          const resumeUnitId = resumeAfterUnitIdRef.current;
          if (resumeUnitId) {
            const resumeIndex = list.findIndex((item, index) => {
              return getItemUnitId(item, index) === resumeUnitId;
            });
            if (resumeIndex >= 0) {
              const targetIndex = resumeIndex + 1;
              if (targetIndex < list.length) {
                resumeAfterUnitIdRef.current = null;
                resolveIndex(targetIndex, 0, 'play-resume-after-interaction');
                return;
              }
              // Still waiting for the next unit; do not restart from current page.
              setSequenceMode('waiting_audio');
              return;
            }
            // Anchor unit disappeared; fall back to the last known numeric index,
            // which typically points at the next unit after removals.
            const fallbackIndex = Math.max(
              0,
              Math.min(sequenceIndexRef.current, list.length - 1),
            );
            if (list[fallbackIndex]) {
              resumeAfterUnitIdRef.current = null;
              resolveIndex(
                fallbackIndex,
                0,
                'play-resume-after-interaction-missing-anchor',
              );
              return;
            }
            resumeAfterUnitIdRef.current = null;
          }
          const currentPage =
            deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
          dispatchSequenceEventRef.current({
            type: 'START_FROM_PAGE',
            page: currentPage,
          });
          return;
        }
        audioPlayerRef.current?.play();
        return;
      }

      if (event.type === 'PAUSE') {
        if (previewMode) {
          return;
        }
        isSequencePausedRef.current = true;
        clearAudioSequenceTimer();
        setSequenceMode('paused');
        audioPlayerRef.current?.pause({ traceId: event.traceId });
        return;
      }

      if (event.type === 'LIST_UPDATED') {
        if (previewMode) {
          return;
        }
        if (isSequencePausedRef.current) {
          return;
        }

        const list = audioSequenceListRef.current;
        if (!list.length) {
          return;
        }

        const resumeUnitId = resumeAfterUnitIdRef.current;
        if (resumeUnitId) {
          const resumeIndex = list.findIndex((item, index) => {
            return getItemUnitId(item, index) === resumeUnitId;
          });
          if (resumeIndex >= 0) {
            const targetIndex = resumeIndex + 1;
            if (targetIndex < list.length) {
              resumeAfterUnitIdRef.current = null;
              resolveIndex(targetIndex, 0, 'resume-after-interaction');
              return;
            }
            setSequenceMode('waiting_audio');
            return;
          }
          const fallbackIndex = Math.max(
            0,
            Math.min(sequenceIndexRef.current, list.length - 1),
          );
          if (list[fallbackIndex]) {
            resumeAfterUnitIdRef.current = null;
            resolveIndex(
              fallbackIndex,
              0,
              'resume-after-interaction-missing-anchor',
            );
            return;
          }
          resumeAfterUnitIdRef.current = null;
        }
        const currentIndex = resolveCurrentSequenceIndex(list);

        if (
          sequenceModeRef.current !== 'idle' &&
          sequenceUnitIdRef.current &&
          currentIndex < 0
        ) {
          const fallbackIndex = Math.max(
            0,
            Math.min(sequenceIndexRef.current, list.length - 1),
          );
          if (list[fallbackIndex]) {
            resolveIndex(fallbackIndex, 0, 'recover-missing-unit');
            return;
          }
          endSequence();
          return;
        }

        if (
          sequenceModeRef.current === 'waiting_audio' &&
          currentIndex >= 0 &&
          list[currentIndex] &&
          hasPlayableAudioForItem(list[currentIndex])
        ) {
          resolveIndex(currentIndex, 0, 'waiting-audio-ready');
          return;
        }

        // After a silent visual at the tail of the list finished its
        // display, we enter waiting_audio with waitingForListGrowthRef
        // set.  Check if the list has grown to include the target index.
        if (
          sequenceModeRef.current === 'waiting_audio' &&
          waitingForListGrowthRef.current
        ) {
          const { nextIdx, since } = waitingForListGrowthRef.current;
          if (nextIdx < list.length) {
            waitingForListGrowthRef.current = null;
            resolveIndex(nextIdx, 0, 'list-growth-resume');
            return;
          }
          // Timeout after 30 seconds of waiting.
          if (Date.now() - since > 30_000) {
            waitingForListGrowthRef.current = null;
            endSequence({ tryAdvanceToNextBlock: true });
            return;
          }
        }

        // While showing a silent visual (mode=playing, no active audio),
        // the block may receive audio data via a later SSE chunk.  When
        // that happens the list rebuilds and the entry at the current
        // index is no longer isSilentVisual.  Re-resolve so the sequence
        // transitions from the 5-second silent display to proper audio
        // playback.
        if (
          sequenceModeRef.current === 'playing' &&
          !activeAudioBid &&
          currentIndex >= 0 &&
          list[currentIndex] &&
          !list[currentIndex].isSilentVisual
        ) {
          resolveIndex(currentIndex, 0, 'silent-visual-upgraded');
          return;
        }

        if (
          sequenceModeRef.current === 'interaction_blocked' &&
          sequenceInteraction
        ) {
          // Interaction explicitly gates progression. New list updates must not
          // auto-resolve or auto-advance until submit/skip/autocontinue event.
          return;
        }

        // Intentionally do not auto-start from idle on arbitrary list updates.
        // Startup should be driven by explicit start/play events or the
        // shouldStartSequenceRef bootstrap flow to avoid replay loops.
      }
    },
    [
      activeAudioBid,
      clearAudioSequenceTimer,
      currentPptPageRef,
      deckRef,
      endSequence,
      getItemUnitId,
      hasPlayableAudioForItem,
      previewMode,
      resolveContentBid,
      resolveCurrentSequenceIndex,
      resolveIndex,
      resolveSequenceStartIndex,
      sequenceInteraction,
      setIsAudioPlaying,
      setSequenceMode,
      syncToSequencePage,
    ],
  );

  dispatchSequenceEventRef.current = dispatchSequenceEvent;

  useEffect(() => {
    audioSequenceTokenRef.current = audioSequenceToken;
  }, [audioSequenceToken]);

  useEffect(() => {
    audioSequenceListRef.current = audioAndInteractionList;
    dispatchSequenceEventRef.current({ type: 'LIST_UPDATED' });
  }, [audioAndInteractionList]);

  useEffect(() => {
    return () => {
      clearAudioSequenceTimer();
    };
  }, [clearAudioSequenceTimer]);

  useEffect(() => {
    if (audioAndInteractionList.length) {
      return;
    }
    dispatchSequenceEventRef.current({ type: 'RESET' });
  }, [audioAndInteractionList.length]);

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
    dispatchSequenceEventRef.current({
      type: 'START_FROM_INDEX',
      index: startIndex,
    });
  }, [
    audioAndInteractionList,
    currentPptPageRef,
    deckRef,
    resolveSequenceStartIndex,
    shouldStartSequenceRef,
  ]);

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

  const handleAudioEnded = useCallback((token?: number) => {
    if (typeof token === 'number' && token !== audioSequenceTokenRef.current) {
      return;
    }
    dispatchSequenceEventRef.current({ type: 'AUDIO_ENDED' });
  }, []);

  const handleAudioError = useCallback((token?: number) => {
    if (typeof token === 'number' && token !== audioSequenceTokenRef.current) {
      return;
    }
    dispatchSequenceEventRef.current({ type: 'AUDIO_ERROR' });
  }, []);

  const handlePlay = useCallback(() => {
    dispatchSequenceEventRef.current({ type: 'PLAY' });
  }, []);

  const handlePause = useCallback((traceId?: string) => {
    dispatchSequenceEventRef.current({ type: 'PAUSE', traceId });
  }, []);

  const continueAfterInteraction = useCallback(() => {
    dispatchSequenceEventRef.current({
      type: 'INTERACTION_RESOLVED',
      interactionBid: sequenceInteraction?.generated_block_bid,
    });
  }, [sequenceInteraction?.generated_block_bid]);

  const startSequenceFromIndex = useCallback((index: number) => {
    dispatchSequenceEventRef.current({ type: 'START_FROM_INDEX', index });
  }, []);

  const startSequenceFromPage = useCallback((page: number) => {
    dispatchSequenceEventRef.current({ type: 'START_FROM_PAGE', page });
  }, []);

  useEffect(() => {
    hasObservedPlaybackRef.current = false;
    setIsAudioPlaying(false);
  }, [audioSequenceToken, setIsAudioPlaying]);

  useEffect(() => {
    if (isAudioPlaying || isAudioPlayerBusy()) {
      hasObservedPlaybackRef.current = true;
    }
  }, [isAudioPlayerBusy, isAudioPlaying]);

  const handleAudioEndedRef = useRef(handleAudioEnded);
  handleAudioEndedRef.current = handleAudioEnded;
  const handleAudioErrorRef = useRef(handleAudioError);
  handleAudioErrorRef.current = handleAudioError;

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
      // Do not force-advance on watchdog timeout. If playback never starts,
      // move to paused/error state and keep current unit/page for manual recovery.
      handleAudioErrorRef.current();
    }, audioWatchdogTimeoutMs);
    return () => clearTimeout(timer);
  }, [
    isAudioSequenceActive,
    activeAudioBid,
    isAudioPlaying,
    isAudioPlayerBusy,
    audioWatchdogTimeoutMs,
  ]);

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
