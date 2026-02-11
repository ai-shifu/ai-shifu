import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Reveal, { Options } from 'reveal.js';
import {
  splitContentSegments,
  type RenderSegment,
} from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import type { AudioPlayerHandle } from '@/components/audio/AudioPlayer';

type HtmlVisualKind = 'video' | 'table' | 'iframe';
type HtmlSandboxRootTag =
  | 'iframe'
  | 'div'
  | 'section'
  | 'article'
  | 'main'
  | 'template';

const isFixedMarkerText = (raw: string) => {
  const trimmed = (raw || '').trim();
  return Boolean(trimmed && /^!?=+$/.test(trimmed));
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

const escapeHtml = (raw: string) =>
  raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const parseMarkdownTableRow = (line: string): string[] => {
  const trimmed = line.trim();
  const withoutLeading = trimmed.startsWith('|') ? trimmed.slice(1) : trimmed;
  const withoutEdges = withoutLeading.endsWith('|')
    ? withoutLeading.slice(0, -1)
    : withoutLeading;
  return withoutEdges.split('|').map(cell => cell.trim());
};

const parseMarkdownTableAlign = (
  line: string,
): Array<'left' | 'center' | 'right' | ''> => {
  const cells = parseMarkdownTableRow(line);
  return cells.map(cell => {
    const token = cell.replace(/\s+/g, '');
    if (!/^:?-{3,}:?$/.test(token)) {
      return '';
    }
    if (token.startsWith(':') && token.endsWith(':')) {
      return 'center';
    }
    if (token.endsWith(':')) {
      return 'right';
    }
    if (token.startsWith(':')) {
      return 'left';
    }
    return '';
  });
};

const isMarkdownTableSeparatorLine = (line: string): boolean => {
  const cells = parseMarkdownTableRow(line);
  if (cells.length < 2) {
    return false;
  }
  return cells.every(cell => {
    const token = cell.replace(/\s+/g, '');
    return /^:?-{3,}:?$/.test(token);
  });
};

const findFirstMarkdownTableBlock = (
  raw: string,
): { start: number; end: number } | null => {
  if (!raw) {
    return null;
  }

  const lines = raw.split('\n');
  if (lines.length < 2) {
    return null;
  }

  const lineStarts: number[] = [];
  let cursor = 0;
  lines.forEach(line => {
    lineStarts.push(cursor);
    cursor += line.length + 1;
  });

  for (let index = 0; index < lines.length - 1; index += 1) {
    const headerLine = lines[index];
    const separatorLine = lines[index + 1];
    if (!headerLine.includes('|') || !separatorLine.includes('|')) {
      continue;
    }
    const headerCells = parseMarkdownTableRow(headerLine);
    if (headerCells.length < 2) {
      continue;
    }
    if (!isMarkdownTableSeparatorLine(separatorLine)) {
      continue;
    }

    let endLine = index + 2;
    while (endLine < lines.length) {
      const line = lines[endLine];
      if (!line.trim()) {
        break;
      }
      if (!line.includes('|')) {
        break;
      }
      endLine += 1;
    }

    const start = lineStarts[index];
    const lastLineIndex = Math.max(endLine - 1, index + 1);
    let end = lineStarts[lastLineIndex] + lines[lastLineIndex].length;
    if (end < raw.length && raw[end] === '\n') {
      end += 1;
    }
    return { start, end };
  }

  return null;
};

const markdownTableToSandboxHtml = (raw: string): string | null => {
  const lines = (raw || '')
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean);
  if (lines.length < 2) {
    return null;
  }

  const headerLine = lines[0];
  const separatorLine = lines[1];
  if (!headerLine.includes('|') || !separatorLine.includes('|')) {
    return null;
  }

  const headers = parseMarkdownTableRow(headerLine);
  const alignments = parseMarkdownTableAlign(separatorLine);
  if (!headers.length || !alignments.length) {
    return null;
  }

  const bodyLines = lines.slice(2).filter(line => line.includes('|'));
  const headerHtml = headers
    .map((header, index) => {
      const align = alignments[index] || '';
      const alignAttr = align ? ` style="text-align:${align};"` : '';
      return `<th${alignAttr}>${escapeHtml(header)}</th>`;
    })
    .join('');

  const bodyHtml = bodyLines
    .map(line => {
      const cells = parseMarkdownTableRow(line);
      if (!cells.length) {
        return '';
      }
      const cellsHtml = cells
        .map((cell, index) => {
          const align = alignments[index] || '';
          const alignAttr = align ? ` style="text-align:${align};"` : '';
          return `<td${alignAttr}>${escapeHtml(cell)}</td>`;
        })
        .join('');
      return `<tr>${cellsHtml}</tr>`;
    })
    .filter(Boolean)
    .join('');

  return `<div><table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`;
};

