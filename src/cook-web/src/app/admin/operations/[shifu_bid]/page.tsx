'use client';

import { Copy } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import { copyText } from '@/c-utils/textutils';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { fail, show } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminOperationCourseChapterDetailResponse,
  AdminOperationCourseDetailChapter,
  AdminOperationCourseDetailResponse,
} from '../operation-course-types';
import useOperatorGuard from '../useOperatorGuard';

type ErrorState = { message: string; code?: number };

type FlattenedChapterRow = AdminOperationCourseDetailChapter & {
  depth: number;
};

const EMPTY_CHAPTER_DETAIL: AdminOperationCourseChapterDetailResponse = {
  outline_item_bid: '',
  title: '',
  content: '',
  llm_system_prompt: '',
  llm_system_prompt_source: '',
};

const CHAPTER_COLUMN_MIN_WIDTH = 80;
const CHAPTER_COLUMN_MAX_WIDTH = 420;
const CHAPTER_COLUMN_WIDTH_STORAGE_KEY =
  'adminOperationCourseDetailColumnWidths';
const CHAPTER_COLUMN_DEFAULT_WIDTHS = {
  position: 90,
  name: 220,
  chapterId: 220,
  learningPermission: 130,
  visibility: 110,
  contentStatus: 110,
  modifier: 170,
  updatedAt: 170,
  contentDetail: 100,
  followUpCount: 100,
  ratingCount: 100,
} as const;

type ChapterColumnKey = keyof typeof CHAPTER_COLUMN_DEFAULT_WIDTHS;
type ChapterColumnWidthState = Record<ChapterColumnKey, number>;

const CHAPTER_COLUMN_KEYS = Object.keys(
  CHAPTER_COLUMN_DEFAULT_WIDTHS,
) as ChapterColumnKey[];

const clampChapterWidth = (value: number): number =>
  Math.min(CHAPTER_COLUMN_MAX_WIDTH, Math.max(CHAPTER_COLUMN_MIN_WIDTH, value));

const createChapterColumnWidthState = (
  overrides?: Partial<ChapterColumnWidthState>,
): ChapterColumnWidthState => {
  const widths: ChapterColumnWidthState = { ...CHAPTER_COLUMN_DEFAULT_WIDTHS };
  CHAPTER_COLUMN_KEYS.forEach(key => {
    const nextValue = overrides?.[key];
    if (typeof nextValue === 'number' && Number.isFinite(nextValue)) {
      widths[key] = clampChapterWidth(nextValue);
    } else {
      widths[key] = clampChapterWidth(widths[key]);
    }
  });
  return widths;
};

const loadStoredChapterColumnWidthOverrides =
  (): Partial<ChapterColumnWidthState> => {
    if (typeof window === 'undefined') {
      return {};
    }
    try {
      const serialized = window.localStorage.getItem(
        CHAPTER_COLUMN_WIDTH_STORAGE_KEY,
      );
      if (!serialized) {
        return {};
      }
      const parsed = JSON.parse(serialized) as Partial<ChapterColumnWidthState>;
      const overrides: Partial<ChapterColumnWidthState> = {};
      CHAPTER_COLUMN_KEYS.forEach(key => {
        const nextValue = parsed?.[key];
        if (typeof nextValue === 'number' && Number.isFinite(nextValue)) {
          overrides[key] = clampChapterWidth(nextValue);
        }
      });
      return overrides;
    } catch {
      return {};
    }
  };

const persistManualChapterColumnWidths = (
  chapterColumnWidths: ChapterColumnWidthState,
  manualResizeMap: Record<ChapterColumnKey, boolean>,
): void => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    const manualOverrides = CHAPTER_COLUMN_KEYS.reduce<
      Partial<ChapterColumnWidthState>
    >((acc, key) => {
      if (manualResizeMap[key]) {
        acc[key] = chapterColumnWidths[key];
      }
      return acc;
    }, {});
    if (Object.keys(manualOverrides).length === 0) {
      window.localStorage.removeItem(CHAPTER_COLUMN_WIDTH_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      CHAPTER_COLUMN_WIDTH_STORAGE_KEY,
      JSON.stringify(manualOverrides),
    );
  } catch {
    // Ignore storage errors.
  }
};

const EMPTY_DETAIL: AdminOperationCourseDetailResponse = {
  basic_info: {
    shifu_bid: '',
    course_name: '',
    course_status: 'unpublished',
    creator_user_bid: '',
    creator_mobile: '',
    creator_email: '',
    creator_nickname: '',
    created_at: '',
    updated_at: '',
  },
  metrics: {
    visit_count_30d: 0,
    learner_count: 0,
    order_count: 0,
    order_amount: '0',
    follow_up_count: 0,
    rating_score: '',
  },
  chapters: [],
};

const flattenChapters = (
  chapters: AdminOperationCourseDetailChapter[],
  depth = 0,
): FlattenedChapterRow[] =>
  chapters.flatMap(chapter => [
    { ...chapter, depth },
    ...flattenChapters(chapter.children || [], depth + 1),
  ]);