const findFirstHtmlVisualBlock = (
  raw: string,
): { kind: HtmlVisualKind; start: number; end: number } | null => {
  if (!raw) {
    return null;
  }

  const lower = raw.toLowerCase();
  const videoStart = lower.indexOf('<video');
  const tableStart = lower.indexOf('<table');
  const iframeStart = lower.indexOf('<iframe');

  let kind: HtmlVisualKind | null = null;
  let start = -1;
  const candidates: Array<{ kind: HtmlVisualKind; start: number }> = [];
  if (videoStart !== -1) {
    candidates.push({ kind: 'video', start: videoStart });
  }
  if (tableStart !== -1) {
    candidates.push({ kind: 'table', start: tableStart });
  }
  if (iframeStart !== -1) {
    candidates.push({ kind: 'iframe', start: iframeStart });
  }
  candidates.sort((a, b) => a.start - b.start);
  const first = candidates[0];
  if (first) {
    kind = first.kind;
    start = first.start;
  }

  if (!kind || start < 0) {
    return null;
  }

  const closeTagName =
    kind === 'video' ? 'video' : kind === 'table' ? 'table' : 'iframe';
  const closeIdx = lower.indexOf(`</${closeTagName}`, start);
  if (closeIdx !== -1) {
    const closeEnd = raw.indexOf('>', closeIdx);
    if (closeEnd !== -1) {
      return { kind, start, end: closeEnd + 1 };
    }
  }

  // Best-effort support for self-closing <video ... /> / <iframe ... /> tags.
  if (kind === 'video' || kind === 'iframe') {
    const openEnd = raw.indexOf('>', start);
    if (openEnd !== -1) {
      const head = raw.slice(start, openEnd + 1);
      if (/\/\s*>$/.test(head)) {
        return { kind, start, end: openEnd + 1 };
      }
    }
  }

  return null;
};

type TextVisualBlock =
  | { kind: HtmlVisualKind; start: number; end: number }
  | { kind: 'markdown-table'; start: number; end: number };