const formatCount = (value: number): string =>
  Number.isFinite(value) ? value.toLocaleString() : '--';

function OverflowTooltipText({
  text,
  className,
}: {
  text?: string;
  className?: string;
}) {
  const value = text && text.trim().length > 0 ? text : '--';
  const textRef = useRef<HTMLSpanElement | null>(null);
  const [isOverflowing, setIsOverflowing] = useState(false);

  useEffect(() => {
    const element = textRef.current;
    if (!element) {
      return;
    }

    const updateOverflowState = () => {
      setIsOverflowing(
        element.scrollWidth > element.clientWidth ||
          element.scrollHeight > element.clientHeight,
      );
    };

    updateOverflowState();

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(() => {
        updateOverflowState();
      });
      observer.observe(element);
      return () => observer.disconnect();
    }

    window.addEventListener('resize', updateOverflowState);
    return () => window.removeEventListener('resize', updateOverflowState);
  }, [value]);

  const content = (
    <span
      ref={textRef}
      className={`inline-block max-w-full overflow-hidden text-ellipsis whitespace-nowrap align-bottom ${className || ''}`}
    >
      {value}
    </span>
  );

  if (!isOverflowing) {
    return content;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side='top'>{value}</TooltipContent>
    </Tooltip>
  );
}

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.operationsCourse.detail.title')
 * t('module.operationsCourse.detail.back')
 * t('module.operationsCourse.detail.basicInfo')
 * t('module.operationsCourse.detail.metrics')
 * t('module.operationsCourse.detail.chapters')
 * t('module.operationsCourse.detail.fields.courseName')
 * t('module.operationsCourse.detail.fields.courseId')
 * t('module.operationsCourse.detail.fields.status')
 * t('module.operationsCourse.detail.fields.creator')
 * t('module.operationsCourse.detail.fields.createdAt')
 * t('module.operationsCourse.detail.fields.updatedAt')
 * t('module.operationsCourse.detail.metricsLabels.visitCount30d')
 * t('module.operationsCourse.detail.metricsLabels.learnerCount')
 * t('module.operationsCourse.detail.metricsLabels.orderCount')
 * t('module.operationsCourse.detail.metricsLabels.orderAmount')
 * t('module.operationsCourse.detail.metricsLabels.followUpCount')
 * t('module.operationsCourse.detail.metricsLabels.ratingScore')
 * t('module.operationsCourse.detail.chaptersTable.position')
 * t('module.operationsCourse.detail.chaptersTable.name')
 * t('module.operationsCourse.detail.chaptersTable.type')
 * t('module.operationsCourse.detail.chaptersTable.learningPermission')
 * t('module.operationsCourse.detail.chaptersTable.visibility')
 * t('module.operationsCourse.detail.chaptersTable.contentStatus')
 * t('module.operationsCourse.detail.chaptersTable.modifier')
 * t('module.operationsCourse.detail.chaptersTable.contentDetail')
 * t('module.operationsCourse.detail.chaptersTable.followUpCount')
 * t('module.operationsCourse.detail.chaptersTable.ratingCount')
 * t('module.operationsCourse.detail.chaptersTable.chapterId')
 * t('module.operationsCourse.detail.chaptersTable.updatedAt')
 * t('module.operationsCourse.detail.chaptersTable.empty')
 * t('module.operationsCourse.detail.chaptersTable.detailAction')
 * t('module.operationsCourse.detail.chapterType.chapter')
 * t('module.operationsCourse.detail.chapterType.lesson')
 * t('module.operationsCourse.detail.learningPermission.guest')
 * t('module.operationsCourse.detail.learningPermission.free')
 * t('module.operationsCourse.detail.learningPermission.paid')
 * t('module.operationsCourse.detail.learningPermission.unknown')
 * t('module.operationsCourse.detail.visibility.visible')
 * t('module.operationsCourse.detail.visibility.hidden')
 * t('module.operationsCourse.detail.contentStatus.has')
 * t('module.operationsCourse.detail.contentStatus.empty')
 * t('module.operationsCourse.detail.contentStatus.unknown')
 * t('module.operationsCourse.detail.contentDetailDialog.title')
 * t('module.operationsCourse.detail.contentDetailDialog.copy')
 * t('module.operationsCourse.detail.contentDetailDialog.copySuccess')
 * t('module.operationsCourse.detail.contentDetailDialog.copyFailed')
 * t('module.operationsCourse.detail.contentDetailDialog.empty')
 * t('module.operationsCourse.detail.contentDetailDialog.sections.content')
 * t('module.operationsCourse.detail.contentDetailDialog.sections.systemPrompt')
 * t('module.operationsCourse.detail.contentDetailDialog.sources.lesson')
 * t('module.operationsCourse.detail.contentDetailDialog.sources.chapter')
 * t('module.operationsCourse.detail.contentDetailDialog.sources.course')
 * t('module.operationsCourse.statusLabels.unknown')
 */
export default function AdminOperationCourseDetailPage() {
  const router = useRouter();
  const params = useParams<{ shifu_bid?: string }>();
  const { t } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');
  const { isReady } = useOperatorGuard();
  const currencySymbol = useEnvStore(state => state.currencySymbol || '');
  const storedChapterManualWidthsRef = useRef<Partial<ChapterColumnWidthState>>(
    loadStoredChapterColumnWidthOverrides(),
  );

  const [detail, setDetail] =
    useState<AdminOperationCourseDetailResponse>(EMPTY_DETAIL);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [selectedChapter, setSelectedChapter] =
    useState<FlattenedChapterRow | null>(null);
  const [selectedChapterDetail, setSelectedChapterDetail] =
    useState<AdminOperationCourseChapterDetailResponse>(EMPTY_CHAPTER_DETAIL);
  const [chapterDetailLoading, setChapterDetailLoading] = useState(false);
  const [chapterColumnWidths, setChapterColumnWidths] =
    useState<ChapterColumnWidthState>(() =>
      createChapterColumnWidthState(storedChapterManualWidthsRef.current),
    );
  const chapterColumnWidthsRef = useRef(chapterColumnWidths);
  const chapterColumnResizeRef = useRef<{
    key: ChapterColumnKey;
    startX: number;
    startWidth: number;
  } | null>(null);
  const manualChapterResizeRef = useRef<Record<ChapterColumnKey, boolean>>(
    CHAPTER_COLUMN_KEYS.reduce(
      (acc, key) => ({
        ...acc,
        [key]: typeof storedChapterManualWidthsRef.current[key] === 'number',
      }),
      {} as Record<ChapterColumnKey, boolean>,
    ),
  );

  const shifuBid = Array.isArray(params?.shifu_bid)
    ? params.shifu_bid[0] || ''
    : params?.shifu_bid || '';
  const emptyValue = '--';

  const fetchDetail = useCallback(async () => {
    if (!shifuBid.trim()) {
      setError({ message: t('common.core.unknownError') });
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = (await api.getAdminOperationCourseDetail({
        shifu_bid: shifuBid,
      })) as AdminOperationCourseDetailResponse;
      setDetail(response || EMPTY_DETAIL);
    } catch (err) {
      setDetail(EMPTY_DETAIL);
      if (err instanceof ErrorWithCode) {
        setError({ message: err.message, code: err.code });
      } else if (err instanceof Error) {
        setError({ message: err.message });
      } else {
        setError({ message: t('common.core.unknownError') });
      }
    } finally {
      setLoading(false);
    }
  }, [shifuBid, t]);

  useEffect(() => {
    if (!isReady) {
      return;
    }
    fetchDetail();
  }, [fetchDetail, isReady]);

  useEffect(() => {
    chapterColumnWidthsRef.current = chapterColumnWidths;
  }, [chapterColumnWidths]);

  const formatUnknownEnumLabel = useCallback(
    (labelKey: string, rawValue?: string) => {
      const fallbackLabel = tOperations(labelKey);
      const normalizedValue = (rawValue || '').trim();
      if (!normalizedValue) {
        return fallbackLabel;
      }

      const wrapper = /[^\x00-\x7F]/.test(`${fallbackLabel}${normalizedValue}`)
        ? ['（', '）']
        : [' (', ')'];
      return `${fallbackLabel}${wrapper[0]}${normalizedValue}${wrapper[1]}`;
    },
    [tOperations],
  );

  const resolveCourseStatusLabel = useCallback(
    (courseStatus?: string) => {
      if (courseStatus === 'published') {
        return tOperations('statusLabels.published');
      }
      if (courseStatus === 'unpublished') {
        return tOperations('statusLabels.unpublished');
      }
      return formatUnknownEnumLabel('statusLabels.unknown', courseStatus);
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveLearningPermissionLabel = useCallback(
    (permission?: string) => {
      if (permission === 'guest') {
        return tOperations('detail.learningPermission.guest');
      }
      if (permission === 'free') {
        return tOperations('detail.learningPermission.free');
      }
      if (permission === 'paid') {
        return tOperations('detail.learningPermission.paid');
      }
      return formatUnknownEnumLabel(
        'detail.learningPermission.unknown',
        permission,
      );
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveContentStatusLabel = useCallback(
    (contentStatus?: string) => {
      if (contentStatus === 'has') {
        return tOperations('detail.contentStatus.has');
      }
      if (contentStatus === 'empty') {
        return tOperations('detail.contentStatus.empty');
      }
      return formatUnknownEnumLabel(
        'detail.contentStatus.unknown',
        contentStatus,
      );
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveChapterTypeLabel = useCallback(
    (nodeType?: string) => {
      if (nodeType === 'chapter') {
        return tOperations('detail.chapterType.chapter');
      }
      if (nodeType === 'lesson') {
        return tOperations('detail.chapterType.lesson');
      }
      return formatUnknownEnumLabel('statusLabels.unknown', nodeType);
    },
    [formatUnknownEnumLabel, tOperations],
  );

  const resolveModifierDisplay = useCallback(
    (chapter: AdminOperationCourseDetailChapter) => {
      const primary =
        chapter.modifier_mobile ||
        chapter.modifier_email ||
        chapter.modifier_user_bid ||
        emptyValue;
      const secondary =
        chapter.modifier_nickname &&
        chapter.modifier_nickname !== t('module.user.defaultUserName')
          ? chapter.modifier_nickname
          : '';
      return {
        primary,
        secondary,
      };
    },
    [emptyValue, t],
  );

  const creatorDisplay = useMemo(() => {
    const primary =
      detail.basic_info.creator_mobile ||
      detail.basic_info.creator_email ||
      detail.basic_info.creator_user_bid ||
      emptyValue;
    const secondary = detail.basic_info.creator_nickname || '';
    return {
      primary,
      secondary:
        secondary && secondary !== t('module.user.defaultUserName')
          ? secondary
          : '',
    };
  }, [
    detail.basic_info.creator_email,
    detail.basic_info.creator_mobile,
    detail.basic_info.creator_nickname,
    detail.basic_info.creator_user_bid,
    emptyValue,
    t,
  ]);

  const metricCards = useMemo(
    () => [
      {
        label: tOperations('detail.metricsLabels.visitCount30d'),
        value: formatCount(detail.metrics.visit_count_30d),
      },
      {
        label: tOperations('detail.metricsLabels.learnerCount'),
        value: formatCount(detail.metrics.learner_count),
      },
      {
        label: tOperations('detail.metricsLabels.orderCount'),
        value: formatCount(detail.metrics.order_count),
      },
      {
        label: tOperations('detail.metricsLabels.orderAmount'),
        value: `${currencySymbol}${detail.metrics.order_amount || '0'}`,
      },
      {
        label: tOperations('detail.metricsLabels.followUpCount'),
        value: formatCount(detail.metrics.follow_up_count),
      },
      {
        label: tOperations('detail.metricsLabels.ratingScore'),
        value: detail.metrics.rating_score || emptyValue,
      },
    ],
    [currencySymbol, detail.metrics, emptyValue, tOperations],
  );

  const chapterRows = useMemo(
    () => flattenChapters(detail.chapters || []),
    [detail.chapters],
  );

  const resolvePromptSourceLabel = useCallback(
    (source?: string) => {
      if (source === 'lesson') {
        return tOperations('detail.contentDetailDialog.sources.lesson');
      }
      if (source === 'chapter') {
        return tOperations('detail.contentDetailDialog.sources.chapter');
      }
      if (source === 'course') {
        return tOperations('detail.contentDetailDialog.sources.course');
      }
      return '';
    },
    [tOperations],
  );

  const buildPromptSectionLabel = useCallback(
    (baseLabel: string, source?: string) => {
      const sourceLabel = resolvePromptSourceLabel(source);
      if (!sourceLabel) {
        return baseLabel;
      }
      const wrapper = /[^\x00-\x7F]/.test(`${baseLabel}${sourceLabel}`)
        ? ['（', '）']
        : [' (', ')'];
      return `${baseLabel}${wrapper[0]}${sourceLabel}${wrapper[1]}`;
    },
    [resolvePromptSourceLabel],
  );

  const selectedChapterDetailSections = useMemo(() => {
    if (!selectedChapter) {
      return [];
    }
    return [
      {
        label: tOperations('detail.contentDetailDialog.sections.content'),
        value: selectedChapterDetail.content || '',
      },
      {
        label: buildPromptSectionLabel(
          tOperations('detail.contentDetailDialog.sections.systemPrompt'),
          selectedChapterDetail.llm_system_prompt_source,
        ),
        value: selectedChapterDetail.llm_system_prompt || '',
      },
    ];
  }, [
    buildPromptSectionLabel,
    selectedChapter,
    selectedChapterDetail,
    tOperations,
  ]);

  const selectedChapterCopyText = useMemo(() => {
    const sections = selectedChapterDetailSections.filter(section =>
      section.value.trim(),
    );
    if (sections.length === 0) {
      return '';
    }
    return sections
      .map(section => `${section.label}\n${section.value}`)
      .join('\n\n');
  }, [selectedChapterDetailSections]);

  const handleCopyChapterDetail = useCallback(async () => {
    if (!selectedChapterCopyText) {
      return;
    }
    try {
      await copyText(selectedChapterCopyText);
      show(tOperations('detail.contentDetailDialog.copySuccess'));
    } catch {
      fail(tOperations('detail.contentDetailDialog.copyFailed'));
    }
  }, [selectedChapterCopyText, tOperations]);

  const chapterDetailLayout = useMemo(() => {
    const populatedSections = selectedChapterDetailSections.filter(section =>
      section.value.trim(),
    );
    const totalCharacters = populatedSections.reduce(
      (sum, section) => sum + section.value.trim().length,
      0,
    );

    if (chapterDetailLoading) {
      return {
        dialogClassName: 'w-[min(88vw,760px)] max-w-[760px] p-0',
        bodyClassName: 'min-h-[260px] max-h-[420px] overflow-auto px-6 py-5',
      };
    }

    if (!populatedSections.length) {
      return {
        dialogClassName: 'w-[min(84vw,640px)] max-w-[640px] p-0',
        bodyClassName: 'min-h-[220px] max-h-[320px] overflow-auto px-6 py-5',
      };
    }

    if (totalCharacters <= 600) {
      return {
        dialogClassName: 'w-[min(88vw,760px)] max-w-[760px] p-0',
        bodyClassName: 'min-h-[240px] max-h-[460px] overflow-auto px-6 py-5',
      };
    }

    return {
      dialogClassName: 'w-[min(92vw,980px)] max-w-5xl p-0',
      bodyClassName: 'h-[70vh] max-h-[720px] overflow-auto px-6 py-5',
    };
  }, [chapterDetailLoading, selectedChapterDetailSections]);

  useEffect(() => {
    if (!selectedChapter?.outline_item_bid) {
      setSelectedChapterDetail(EMPTY_CHAPTER_DETAIL);
      setChapterDetailLoading(false);
      return;
    }

    let isActive = true;
    setChapterDetailLoading(true);
    setSelectedChapterDetail(EMPTY_CHAPTER_DETAIL);

    api
      .getAdminOperationCourseChapterDetail({
        shifu_bid: shifuBid,
        outline_item_bid: selectedChapter.outline_item_bid,
      })
      .then(response => {
        if (!isActive) {
          return;
        }
        setSelectedChapterDetail(
          (response as AdminOperationCourseChapterDetailResponse) ||
            EMPTY_CHAPTER_DETAIL,
        );
      })
      .catch(err => {
        if (!isActive) {
          return;
        }
        const message =
          err instanceof ErrorWithCode || err instanceof Error
            ? err.message
            : t('common.core.unknownError');
        fail(message);
        setSelectedChapter(null);
      })
      .finally(() => {
        if (isActive) {
          setChapterDetailLoading(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, [selectedChapter?.outline_item_bid, shifuBid, t]);

  const startChapterColumnResize = useCallback(
    (key: ChapterColumnKey, clientX: number) => {
      chapterColumnResizeRef.current = {
        key,
        startX: clientX,
        startWidth: chapterColumnWidths[key],
      };
      manualChapterResizeRef.current[key] = true;
    },
    [chapterColumnWidths],
  );

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const info = chapterColumnResizeRef.current;
      if (!info) {
        return;
      }
      const delta = event.clientX - info.startX;
      const nextWidth = clampChapterWidth(info.startWidth + delta);
      setChapterColumnWidths(prev => {
        if (Math.abs(prev[info.key] - nextWidth) < 0.5) {
          return prev;
        }
        return { ...prev, [info.key]: nextWidth };
      });
    };

    const handleMouseUp = () => {
      if (chapterColumnResizeRef.current) {
        persistManualChapterColumnWidths(
          chapterColumnWidthsRef.current,
          manualChapterResizeRef.current,
        );
      }
      chapterColumnResizeRef.current = null;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  const getChapterColumnStyle = useCallback(
    (key: ChapterColumnKey) => {
      const width = chapterColumnWidths[key];
      return {
        width,
        minWidth: width,
        maxWidth: width,
      };
    },
    [chapterColumnWidths],
  );

  const estimateChapterColumnWidth = useCallback(
    (text: string, multiplier = 7) => {
      if (!text) {
        return CHAPTER_COLUMN_MIN_WIDTH;
      }
      return text.length * multiplier + 24;
    },
    [],
  );

  const autoAdjustChapterColumns = useCallback(
    (rows: FlattenedChapterRow[]) => {
      if (!rows.length) {
        setChapterColumnWidths(prev => {
          const next = { ...prev };
          CHAPTER_COLUMN_KEYS.forEach(key => {
            if (!manualChapterResizeRef.current[key]) {
              next[key] = CHAPTER_COLUMN_DEFAULT_WIDTHS[key];
            }
          });
          const changed = CHAPTER_COLUMN_KEYS.some(
            key => Math.abs(next[key] - prev[key]) > 0.5,
          );
          return changed ? next : prev;
        });
        return;
      }

      const nextWidths: Partial<Record<ChapterColumnKey, number>> = {};
      const columnValueExtractors: Record<
        ChapterColumnKey,
        (chapter: FlattenedChapterRow) => string[]
      > = {
        position: chapter => [chapter.position],
        name: chapter => [
          chapter.title,
          chapter.node_type,
          ' '.repeat(chapter.depth),
        ],
        learningPermission: chapter => [
          resolveLearningPermissionLabel(chapter.learning_permission),
        ],
        visibility: chapter => [
          chapter.is_visible
            ? tOperations('detail.visibility.visible')
            : tOperations('detail.visibility.hidden'),
        ],
        contentStatus: chapter => [
          resolveContentStatusLabel(chapter.content_status),
        ],
        modifier: chapter => {
          const modifier = resolveModifierDisplay(chapter);
          return [modifier.primary, modifier.secondary];
        },
        contentDetail: () => [tOperations('detail.chaptersTable.detailAction')],
        followUpCount: chapter => [formatCount(chapter.follow_up_count)],
        ratingCount: chapter => [formatCount(chapter.rating_count)],
        chapterId: chapter => [chapter.outline_item_bid],
        updatedAt: chapter => [chapter.updated_at],
      };

      const multiplierMap: Partial<Record<ChapterColumnKey, number>> = {
        position: 5,
        name: 8,
        learningPermission: 6,
        visibility: 6,
        contentStatus: 6,
        modifier: 5.2,
        contentDetail: 5,
        followUpCount: 5,
        ratingCount: 5,
        chapterId: 5,
        updatedAt: 5,
      };

      rows.forEach(chapter => {
        CHAPTER_COLUMN_KEYS.forEach(key => {
          const texts = columnValueExtractors[key](chapter).filter(Boolean);
          if (!texts.length) {
            return;
          }
          const required = texts.reduce(
            (maxWidth, text) =>
              Math.max(
                maxWidth,
                estimateChapterColumnWidth(text, multiplierMap[key] ?? 7),
              ),
            Number(CHAPTER_COLUMN_DEFAULT_WIDTHS[key]),
          );
          if (
            !nextWidths[key] ||
            required > (nextWidths[key] ?? CHAPTER_COLUMN_MIN_WIDTH)
          ) {
            nextWidths[key] = required;
          }
        });
      });

      setChapterColumnWidths(prev => {
        const next = { ...prev };
        CHAPTER_COLUMN_KEYS.forEach(key => {
          if (!manualChapterResizeRef.current[key]) {
            next[key] = clampChapterWidth(
              nextWidths[key] ?? CHAPTER_COLUMN_DEFAULT_WIDTHS[key],
            );
          }
        });
        const changed = CHAPTER_COLUMN_KEYS.some(
          key => Math.abs(next[key] - prev[key]) > 0.5,
        );
        return changed ? next : prev;
      });
    },
    [
      estimateChapterColumnWidth,
      resolveContentStatusLabel,
      resolveLearningPermissionLabel,
      resolveModifierDisplay,
      tOperations,
    ],
  );

  const renderChapterResizeHandle = (key: ChapterColumnKey) => (
    <span
      className='absolute right-0 top-0 h-full w-2 cursor-col-resize select-none'
      onMouseDown={event => {
        event.preventDefault();
        startChapterColumnResize(key, event.clientX);
      }}
      aria-hidden='true'
    />
  );

  const basicInfoItems = useMemo(
    () => [
      {
        label: tOperations('detail.fields.courseName'),
        value: detail.basic_info.course_name || emptyValue,
      },
      {
        label: tOperations('detail.fields.courseId'),
        value: detail.basic_info.shifu_bid || shifuBid || emptyValue,
      },
      {
        label: tOperations('detail.fields.status'),
        value: (
          <span className='font-medium text-foreground'>
            {resolveCourseStatusLabel(detail.basic_info.course_status)}
          </span>
        ),
      },
      {
        label: tOperations('detail.fields.creator'),
        value: (
          <div className='space-y-0.5'>
            <div className='font-medium text-foreground'>
              {creatorDisplay.primary}
            </div>
            {creatorDisplay.secondary ? (
              <div className='text-xs text-muted-foreground'>
                {creatorDisplay.secondary}
              </div>
            ) : null}
          </div>
        ),
      },
      {
        label: tOperations('detail.fields.createdAt'),
        value: detail.basic_info.created_at || emptyValue,
      },
      {
        label: tOperations('detail.fields.updatedAt'),
        value: detail.basic_info.updated_at || emptyValue,
      },
    ],
    [
      creatorDisplay.primary,
      creatorDisplay.secondary,
      detail.basic_info.course_name,
      detail.basic_info.course_status,
      detail.basic_info.created_at,
      detail.basic_info.shifu_bid,
      detail.basic_info.updated_at,
      emptyValue,
      resolveCourseStatusLabel,
      shifuBid,
      tOperations,
    ],
  );

  useEffect(() => {
    autoAdjustChapterColumns(chapterRows);
  }, [autoAdjustChapterColumns, chapterRows]);

  if (!isReady) {
    return <Loading />;
  }

  if (loading && !detail.basic_info.shifu_bid) {
    return <Loading />;
  }

  if (error && !loading) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 500}
          errorMessage={error.message}
          onRetry={fetchDetail}
        />
      </div>
    );
  }

  return (
    <div className='h-full overflow-auto'>
      <div className='mx-auto max-w-6xl space-y-5 px-1 py-6'>
        <div className='flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between'>
          <h1 className='text-2xl font-semibold text-gray-900'>
            {tOperations('detail.title')}
          </h1>
          <Button
            variant='outline'
            className='sm:mr-3'
            onClick={() => router.push('/admin/operations')}
          >
            {tOperations('detail.back')}
          </Button>
        </div>

        <Card>
          <CardHeader className='pb-4'>
            <CardTitle className='text-base font-semibold tracking-normal'>
              {tOperations('detail.basicInfo')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className='grid gap-4 md:grid-cols-2 xl:grid-cols-3'>
              {basicInfoItems.map(item => (
                <div
                  key={item.label}
                  className='space-y-1'
                >
                  <dt className='text-sm text-muted-foreground'>
                    {item.label}
                  </dt>
                  <dd className='text-sm text-foreground'>{item.value}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className='pb-4'>
            <CardTitle className='text-base font-semibold tracking-normal'>
              {tOperations('detail.metrics')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6'>
              {metricCards.map(card => (
                <div
                  key={card.label}
                  className='rounded-lg border border-border/70 bg-muted/20 p-4'
                >
                  <div className='text-sm text-muted-foreground'>
                    {card.label}
                  </div>
                  <div className='mt-3 text-2xl font-semibold text-foreground'>
                    {card.value}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className='pb-4'>
            <CardTitle className='text-base font-semibold tracking-normal'>
              {tOperations('detail.chapters')}
            </CardTitle>
          </CardHeader>
          <CardContent className='pt-0'>
            <div className='overflow-auto rounded-xl border border-border bg-white shadow-sm'>
              <TooltipProvider delayDuration={150}>
                <Table className='table-auto'>
                  <TableHeader>
                    <TableRow>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('position')}
                      >
                        {tOperations('detail.chaptersTable.position')}
                        {renderChapterResizeHandle('position')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('name')}
                      >
                        {tOperations('detail.chaptersTable.name')}
                        {renderChapterResizeHandle('name')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('chapterId')}
                      >
                        {tOperations('detail.chaptersTable.chapterId')}
                        {renderChapterResizeHandle('chapterId')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('learningPermission')}
                      >
                        {tOperations('detail.chaptersTable.learningPermission')}
                        {renderChapterResizeHandle('learningPermission')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('visibility')}
                      >
                        {tOperations('detail.chaptersTable.visibility')}
                        {renderChapterResizeHandle('visibility')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('contentStatus')}
                      >
                        {tOperations('detail.chaptersTable.contentStatus')}
                        {renderChapterResizeHandle('contentStatus')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('contentDetail')}
                      >
                        {tOperations('detail.chaptersTable.contentDetail')}
                        {renderChapterResizeHandle('contentDetail')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('modifier')}
                      >
                        {tOperations('detail.chaptersTable.modifier')}
                        {renderChapterResizeHandle('modifier')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('updatedAt')}
                      >
                        {tOperations('detail.chaptersTable.updatedAt')}
                        {renderChapterResizeHandle('updatedAt')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap border-l-2 border-l-border/80 border-r border-border bg-muted/80 text-center text-xs font-medium text-muted-foreground last:border-r-0'
                        style={getChapterColumnStyle('followUpCount')}
                      >
                        {tOperations('detail.chaptersTable.followUpCount')}
                        {renderChapterResizeHandle('followUpCount')}
                      </TableHead>
                      <TableHead
                        className='relative h-10 whitespace-nowrap bg-muted/80 text-center text-xs font-medium text-muted-foreground'
                        style={getChapterColumnStyle('ratingCount')}
                      >
                        {tOperations('detail.chaptersTable.ratingCount')}
                        {renderChapterResizeHandle('ratingCount')}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {chapterRows.length === 0 ? (
                      <TableEmpty colSpan={11}>
                        {tOperations('detail.chaptersTable.empty')}
                      </TableEmpty>
                    ) : (
                      chapterRows.map(chapter => {
                        const {
                          primary: modifierPrimary,
                          secondary: modifierSecondary,
                        } = resolveModifierDisplay(chapter);

                        return (
                          <TableRow key={chapter.outline_item_bid}>
                            <TableCell
                              className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/80 last:border-r-0'
                              style={getChapterColumnStyle('position')}
                            >
                              {chapter.position || emptyValue}
                            </TableCell>
                            <TableCell
                              className='py-2.5 border-r border-border last:border-r-0'
                              style={getChapterColumnStyle('name')}
                            >
                              <div
                                className='flex min-w-0 items-center justify-center gap-2'
                                style={{
                                  paddingLeft: `${chapter.depth * 20}px`,
                                }}
                              >
                                <Badge
                                  variant='outline'
                                  className='shrink-0 rounded-full border-border/60 bg-background px-1.5 py-0 text-[10px] font-medium text-muted-foreground'
                                >
                                  {resolveChapterTypeLabel(chapter.node_type)}
                                </Badge>
                                <OverflowTooltipText
                                  text={chapter.title || emptyValue}
                                  className='text-center text-sm font-medium text-foreground'
                                />
                              </div>
                            </TableCell>
                            <TableCell
                              className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                              style={getChapterColumnStyle('chapterId')}
                            >
                              <OverflowTooltipText
                                text={chapter.outline_item_bid || emptyValue}
                                className='mx-auto block max-w-[240px] font-mono text-[11px] text-muted-foreground/65'
                              />
                            </TableCell>
                            <TableCell
                              className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                              style={getChapterColumnStyle(
                                'learningPermission',
                              )}
                            >
                              {resolveLearningPermissionLabel(
                                chapter.learning_permission,
                              )}
                            </TableCell>
                            <TableCell
                              className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                              style={getChapterColumnStyle('visibility')}
                            >
                              {chapter.is_visible
                                ? tOperations('detail.visibility.visible')
                                : tOperations('detail.visibility.hidden')}
                            </TableCell>
                            <TableCell
                              className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                              style={getChapterColumnStyle('contentStatus')}
                            >
                              {resolveContentStatusLabel(
                                chapter.content_status,
                              )}
                            </TableCell>
                            <TableCell
                              className='py-2.5 whitespace-nowrap border-r border-border text-center last:border-r-0'
                              style={getChapterColumnStyle('contentDetail')}
                            >
                              <button
                                type='button'
                                className='text-sm text-primary transition-colors hover:text-primary/80'
                                onClick={() => setSelectedChapter(chapter)}
                              >
                                {tOperations(
                                  'detail.chaptersTable.detailAction',
                                )}
                              </button>
                            </TableCell>
                            <TableCell
                              className='py-2.5 border-r border-border text-center last:border-r-0'
                              style={getChapterColumnStyle('modifier')}
                            >
                              <div className='flex flex-col gap-0.5 leading-tight'>
                                <OverflowTooltipText
                                  text={modifierPrimary}
                                  className='text-sm text-foreground'
                                />
                                {modifierSecondary ? (
                                  <OverflowTooltipText
                                    text={modifierSecondary}
                                    className='text-xs text-muted-foreground'
                                  />
                                ) : null}
                              </div>
                            </TableCell>
                            <TableCell
                              className='py-2.5 whitespace-nowrap border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                              style={getChapterColumnStyle('updatedAt')}
                            >
                              <OverflowTooltipText
                                text={chapter.updated_at || emptyValue}
                                className='mx-auto block max-w-full'
                              />
                            </TableCell>
                            <TableCell
                              className='py-2.5 whitespace-nowrap border-l-2 border-l-border/80 border-r border-border text-center text-sm text-muted-foreground/75 last:border-r-0'
                              style={getChapterColumnStyle('followUpCount')}
                            >
                              {formatCount(chapter.follow_up_count)}
                            </TableCell>
                            <TableCell
                              className='py-2.5 whitespace-nowrap text-center text-sm text-muted-foreground/75'
                              style={getChapterColumnStyle('ratingCount')}
                            >
                              {formatCount(chapter.rating_count)}
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </TooltipProvider>
            </div>
          </CardContent>
        </Card>

        <Dialog
          open={Boolean(selectedChapter)}
          onOpenChange={open => {
            if (!open) {
              setSelectedChapter(null);
              setSelectedChapterDetail(EMPTY_CHAPTER_DETAIL);
            }
          }}
        >
          <DialogContent className={chapterDetailLayout.dialogClassName}>
            <DialogHeader className='border-b border-border px-6 py-4 pr-16'>
              <div className='flex items-center justify-between gap-4'>
                <DialogTitle>
                  {tOperations('detail.contentDetailDialog.title')}
                </DialogTitle>
                <DialogDescription className='sr-only'>
                  {selectedChapter?.title ||
                    tOperations('detail.contentDetailDialog.title')}
                </DialogDescription>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='gap-2'
                  onClick={handleCopyChapterDetail}
                  disabled={chapterDetailLoading || !selectedChapterCopyText}
                >
                  <Copy className='h-4 w-4' />
                  {tOperations('detail.contentDetailDialog.copy')}
                </Button>
              </div>
            </DialogHeader>
            <div className={chapterDetailLayout.bodyClassName}>
              {chapterDetailLoading ? (
                <div className='flex h-full min-h-[240px] items-center justify-center'>
                  <Loading />
                </div>
              ) : selectedChapterDetailSections.some(section =>
                  section.value.trim(),
                ) ? (
                <div className='space-y-5'>
                  {selectedChapterDetailSections.map(section => (
                    <section
                      key={section.label}
                      className='space-y-2'
                    >
                      <div className='text-sm font-medium text-foreground'>
                        {section.label}
                      </div>
                      <pre className='overflow-x-auto rounded-lg border border-border bg-muted/20 p-4 text-sm leading-6 text-foreground whitespace-pre-wrap break-words'>
                        {section.value.trim() ||
                          tOperations('detail.contentDetailDialog.empty')}
                      </pre>
                    </section>
                  ))}
                </div>
              ) : (
                <div className='flex h-full min-h-[240px] items-center justify-center text-sm text-muted-foreground'>
                  {tOperations('detail.contentDetailDialog.empty')}
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