const findFirstTextVisualBlock = (raw: string): TextVisualBlock | null => {
  const htmlBlock = findFirstHtmlVisualBlock(raw);
  const markdownTableBlock = findFirstMarkdownTableBlock(raw);
  if (!htmlBlock && !markdownTableBlock) {
    return null;
  }
  if (!htmlBlock) {
    return { kind: 'markdown-table', ...markdownTableBlock! };
  }
  if (!markdownTableBlock) {
    return htmlBlock;
  }
  return markdownTableBlock.start < htmlBlock.start
    ? { kind: 'markdown-table', ...markdownTableBlock }
    : htmlBlock;
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
  if (
    !['iframe', 'div', 'section', 'article', 'main', 'template'].includes(tag)
  ) {
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

export type AudioInteractionItem = ChatContentItem & {
  page: number;
  audioPosition?: number;
};

export type ListenSlideItem = {
  item: ChatContentItem;
  segments: RenderSegment[];
};

const resolveListenInteractionAutoContinueMs = () => {
  const raw = process.env.NEXT_PUBLIC_LISTEN_INTERACTION_AUTOCONTINUE_MS;
  if (!raw) {
    return 0;
  }
  const value = Number(raw);
  if (Number.isNaN(value) || value <= 0) {
    return 0;
  }
  return Math.floor(value);
};

const getAvailableAudioPositions = (item: ChatContentItem): number[] => {
  const contractPositions =
    item.avContract && item.avContract.speakable_segments
      ? item.avContract.speakable_segments
          .map(segment => Number(segment.position ?? 0))
          .filter(value => !Number.isNaN(value))
      : [];
  const persistedPositions =
    item.audios && item.audios.length > 0
      ? Array.from(
          new Set(
            item.audios
              .map(audio => Number((audio as any).position ?? 0))
              .filter(value => !Number.isNaN(value)),
          ),
        )
      : [];
  const trackPositions =
    item.audioTracksByPosition &&
    Object.keys(item.audioTracksByPosition).length > 0
      ? Object.keys(item.audioTracksByPosition)
          .map(Number)
          .filter(value => !Number.isNaN(value))
      : [];
  return Array.from(
    new Set([...contractPositions, ...persistedPositions, ...trackPositions]),
  ).sort((a, b) => a - b);
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

export const useListenContentData = (items: ChatContentItem[]) => {
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
          if (lastVisualPage >= 0) {
            activeTimelinePage = lastVisualPage;
          }
          return;
        }

        const availablePositions = getAvailableAudioPositions(contentItem);
        const hasMultiplePositions =
          availablePositions.length > 1 ||
          availablePositions.some(position => position > 0);
        const positions = hasMultiplePositions
          ? availablePositions.length
            ? availablePositions
            : [0]
          : [0];

        const fallbackPage =
          (firstVisualPage >= 0 ? firstVisualPage : null) ??
          (lastVisualPage >= 0 ? lastVisualPage : null) ??
          (activeTimelinePage >= 0 ? activeTimelinePage : null) ??
          0;

        positions.forEach(position => {
          const mappedPage = pagesForAudio[position];
          const resolvedPage =
            typeof mappedPage === 'number' && mappedPage >= 0
              ? mappedPage
              : fallbackPage;
          if (typeof mappedPage !== 'number' || mappedPage < 0) {
            // eslint-disable-next-line no-console
            console.warn('[listen-timeline] position exists but no slide', {
              generated_block_bid: contentItem.generated_block_bid,
              position,
              mappedPage,
              fallbackPage,
            });
          }
          nextAudioAndInteractionList.push({
            ...contentItem,
            page: resolvedPage,
            audioPosition: hasMultiplePositions ? position : undefined,
          });
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
  }, [items]);

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
    if (!prevFirstSlideBidRef.current) {
      shouldSlideToFirstRef.current = true;
      onResetSequence?.();
    } else if (prevFirstSlideBidRef.current !== firstSlideBid) {
      shouldSlideToFirstRef.current = true;
      onResetSequence?.();
    }
    prevFirstSlideBidRef.current = firstSlideBid;
  }, [firstSlideBid, onResetSequence]);

  useEffect(() => {
    if (!sectionTitle) {
      prevSectionTitleRef.current = null;
      return;
    }
    if (
      prevSectionTitleRef.current &&
      prevSectionTitleRef.current !== sectionTitle
    ) {
      shouldSlideToFirstRef.current = true;
      onResetSequence?.();
    }
    prevSectionTitleRef.current = sectionTitle;
  }, [sectionTitle, onResetSequence]);

  const syncInteractionForCurrentPage = useCallback(
    (pageIndex?: number) => {
      const targetPage =
        typeof pageIndex === 'number' ? pageIndex : currentPptPageRef.current;
      const queue = interactionByPage.get(targetPage) || [];
      setCurrentInteraction(queue[0] ?? null);
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
        console.log('销毁reveal实例 (no content)');
        deckRef.current?.destroy();
      } catch (e) {
        console.warn('Reveal.js destroy 調用失敗。');
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
        console.warn('Reveal.js destroy 調用失敗。');
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

      const shouldAutoFollowOnAppend =
        prevSlidesLength > 0 &&
        nextSlidesLength > prevSlidesLength &&
        currentIndex >= prevLastIndex;
      if (pendingAutoNextRef.current) {
        const moved = goToNextBlock();
        pendingAutoNextRef.current = !moved;
      }

      // During playback, slide progression should be controlled by audio sequence
      // mapping only. Auto-following newly appended slides here causes premature
      // visual jumps before narration finishes.
      if (isAudioPlaying) {
        prevSlidesLengthRef.current = nextSlidesLength;
        return;
      }

      const shouldFollowLatest =
        shouldAutoFollowOnAppend ||
        !hasAutoSlidToLatestRef.current ||
        currentIndex >= lastIndex;
      if (shouldFollowLatest) {
        deckRef.current.slide(lastIndex);
        hasAutoSlidToLatestRef.current = true;
      } else if (indices) {
        deckRef.current.slide(indices.h, indices.v, indices.f);
      }
      updateNavState();
      prevSlidesLengthRef.current = nextSlidesLength;
    } catch {
      // Ignore reveal sync errors
    }
  }, [
    slideItems,
    isAudioPlaying,
    isLoading,
    goToNextBlock,
    goToBlock,
    chatRef,
    updateNavState,
    deckRef,
    pendingAutoNextRef,
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
  const audioPlayerRef = useRef<AudioPlayerHandle | null>(null);
  const audioSequenceIndexRef = useRef(-1);
  const audioSequenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const audioSequenceListRef = useRef<AudioInteractionItem[]>([]);
  const prevAudioSequenceLengthRef = useRef(0);
  const [activeAudioBid, setActiveAudioBid] = useState<string | null>(null);
  const [activeAudioPosition, setActiveAudioPosition] = useState(0);
  const [sequenceInteraction, setSequenceInteraction] =
    useState<AudioInteractionItem | null>(null);
  const [isAudioSequenceActive, setIsAudioSequenceActive] = useState(false);
  const [audioSequenceToken, setAudioSequenceToken] = useState(0);
  const isSequencePausedRef = useRef(false);
  const interactionNextIndexRef = useRef<number | null>(null);
  const interactionAutoContinueMsRef = useRef<number>(
    resolveListenInteractionAutoContinueMs(),
  );

  const lastPlayedAudioBidRef = useRef<string | null>(null);

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

  useEffect(() => {
    audioSequenceListRef.current = audioAndInteractionList;
    // console.log('audioAndInteractionList', audioSequenceListRef.current);
    // console.log('listen-sequence-list-update', {
    //   listLength: audioAndInteractionList.length,
    //   contentCount: audioAndInteractionList.filter(
    //     item => item.type === ChatContentItemType.CONTENT,
    //   ).length,
    //   interactionCount: audioAndInteractionList.filter(
    //     item => item.type === ChatContentItemType.INTERACTION,
    //   ).length,
    // });
  }, [audioAndInteractionList]);

  const clearAudioSequenceTimer = useCallback(() => {
    if (audioSequenceTimerRef.current) {
      clearTimeout(audioSequenceTimerRef.current);
      audioSequenceTimerRef.current = null;
    }
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

      // Ensure Reveal sees newly appended slides before attempting to navigate.
      // Without this, audio can advance to the next position before its visual
      // slide exists in the deck (race between streaming updates and playback).
      try {
        if (typeof deck.sync === 'function') {
          deck.sync();
        }
        if (typeof deck.layout === 'function') {
          deck.layout();
        }
      } catch {
        // Ignore sync/layout errors; we will retry.
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

      const currentIndex = deck.getIndices?.().h ?? 0;
      if (currentIndex !== page) {
        deck.slide(page);
      }
      return true;
    },
    [deckRef],
  );

  const resolveSequenceStartIndex = useCallback((page: number) => {
    const list = audioSequenceListRef.current;
    if (!list.length) {
      return -1;
    }
    const audioIndex = list.findIndex(
      item => item.page === page && item.type === ChatContentItemType.CONTENT,
    );
    if (audioIndex >= 0) {
      return audioIndex;
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
    const nextIndex = list.findIndex(item => item.page > page);
    return nextIndex;
  }, []);

  const playAudioSequenceFromIndex = useCallback(
    (index: number, retryCount = 0) => {
      // Prevent redundant calls for the same index if already active
      if (audioSequenceIndexRef.current === index && isAudioSequenceActive) {
        return;
      }
      if (isSequencePausedRef.current) {
        // console.log('listen-sequence-skip-play-paused', { index });
        return;
      }

      clearAudioSequenceTimer();
      const list = audioSequenceListRef.current;
      const nextItem = list[index];

      if (!nextItem) {
        // console.log('listen-sequence-end', { index, listLength: list.length });
        setSequenceInteraction(null);
        setActiveAudioBid(null);
        setIsAudioSequenceActive(false);
        return;
      }

      const pageReady = syncToSequencePage(nextItem.page);
      if (!pageReady) {
        // Wait until the target slide is actually present in the deck before
        // advancing playback. This prevents audio from starting "ahead" of the
        // rendered visual during streaming output.
        audioSequenceTimerRef.current = setTimeout(() => {
          playAudioSequenceFromIndex(index, retryCount + 1);
        }, 120);
        return;
      }

      if (
        nextItem.type === ChatContentItemType.CONTENT &&
        !hasPlayableAudioForItem(nextItem)
      ) {
        // The timeline may know this position from contract before audio chunks/URL
        // arrive. Retry briefly instead of switching to an empty track.
        if (retryCount < 80) {
          audioSequenceTimerRef.current = setTimeout(() => {
            playAudioSequenceFromIndex(index, retryCount + 1);
          }, 120);
          return;
        }
        // Guard fallback: if still unavailable after retries, skip to next item.
        const listLength = list.length;
        if (index + 1 < listLength) {
          playAudioSequenceFromIndex(index + 1);
        } else {
          setSequenceInteraction(null);
          setActiveAudioBid(null);
          setIsAudioSequenceActive(false);
        }
        return;
      }

      audioSequenceIndexRef.current = index;
      setIsAudioSequenceActive(true);
      if (nextItem.generated_block_bid) {
        lastPlayedAudioBidRef.current = nextItem.generated_block_bid;
      }

      if (nextItem.type === ChatContentItemType.INTERACTION) {
        setSequenceInteraction(nextItem);
        setActiveAudioBid(null);
        const nextSequenceIndex = index >= list.length - 1 ? null : index + 1;
        interactionNextIndexRef.current = nextSequenceIndex;
        const autoContinueMs = interactionAutoContinueMsRef.current;
        if (
          nextSequenceIndex !== null &&
          Number.isFinite(autoContinueMs) &&
          autoContinueMs > 0
        ) {
          audioSequenceTimerRef.current = setTimeout(() => {
            playAudioSequenceFromIndex(nextSequenceIndex);
          }, autoContinueMs);
        }
        return;
      }
      interactionNextIndexRef.current = null;
      setSequenceInteraction(null);
      setActiveAudioBid(nextItem.generated_block_bid);
      setActiveAudioPosition(nextItem.audioPosition ?? 0);
      setAudioSequenceToken(prev => prev + 1);
    },
    [
      clearAudioSequenceTimer,
      hasPlayableAudioForItem,
      isAudioSequenceActive,
      syncToSequencePage,
    ],
  );

  useEffect(() => {
    const prevLength = prevAudioSequenceLengthRef.current;
    const nextLength = audioAndInteractionList.length;
    prevAudioSequenceLengthRef.current = nextLength;
    // console.log('listen-sequence-length-change', {
    //   prevLength,
    //   nextLength,
    //   isAudioSequenceActive,
    //   sequenceIndex: audioSequenceIndexRef.current,
    // });
    if (previewMode || !nextLength) {
      return;
    }
    if (isSequencePausedRef.current) {
      // console.log('listen-sequence-skip-length-change-paused', {
      //   nextLength,
      // });
      return;
    }
    const currentIndex = audioSequenceIndexRef.current;

    if (
      isAudioSequenceActive &&
      sequenceInteraction &&
      nextLength > prevLength
    ) {
      // If audio for the same interaction page arrives after interaction was shown,
      // prioritize that content block before attempting to continue.
      const samePageAudioIndex = audioAndInteractionList.findIndex(
        item =>
          item.type === ChatContentItemType.CONTENT &&
          item.page === sequenceInteraction.page,
      );
      if (samePageAudioIndex >= 0) {
        playAudioSequenceFromIndex(samePageAudioIndex);
        return;
      }

      const interactionIndex = sequenceInteraction.generated_block_bid
        ? audioAndInteractionList.findIndex(
            item =>
              item.type === ChatContentItemType.INTERACTION &&
              item.generated_block_bid ===
                sequenceInteraction.generated_block_bid,
          )
        : currentIndex;
      if (interactionIndex >= 0) {
        const nextAudioIndex = audioAndInteractionList.findIndex(
          (item, index) =>
            index > interactionIndex &&
            item.type === ChatContentItemType.CONTENT,
        );
        if (nextAudioIndex >= 0) {
          playAudioSequenceFromIndex(nextAudioIndex);
          return;
        }
      }

      if (currentIndex >= 0 && currentIndex === prevLength - 1) {
        const fallbackIndex = Math.min(currentIndex + 1, nextLength - 1);
        if (fallbackIndex > currentIndex) {
          playAudioSequenceFromIndex(fallbackIndex);
          return;
        }
      }
    }

    // Auto-play new content if it matches the current page (e.g. Retake, or streaming new content)
    if (nextLength > prevLength) {
      const newItemIndex = nextLength - 1;
      const newItem = audioAndInteractionList[newItemIndex];
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;

      if (newItem?.page === currentPage) {
        // If it's the first item ever (prevLength === 0), or if we are appending to the current page sequence
        // we should play it.
        // But if we are just appending a new item to the END of the list, we should only play it if
        // we are not currently playing something else (unless it's a replacement/retake of the same index).
        if (prevLength === 0) {
          // Initial load for this page
          // Check if we are recovering from a flash (list became empty then full again)
          const lastBid = lastPlayedAudioBidRef.current;
          const resumeIndex = lastBid
            ? audioAndInteractionList.findIndex(
                item => item.generated_block_bid === lastBid,
              )
            : -1;

          if (resumeIndex >= 0) {
            // Resume playback from the last known block to maintain continuity
            playAudioSequenceFromIndex(resumeIndex);
          } else {
            const startIndex = resolveSequenceStartIndex(currentPage);
            if (startIndex >= 0) {
              playAudioSequenceFromIndex(startIndex);
            }
          }
        } else {
          // Appending new item
          if (
            !isAudioSequenceActive ||
            audioSequenceIndexRef.current === newItemIndex
          ) {
            playAudioSequenceFromIndex(newItemIndex);
          }
        }
      }
    }
  }, [
    audioAndInteractionList,
    isAudioSequenceActive,
    playAudioSequenceFromIndex,
    previewMode,
    sequenceInteraction,
    deckRef,
    currentPptPageRef,
    resolveSequenceStartIndex,
  ]);

  const resetSequenceState = useCallback(() => {
    isSequencePausedRef.current = false;
    clearAudioSequenceTimer();
    audioPlayerRef.current?.pause({
      traceId: 'sequence-reset',
      keepAutoPlay: true,
    });
    audioSequenceIndexRef.current = -1;
    interactionNextIndexRef.current = null;
    setSequenceInteraction(null);
    setActiveAudioBid(null);
    setActiveAudioPosition(0);
    setIsAudioSequenceActive(false);
    // console.log('listen-sequence-reset');
  }, [clearAudioSequenceTimer]);

  const startSequenceFromIndex = useCallback(
    (index: number) => {
      const listLength = audioSequenceListRef.current.length;
      if (!listLength) {
        // console.log('listen-sequence-start-empty', { index });
        return;
      }
      const maxIndex = Math.max(listLength - 1, 0);
      const nextIndex = Math.min(Math.max(index, 0), maxIndex);
      resetSequenceState();
      // console.log('listen-sequence-start-index', { index, nextIndex });
      playAudioSequenceFromIndex(nextIndex);
    },
    [playAudioSequenceFromIndex, resetSequenceState],
  );

  const startSequenceFromPage = useCallback(
    (page: number) => {
      const startIndex = resolveSequenceStartIndex(page);
      if (startIndex < 0) {
        // console.log('listen-sequence-start-page-miss', { page });
        return;
      }
      // console.log('listen-sequence-start-page', { page, startIndex });
      startSequenceFromIndex(startIndex);
    },
    [resolveSequenceStartIndex, startSequenceFromIndex],
  );

  useEffect(() => {
    return () => {
      clearAudioSequenceTimer();
    };
  }, [clearAudioSequenceTimer]);

  useEffect(() => {
    if (audioAndInteractionList.length) {
      return;
    }
    clearAudioSequenceTimer();
    audioSequenceIndexRef.current = -1;
    interactionNextIndexRef.current = null;
    setActiveAudioBid(null);
    setActiveAudioPosition(0);
    setSequenceInteraction(null);
    setIsAudioSequenceActive(false);
  }, [audioAndInteractionList.length, clearAudioSequenceTimer]);

  useEffect(() => {
    if (!shouldStartSequenceRef.current) {
      return;
    }
    if (!audioAndInteractionList.length) {
      // console.log('listen-sequence-auto-start-skip-empty');
      return;
    }
    if (isSequencePausedRef.current) {
      // console.log('listen-sequence-auto-start-skip-paused');
      return;
    }
    shouldStartSequenceRef.current = false;

    // Check if we can resume from the last played block (e.g. after a list flash/refresh)
    if (lastPlayedAudioBidRef.current) {
      const resumeIndex = audioAndInteractionList.findIndex(
        item => item.generated_block_bid === lastPlayedAudioBidRef.current,
      );
      if (resumeIndex >= 0) {
        // We found the last played item, so we are likely just recovering from a refresh.
        // Resume from there instead of restarting.
        // console.log('listen-sequence-auto-resume', {
        //   resumeIndex,
        //   blockBid: lastPlayedAudioBidRef.current,
        // });
        playAudioSequenceFromIndex(resumeIndex);
        return;
      }
    }

    // Otherwise, truly start from the beginning
    // console.log('listen-sequence-auto-start');
    playAudioSequenceFromIndex(0);
  }, [
    audioAndInteractionList,
    playAudioSequenceFromIndex,
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

  const tryAdvanceToNextBlock = useCallback(() => {
    const currentBid = resolveContentBid(activeBlockBidRef.current);
    const nextBid = getNextContentBid(currentBid);
    if (!nextBid) {
      // console.log('listen-sequence-advance-miss', { currentBid });
      return false;
    }

    const moved = goToBlock(nextBid);
    if (moved) {
      // console.log('listen-sequence-advance-success', {
      //   currentBid,
      //   nextBid,
      // });
      return true;
    }

    if (shouldRenderEmptyPpt) {
      activeBlockBidRef.current = `empty-ppt-${nextBid}`;
      // console.log('listen-sequence-advance-empty-ppt', { nextBid });
      return true;
    }

    pendingAutoNextRef.current = true;
    // console.log('listen-sequence-advance-pending', { nextBid });
    return true;
  }, [
    activeBlockBidRef,
    getNextContentBid,
    goToBlock,
    pendingAutoNextRef,
    resolveContentBid,
    shouldRenderEmptyPpt,
  ]);

  const continueAfterInteraction = useCallback(() => {
    if (previewMode) {
      return;
    }
    clearAudioSequenceTimer();
    isSequencePausedRef.current = false;
    const nextIndex = interactionNextIndexRef.current;
    interactionNextIndexRef.current = null;
    setSequenceInteraction(null);
    if (typeof nextIndex === 'number' && nextIndex >= 0) {
      playAudioSequenceFromIndex(nextIndex);
      return;
    }
    setActiveAudioBid(null);
    setIsAudioSequenceActive(false);
    tryAdvanceToNextBlock();
  }, [
    clearAudioSequenceTimer,
    playAudioSequenceFromIndex,
    previewMode,
    tryAdvanceToNextBlock,
  ]);

  const handleAudioEnded = useCallback(() => {
    if (isSequencePausedRef.current) {
      // console.log('listen-sequence-ended-skip-paused');
      return;
    }
    const list = audioSequenceListRef.current;
    if (!list.length) {
      tryAdvanceToNextBlock();
      return;
    }

    const currentIndex = audioSequenceIndexRef.current;
    const nextIndex = currentIndex + 1;
    const currentItem = list[currentIndex];
    const nextItem = list[nextIndex];
    const currentPage = currentItem?.page ?? currentPptPageRef.current;
    const nextPage = nextItem?.page ?? null;
    const currentBid =
      currentItem?.type === ChatContentItemType.CONTENT
        ? resolveContentBid(currentItem.generated_block_bid)
        : null;
    const nextBid =
      nextItem?.type === ChatContentItemType.CONTENT
        ? resolveContentBid(nextItem.generated_block_bid)
        : null;

    // Do not skip silent visual slides. If the next timeline item is on a later page,
    // stop at the immediate next slide and wait for manual navigation.
    if (
      typeof currentPage === 'number' &&
      typeof nextPage === 'number' &&
      nextPage > currentPage + 1
    ) {
      const targetPage = currentPage + 1;
      const moved = syncToSequencePage(targetPage);
      if (!moved) {
        // If Reveal hasn't caught up yet, retry briefly.
        clearAudioSequenceTimer();
        audioSequenceTimerRef.current = setTimeout(() => {
          handleAudioEnded();
        }, 120);
        return;
      }
      setSequenceInteraction(null);
      setActiveAudioBid(null);
      setIsAudioSequenceActive(false);
      return;
    }

    // Keep immediate progression for segmented audio within the same content block.
    if (currentBid && nextBid && currentBid === nextBid) {
      playAudioSequenceFromIndex(nextIndex);
      return;
    }

    const continueSequence = () => {
      if (nextIndex >= list.length) {
        // console.log('listen-sequence-ended-last', {
        //   nextIndex,
        //   listLength: list.length,
        // });
        setActiveAudioBid(null);
        setIsAudioSequenceActive(false);
        tryAdvanceToNextBlock();
        return;
      }
      // console.log('listen-sequence-ended-next', { nextIndex });
      playAudioSequenceFromIndex(nextIndex);
    };

    continueSequence();
  }, [
    clearAudioSequenceTimer,
    playAudioSequenceFromIndex,
    resolveContentBid,
    syncToSequencePage,
    tryAdvanceToNextBlock,
  ]);

  const logAudioAction = useCallback(
    (action: 'play' | 'pause') => {
      // console.log(`listen-audio-${action}`, {
      //   activeAudioBid,
      //   activeAudioBlockBid,
      //   audioUrl: activeContentItem?.audioUrl,
      //   content: activeContentItem?.content,
      //   listLength: audioSequenceListRef.current.length,
      //   sequenceIndex: audioSequenceIndexRef.current,
      //   isAudioSequenceActive,
      // });
    },
    [
      activeAudioBid,
      activeAudioBlockBid,
      activeContentItem?.audioUrl,
      activeContentItem?.content,
      isAudioSequenceActive,
    ],
  );

  const handlePlay = useCallback(() => {
    if (previewMode) {
      return;
    }
    isSequencePausedRef.current = false;
    // console.log('listen-sequence-handle-play', {
    //   activeAudioBid,
    //   listLength: audioSequenceListRef.current.length,
    // });
    // console.log('listen-toggle-play', {
    //   activeAudioBid,
    //   hasAudioRef: Boolean(audioPlayerRef.current),
    //   listLength: audioSequenceListRef.current.length,
    //   sequenceIndex: audioSequenceIndexRef.current,
    //   isAudioSequenceActive,
    // });
    logAudioAction('play');
    if (sequenceInteraction) {
      continueAfterInteraction();
      return;
    }
    if (!activeAudioBid && audioSequenceListRef.current.length) {
      const currentPage =
        deckRef.current?.getIndices?.().h ?? currentPptPageRef.current;
      startSequenceFromPage(currentPage);
      return;
    }
    audioPlayerRef.current?.play();
  }, [
    previewMode,
    activeAudioBid,
    isAudioSequenceActive,
    sequenceInteraction,
    continueAfterInteraction,
    logAudioAction,
    startSequenceFromPage,
    deckRef,
    currentPptPageRef,
  ]);

  const handlePause = useCallback(
    (traceId?: string) => {
      if (previewMode) {
        return;
      }
      // console.log('listen-mode-handle-pause', {
      //   traceId,
      //   activeAudioBid,
      //   activeAudioBlockBid,
      //   audioUrl: activeContentItem?.audioUrl,
      //   content: activeContentItem?.content,
      //   isAudioSequenceActive,
      //   sequenceIndex: audioSequenceIndexRef.current,
      // });
      logAudioAction('pause');
      isSequencePausedRef.current = true;
      // console.log('listen-sequence-handle-pause', { traceId });
      clearAudioSequenceTimer();
      audioPlayerRef.current?.pause({ traceId });
      // console.log('listen-mode-handle-pause-end', {
      //   traceId,
      //   activeAudioBid,
      //   activeAudioBlockBid,
      // });
    },
    [
      previewMode,
      activeAudioBid,
      activeAudioBlockBid,
      activeContentItem?.audioUrl,
      activeContentItem?.content,
      isAudioSequenceActive,
      logAudioAction,
      clearAudioSequenceTimer,
    ],
  );

  useEffect(() => {
    setIsAudioPlaying(false);
  }, [audioSequenceToken, setIsAudioPlaying]);

  // Watchdog: if the sequence is active and we have an activeAudioBid (i.e. we
  // expect audio to be playing), but the AudioPlayer has not reported "playing"
  // state for 8 seconds, force-advance to the next item. This catches any
  // remaining edge cases where onEnded is never fired.
  const handleAudioEndedRef = useRef(handleAudioEnded);
  handleAudioEndedRef.current = handleAudioEnded;

  useEffect(() => {
    if (!isAudioSequenceActive || !activeAudioBid || isAudioPlaying) {
      return;
    }
    const timer = setTimeout(() => {
      // Re-check conditions inside the timeout to avoid stale closure issues.
      // isAudioPlaying is from the outer scope snapshot, but if the effect
      // hasn't been cleaned up it means the conditions still hold.
      handleAudioEndedRef.current();
    }, 8000);
    return () => clearTimeout(timer);
  }, [isAudioSequenceActive, activeAudioBid, isAudioPlaying]);

  return {
    audioPlayerRef,
    activeContentItem,
    activeAudioBlockBid,
    activeAudioPosition,
    sequenceInteraction,
    isAudioSequenceActive,
    audioSequenceToken,
    handleAudioEnded,
    handlePlay,
    handlePause,
    continueAfterInteraction,
    startSequenceFromIndex,
    startSequenceFromPage,
  };
};
