'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp, Copy, X } from 'lucide-react';
import api from '@/api';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import { useToast } from '@/hooks/useToast';
import { copyText } from '@/c-utils/textutils';
import { ErrorWithCode } from '@/lib/request';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { cn } from '@/lib/utils';
import { isValidEmail } from '@/lib/validators';
import { buildAdminOperationsCourseDetailUrl } from './operation-course-routes';
import type {
  AdminOperationCourseItem,
  AdminOperationCourseListResponse,
  AdminOperationCourseOverview,
  AdminOperationCoursePromptResponse,
} from './operation-course-types';
import useOperatorGuard from './useOperatorGuard';

type CourseFilters = {
  shifu_bid: string;
  course_name: string;
  creator_keyword: string;
  course_status: string;
  start_time: string;
  end_time: string;
  updated_start_time: string;
  updated_end_time: string;
};

type CourseQuickFilterKey =
  | ''
  | 'draft'
  | 'published'
  | 'created_last_7d'
  | 'learning_active_30d'
  | 'paid_order_30d';

type ErrorState = { message: string; code?: number };

const PAGE_SIZE = 20;
const ALL_OPTION_VALUE = '__all__';
const COURSE_STATUS_PUBLISHED = 'published';
const COURSE_STATUS_UNPUBLISHED = 'unpublished';
const COURSE_QUICK_FILTER_DRAFT = 'draft';
const COURSE_QUICK_FILTER_PUBLISHED = 'published';
const COURSE_QUICK_FILTER_CREATED_LAST_7D = 'created_last_7d';
const COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D = 'learning_active_30d';
const COURSE_QUICK_FILTER_PAID_ORDER_30D = 'paid_order_30d';
const COLUMN_MIN_WIDTH = 80;
const COLUMN_MAX_WIDTH = 360;
const COLUMN_WIDTH_STORAGE_KEY = 'adminOperationsColumnWidths';
const DEFAULT_COLUMN_WIDTHS = {
  courseId: 260,
  courseName: 220,
  status: 110,
  price: 90,
  model: 170,
  coursePrompt: 120,
  creator: 170,
  modifier: 170,
  updatedAt: 170,
  createdAt: 170,
  action: 115,
} as const;
type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;
const COLUMN_KEYS = Object.keys(DEFAULT_COLUMN_WIDTHS) as ColumnKey[];
const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';
const TRANSFER_PHONE_PATTERN = /^\d{11}$/;
const EMPTY_STATE_LABEL = '--';
const EMPTY_COURSE_OVERVIEW: AdminOperationCourseOverview = {
  total_course_count: 0,
  draft_course_count: 0,
  published_course_count: 0,
  created_last_7d_course_count: 0,
  learning_active_30d_course_count: 0,
  paid_order_30d_course_count: 0,
};
const TABLE_INLINE_ACTION_BUTTON_CLASS =
  'inline-flex h-8 items-center justify-center rounded-md px-2.5 text-sm font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2';
const COLLAPSED_TEXT_STYLE: CSSProperties = {
  display: '-webkit-box',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 6,
  overflow: 'hidden',
};

type TransferContactType = 'email' | 'phone';

const createDefaultFilters = (): CourseFilters => ({
  shifu_bid: '',
  course_name: '',
  creator_keyword: '',
  course_status: '',
  start_time: '',
  end_time: '',
  updated_start_time: '',
  updated_end_time: '',
});

const formatLocalDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const buildCreatedLast7DaysFilters = (): Pick<
  CourseFilters,
  'start_time' | 'end_time'
> => {
  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setDate(endDate.getDate() - 6);
  return {
    start_time: formatLocalDate(startDate),
    end_time: formatLocalDate(endDate),
  };
};

const normalizeTransferIdentifier = (
  contactType: TransferContactType,
  value: string,
): string => {
  const trimmed = value.trim();
  return contactType === 'email' ? trimmed.toLowerCase() : trimmed;
};

const isValidTransferIdentifier = (
  contactType: TransferContactType,
  value: string,
): boolean => {
  if (!value) {
    return false;
  }
  if (contactType === 'email') {
    return isValidEmail(value);
  }
  return TRANSFER_PHONE_PATTERN.test(value);
};

const renderTooltipText = (text?: string, className?: string) => {
  return (
    <AdminTooltipText
      text={text}
      emptyValue={EMPTY_STATE_LABEL}
      className={className}
    />
  );
};

const formatCount = (value: number): string =>
  Number.isFinite(value) ? value.toLocaleString() : EMPTY_STATE_LABEL;

type ClearableTextInputProps = {
  value: string;
  placeholder: string;
  clearLabel: string;
  onChange: (value: string) => void;
};

const ClearableTextInput = ({
  value,
  placeholder,
  clearLabel,
  onChange,
}: ClearableTextInputProps) => {
  const hasValue = value.trim().length > 0;

  return (
    <div className='relative'>
      <Input
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className={cn('h-9', hasValue && 'pr-9')}
      />
      {hasValue ? (
        <button
          type='button'
          aria-label={clearLabel}
          className='absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground'
          onMouseDown={event => event.preventDefault()}
          onClick={() => onChange('')}
        >
          <X className='h-3.5 w-3.5' />
        </button>
      ) : null}
    </div>
  );
};

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.operationsCourse.title')
 * t('module.operationsCourse.emptyList')
 * t('module.operationsCourse.actions.transferCreator')
 * t('module.operationsCourse.detail.title')
 * t('module.operationsCourse.detail.back')
 * t('module.operationsCourse.detail.basicInfo')
 * t('module.operationsCourse.filters.courseId')
 * t('module.operationsCourse.filters.courseName')
 * t('module.operationsCourse.filters.creator')
 * t('module.operationsCourse.filters.creatorEmailOrUserBid')
 * t('module.operationsCourse.filters.creatorMobileOrUserBid')
 * t('module.operationsCourse.filters.status')
 * t('module.operationsCourse.filters.createdAt')
 * t('module.operationsCourse.filters.startTime')
 * t('module.operationsCourse.filters.endTime')
 * t('module.operationsCourse.statusLabels.published')
 * t('module.operationsCourse.statusLabels.unpublished')
 * t('module.operationsCourse.overview.title')
 * t('module.operationsCourse.overview.metrics.totalCourses')
 * t('module.operationsCourse.overview.metrics.draftCourses')
 * t('module.operationsCourse.overview.metrics.publishedCourses')
 * t('module.operationsCourse.overview.metrics.createdLast7d')
 * t('module.operationsCourse.overview.metrics.learningActive30d')
 * t('module.operationsCourse.overview.metrics.ordered30d')
 * t('module.operationsCourse.overview.tooltips.totalCourses')
 * t('module.operationsCourse.overview.tooltips.draftCourses')
 * t('module.operationsCourse.overview.tooltips.publishedCourses')
 * t('module.operationsCourse.overview.tooltips.createdLast7d')
 * t('module.operationsCourse.overview.tooltips.learningActive30d')
 * t('module.operationsCourse.overview.tooltips.ordered30d')
 * t('module.operationsCourse.overview.activeFilter')
 * t('module.operationsCourse.table.courseName')
 * t('module.operationsCourse.table.courseId')
 * t('module.operationsCourse.table.status')
 * t('module.operationsCourse.table.price')
 * t('module.operationsCourse.table.model')
 * t('module.operationsCourse.table.coursePrompt')
 * t('module.operationsCourse.table.detailAction')
 * t('module.operationsCourse.table.creator')
 * t('module.operationsCourse.table.modifier')
 * t('module.operationsCourse.table.updatedAt')
 * t('module.operationsCourse.table.createdAt')
 * t('module.operationsCourse.table.action')
 * t('module.operationsCourse.coursePromptDialog.title')
 * t('module.operationsCourse.coursePromptDialog.copy')
 * t('module.operationsCourse.coursePromptDialog.copySuccess')
 * t('module.operationsCourse.coursePromptDialog.copyFailed')
 * t('module.operationsCourse.coursePromptDialog.empty')
 * t('module.operationsCourse.transferCreatorDialog.title')
 * t('module.operationsCourse.transferCreatorDialog.description')
 * t('module.operationsCourse.transferCreatorDialog.currentCreator')
 * t('module.operationsCourse.transferCreatorDialog.contactType')
 * t('module.operationsCourse.transferCreatorDialog.contactTypeEmail')
 * t('module.operationsCourse.transferCreatorDialog.contactTypePhone')
 * t('module.operationsCourse.transferCreatorDialog.identifier')
 * t('module.operationsCourse.transferCreatorDialog.contactPlaceholderEmail')
 * t('module.operationsCourse.transferCreatorDialog.contactPlaceholderPhone')
 * t('module.operationsCourse.transferCreatorDialog.identifierRequired')
 * t('module.operationsCourse.transferCreatorDialog.sameCreator')
 * t('module.operationsCourse.transferCreatorDialog.confirm')
 * t('module.operationsCourse.transferCreatorDialog.submitSuccess')
 * t('module.operationsCourse.transferCreatorDialog.confirmTitle')
 * t('module.operationsCourse.transferCreatorDialog.confirmDescriptionPrefix')
 * t('module.operationsCourse.transferCreatorDialog.confirmDescriptionCourseSuffix')
 * t('module.operationsCourse.transferCreatorDialog.confirmDescriptionTargetPrefix')
 */
const OperationsPage = () => {
  const router = useRouter();
  const { t } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');
  const { toast } = useToast();
  const { isInitialized, isGuest, isReady } = useOperatorGuard();
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const currencySymbol = useEnvStore(
    (state: EnvStoreState) => state.currencySymbol,
  );

  const contactType = useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const transferContactOptions = useMemo<TransferContactType[]>(() => {
    const methods = loginMethodsEnabled || [];
    const normalizedMethods = methods
      .map(method => method.trim().toLowerCase())
      .filter(Boolean);
    const options: TransferContactType[] = [];
    if (normalizedMethods.includes('phone')) {
      options.push('phone');
    }
    if (
      normalizedMethods.includes('email') ||
      normalizedMethods.includes('google')
    ) {
      options.push('email');
    }
    if (options.length === 0) {
      options.push(contactType);
    }
    return Array.from(new Set(options));
  }, [contactType, loginMethodsEnabled]);
  const defaultTransferContactType = useMemo<TransferContactType>(() => {
    if (transferContactOptions.includes('phone')) {
      return 'phone';
    }
    if (transferContactOptions.includes('email')) {
      return 'email';
    }
    if (transferContactOptions.includes(contactType)) {
      return contactType;
    }
    return transferContactOptions[0] || 'phone';
  }, [contactType, transferContactOptions]);
  const isEmailMode = contactType === 'email';
  const creatorPlaceholder = useMemo(
    () =>
      isEmailMode
        ? tOperations('filters.creatorEmailOrUserBid')
        : tOperations('filters.creatorMobileOrUserBid'),
    [isEmailMode, tOperations],
  );
  const clearLabel = useMemo(
    () => t('module.chat.lessonFeedbackClearInput'),
    [t],
  );
  const statusOptions = useMemo(
    () => [
      {
        value: COURSE_STATUS_PUBLISHED,
        label: tOperations('statusLabels.published'),
      },
      {
        value: COURSE_STATUS_UNPUBLISHED,
        label: tOperations('statusLabels.unpublished'),
      },
    ],
    [tOperations],
  );

  const [courses, setCourses] = useState<AdminOperationCourseItem[]>([]);
  const [courseOverview, setCourseOverview] =
    useState<AdminOperationCourseOverview>(EMPTY_COURSE_OVERVIEW);
  const [filters, setFilters] = useState<CourseFilters>(createDefaultFilters);
  const [quickFilter, setQuickFilter] = useState<CourseQuickFilterKey>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [expanded, setExpanded] = useState(false);
  const [coursePromptExpanded, setCoursePromptExpanded] = useState(false);
  const [promptDetailCourse, setPromptDetailCourse] =
    useState<AdminOperationCourseItem | null>(null);
  const [promptDetailText, setPromptDetailText] = useState('');
  const [promptDetailLoading, setPromptDetailLoading] = useState(false);
  const [promptDetailError, setPromptDetailError] = useState('');
  const [canTogglePromptDetail, setCanTogglePromptDetail] = useState(false);
  const [transferDialogOpen, setTransferDialogOpen] = useState(false);
  const [transferTargetCourse, setTransferTargetCourse] =
    useState<AdminOperationCourseItem | null>(null);
  const [transferContactType, setTransferContactType] =
    useState<TransferContactType>(defaultTransferContactType);
  const [transferIdentifier, setTransferIdentifier] = useState('');
  const [transferLoading, setTransferLoading] = useState(false);
  const [transferError, setTransferError] = useState('');
  const [transferConfirmOpen, setTransferConfirmOpen] = useState(false);
  const requestedPageRef = useRef(1);
  const requestIdRef = useRef(0);
  const promptRequestIdRef = useRef(0);
  const promptDetailContentRef = useRef<HTMLDivElement | null>(null);
  const fetchCoursesRef = useRef<
    | ((
        targetPage: number,
        nextFilters?: CourseFilters,
        nextQuickFilter?: CourseQuickFilterKey,
      ) => Promise<void>)
    | undefined
  >(undefined);
  const {
    setColumnWidths,
    getColumnStyle,
    getResizeHandleProps,
    isManualColumn,
    clampWidth,
  } = useAdminResizableColumns<ColumnKey>({
    storageKey: COLUMN_WIDTH_STORAGE_KEY,
    defaultWidths: DEFAULT_COLUMN_WIDTHS,
    minWidth: COLUMN_MIN_WIDTH,
    maxWidth: COLUMN_MAX_WIDTH,
  });

  const formatMoney = useCallback(
    (value?: string) =>
      `${currencySymbol || ''}${value && value.trim() ? value : '0'}`,
    [currencySymbol],
  );
  const defaultUserName = useMemo(() => t('module.user.defaultUserName'), [t]);
  const displayStatusValue = filters.course_status || ALL_OPTION_VALUE;
  const hasPromptDetailText = promptDetailText.trim().length > 0;

  useEffect(() => {
    if (promptDetailLoading || promptDetailError || !hasPromptDetailText) {
      setCanTogglePromptDetail(false);
      return;
    }
    if (coursePromptExpanded) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      const container = promptDetailContentRef.current;
      if (!container) {
        setCanTogglePromptDetail(false);
        return;
      }
      setCanTogglePromptDetail(
        container.scrollHeight > container.clientHeight ||
          container.scrollWidth > container.clientWidth,
      );
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [
    coursePromptExpanded,
    hasPromptDetailText,
    promptDetailError,
    promptDetailLoading,
    promptDetailText,
  ]);

  const handleCopyCoursePrompt = useCallback(async () => {
    if (!hasPromptDetailText || promptDetailLoading || promptDetailError) {
      return;
    }

    try {
      await copyText(promptDetailText);
      toast({
        title: tOperations('coursePromptDialog.copySuccess'),
      });
    } catch {
      toast({
        title: tOperations('coursePromptDialog.copyFailed'),
        variant: 'destructive',
      });
    }
  }, [
    hasPromptDetailText,
    promptDetailError,
    promptDetailLoading,
    promptDetailText,
    tOperations,
    toast,
  ]);

  const fetchCourses = useCallback(
    async (
      targetPage: number,
      nextFilters?: CourseFilters,
      nextQuickFilter?: CourseQuickFilterKey,
    ) => {
      const resolvedFilters = nextFilters ?? filters;
      const resolvedQuickFilter = nextQuickFilter ?? quickFilter;
      requestedPageRef.current = targetPage;
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getAdminOperationCourses({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          shifu_bid: resolvedFilters.shifu_bid.trim(),
          course_name: resolvedFilters.course_name.trim(),
          creator_keyword: resolvedFilters.creator_keyword.trim(),
          course_status: resolvedFilters.course_status,
          quick_filter: resolvedQuickFilter,
          start_time: resolvedFilters.start_time,
          end_time: resolvedFilters.end_time,
          updated_start_time: resolvedFilters.updated_start_time,
          updated_end_time: resolvedFilters.updated_end_time,
        })) as AdminOperationCourseListResponse;
        if (requestId !== requestIdRef.current) {
          return;
        }
        setCourseOverview(response.summary ?? EMPTY_COURSE_OVERVIEW);
        setCourses(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 1);
      } catch (err) {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setCourseOverview(EMPTY_COURSE_OVERVIEW);
        setPageIndex(targetPage);
        if (err instanceof ErrorWithCode) {
          setError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setError({ message: err.message });
        } else {
          setError({ message: t('common.core.unknownError') });
        }
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [filters, quickFilter, t],
  );

  useEffect(() => {
    fetchCoursesRef.current = fetchCourses;
  }, [fetchCourses]);

  useEffect(() => {
    if (!isInitialized || isGuest || !isReady) {
      return;
    }
    fetchCoursesRef.current?.(1, createDefaultFilters(), '');
  }, [isGuest, isInitialized, isReady]);

  const clearQuickFilterIfConflicted = useCallback(
    (key: keyof CourseFilters, value: string) => {
      if (!quickFilter) {
        return;
      }
      if (
        quickFilter === COURSE_QUICK_FILTER_DRAFT ||
        quickFilter === COURSE_QUICK_FILTER_PUBLISHED
      ) {
        const expectedStatus =
          quickFilter === COURSE_QUICK_FILTER_DRAFT
            ? COURSE_STATUS_UNPUBLISHED
            : COURSE_STATUS_PUBLISHED;
        if (key === 'course_status' && value !== expectedStatus) {
          setQuickFilter('');
        }
        return;
      }
      if (quickFilter === COURSE_QUICK_FILTER_CREATED_LAST_7D) {
        const expected = buildCreatedLast7DaysFilters();
        if (
          (key === 'start_time' && value !== expected.start_time) ||
          (key === 'end_time' && value !== expected.end_time)
        ) {
          setQuickFilter('');
        }
      }
    },
    [quickFilter],
  );

  const handleFilterChange = (key: keyof CourseFilters, value: string) => {
    clearQuickFilterIfConflicted(key, value);
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const applyQuickFilter = useCallback(
    (targetQuickFilter: CourseQuickFilterKey) => {
      if (targetQuickFilter && targetQuickFilter === quickFilter) {
        const cleared = createDefaultFilters();
        setFilters(cleared);
        setQuickFilter('');
        fetchCourses(1, cleared, '');
        return;
      }

      const nextFilters = createDefaultFilters();
      if (targetQuickFilter === COURSE_QUICK_FILTER_DRAFT) {
        nextFilters.course_status = COURSE_STATUS_UNPUBLISHED;
      } else if (targetQuickFilter === COURSE_QUICK_FILTER_PUBLISHED) {
        nextFilters.course_status = COURSE_STATUS_PUBLISHED;
      } else if (targetQuickFilter === COURSE_QUICK_FILTER_CREATED_LAST_7D) {
        Object.assign(nextFilters, buildCreatedLast7DaysFilters());
      }

      setFilters(nextFilters);
      setQuickFilter(targetQuickFilter);
      fetchCourses(1, nextFilters, targetQuickFilter);
    },
    [fetchCourses, quickFilter],
  );

  const handleSearch = () => {
    fetchCourses(1, filters, quickFilter);
  };

  const handleReset = () => {
    const cleared = createDefaultFilters();
    setFilters(cleared);
    setQuickFilter('');
    fetchCourses(1, cleared, '');
  };

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > pageCount || nextPage === pageIndex) {
      return;
    }
    fetchCourses(nextPage, filters, quickFilter);
  };

  const handleDetailClick = (course: AdminOperationCourseItem) => {
    const detailUrl = buildAdminOperationsCourseDetailUrl(course.shifu_bid);
    if (!detailUrl) {
      return;
    }
    router.push(detailUrl);
  };

  const handlePromptDetailOpenChange = useCallback((nextOpen: boolean) => {
    if (!nextOpen) {
      promptRequestIdRef.current += 1;
      setPromptDetailCourse(null);
      setCoursePromptExpanded(false);
      setPromptDetailText('');
      setPromptDetailLoading(false);
      setPromptDetailError('');
      setCanTogglePromptDetail(false);
    }
  }, []);

  const handlePromptDetailClick = useCallback(
    async (course: AdminOperationCourseItem) => {
      if (!course.has_course_prompt) {
        return;
      }

      const requestId = promptRequestIdRef.current + 1;
      promptRequestIdRef.current = requestId;
      setPromptDetailCourse(course);
      setCoursePromptExpanded(false);
      setPromptDetailText('');
      setPromptDetailError('');
      setPromptDetailLoading(true);

      try {
        const response = (await api.getAdminOperationCoursePrompt({
          shifu_bid: course.shifu_bid,
        })) as AdminOperationCoursePromptResponse;
        if (requestId !== promptRequestIdRef.current) {
          return;
        }
        setPromptDetailText(response.course_prompt ?? '');
      } catch (err) {
        if (requestId !== promptRequestIdRef.current) {
          return;
        }
        if (err instanceof Error) {
          setPromptDetailError(err.message);
        } else {
          setPromptDetailError(t('common.core.unknownError'));
        }
      } finally {
        if (requestId === promptRequestIdRef.current) {
          setPromptDetailLoading(false);
        }
      }
    },
    [t],
  );

  const handleTransferDialogOpenChange = useCallback(
    (nextOpen: boolean) => {
      setTransferDialogOpen(nextOpen);
      if (nextOpen) {
        return;
      }
      setTransferTargetCourse(null);
      setTransferContactType(defaultTransferContactType);
      setTransferIdentifier('');
      setTransferError('');
      setTransferConfirmOpen(false);
      setTransferLoading(false);
    },
    [defaultTransferContactType],
  );

  const handleTransferCreatorClick = useCallback(
    (course: AdminOperationCourseItem) => {
      setTransferTargetCourse(course);
      setTransferContactType(defaultTransferContactType);
      setTransferIdentifier('');
      setTransferError('');
      setTransferConfirmOpen(false);
      setTransferLoading(false);
      setTransferDialogOpen(true);
    },
    [defaultTransferContactType],
  );

  const resolveCourseStatusLabel = useCallback(
    (courseStatus?: string) => {
      if (courseStatus === COURSE_STATUS_PUBLISHED) {
        return tOperations('statusLabels.published');
      }
      return tOperations('statusLabels.unpublished');
    },
    [tOperations],
  );

  const resolvePrimaryContact = useCallback(
    (
      user: Pick<
        AdminOperationCourseItem,
        'creator_mobile' | 'creator_email' | 'updater_mobile' | 'updater_email'
      >,
      kind: 'creator' | 'updater',
    ) => {
      if (kind === 'creator') {
        return isEmailMode ? user.creator_email : user.creator_mobile;
      }
      return isEmailMode ? user.updater_email : user.updater_mobile;
    },
    [isEmailMode],
  );

  const resolveActorDisplay = useCallback(
    (course: AdminOperationCourseItem, kind: 'creator' | 'updater') => {
      const userBid =
        kind === 'creator' ? course.creator_user_bid : course.updater_user_bid;
      if (userBid === 'system') {
        return {
          primary: 'system',
          secondary: '',
        };
      }

      const nickname =
        kind === 'creator' ? course.creator_nickname : course.updater_nickname;

      return {
        primary: resolvePrimaryContact(course, kind) || '',
        secondary: nickname || defaultUserName,
      };
    },
    [defaultUserName, resolvePrimaryContact],
  );

  const transferCreatorDisplay = useMemo(() => {
    if (!transferTargetCourse) {
      return { primary: '--', secondary: '' };
    }
    return resolveActorDisplay(transferTargetCourse, 'creator');
  }, [resolveActorDisplay, transferTargetCourse]);
  const transferCourseName = transferTargetCourse?.course_name?.trim() || '--';

  const normalizedTransferIdentifier = useMemo(
    () => normalizeTransferIdentifier(transferContactType, transferIdentifier),
    [transferContactType, transferIdentifier],
  );
  const transferCurrentCreatorIdentifier = useMemo(() => {
    if (!transferTargetCourse) {
      return '';
    }
    const currentIdentifier =
      transferContactType === 'email'
        ? transferTargetCourse.creator_email
        : transferTargetCourse.creator_mobile;
    return normalizeTransferIdentifier(transferContactType, currentIdentifier);
  }, [transferContactType, transferTargetCourse]);
  const transferIdentifierPlaceholder = useMemo(
    () =>
      transferContactType === 'email'
        ? tOperations('transferCreatorDialog.contactPlaceholderEmail')
        : tOperations('transferCreatorDialog.contactPlaceholderPhone'),
    [tOperations, transferContactType],
  );
  const transferHintText = useMemo(
    () => tOperations('transferCreatorDialog.description'),
    [tOperations],
  );
  const transferCurrentCreatorText = transferCurrentCreatorIdentifier || '--';
  const transferTargetCreatorText = normalizedTransferIdentifier || '--';

  useEffect(() => {
    if (!transferDialogOpen) {
      return;
    }
    if (!transferContactOptions.includes(transferContactType)) {
      setTransferContactType(defaultTransferContactType);
    }
  }, [
    defaultTransferContactType,
    transferContactOptions,
    transferContactType,
    transferDialogOpen,
  ]);

  const handleTransferSubmit = useCallback(() => {
    if (!transferTargetCourse) {
      return;
    }

    if (
      !isValidTransferIdentifier(
        transferContactType,
        normalizedTransferIdentifier,
      )
    ) {
      setTransferError(tOperations('transferCreatorDialog.identifierRequired'));
      return;
    }

    if (
      transferCurrentCreatorIdentifier &&
      normalizedTransferIdentifier === transferCurrentCreatorIdentifier
    ) {
      setTransferError(tOperations('transferCreatorDialog.sameCreator'));
      return;
    }

    setTransferError('');
    setTransferConfirmOpen(true);
  }, [
    normalizedTransferIdentifier,
    tOperations,
    transferContactType,
    transferCurrentCreatorIdentifier,
    transferTargetCourse,
  ]);

  const handleTransferConfirm = useCallback(async () => {
    if (!transferTargetCourse) {
      return;
    }

    setTransferConfirmOpen(false);
    setTransferError('');
    setTransferLoading(true);
    try {
      await api.transferAdminOperationCourseCreator({
        shifu_bid: transferTargetCourse.shifu_bid,
        contact_type: transferContactType,
        identifier: normalizedTransferIdentifier,
      });
      toast({
        title: tOperations('transferCreatorDialog.submitSuccess'),
      });
      handleTransferDialogOpenChange(false);
      await fetchCourses(requestedPageRef.current, filters, quickFilter);
    } catch (error) {
      setTransferError(
        error instanceof Error ? error.message : t('common.core.unknownError'),
      );
    } finally {
      setTransferLoading(false);
    }
  }, [
    fetchCourses,
    filters,
    handleTransferDialogOpenChange,
    normalizedTransferIdentifier,
    quickFilter,
    t,
    tOperations,
    toast,
    transferContactType,
    transferTargetCourse,
  ]);

  const estimateWidth = (text: string, multiplier = 7) => {
    if (!text) {
      return COLUMN_MIN_WIDTH;
    }
    const approx = text.length * multiplier + 16;
    return approx;
  };

  const overviewCards = useMemo(
    () => [
      {
        key: 'total',
        label: tOperations('overview.metrics.totalCourses'),
        value: courseOverview.total_course_count,
        tooltip: tOperations('overview.tooltips.totalCourses'),
        quickFilterKey: '' as CourseQuickFilterKey,
      },
      {
        key: 'draft',
        label: tOperations('overview.metrics.draftCourses'),
        value: courseOverview.draft_course_count,
        tooltip: tOperations('overview.tooltips.draftCourses'),
        quickFilterKey: COURSE_QUICK_FILTER_DRAFT as CourseQuickFilterKey,
      },
      {
        key: 'published',
        label: tOperations('overview.metrics.publishedCourses'),
        value: courseOverview.published_course_count,
        tooltip: tOperations('overview.tooltips.publishedCourses'),
        quickFilterKey: COURSE_QUICK_FILTER_PUBLISHED as CourseQuickFilterKey,
      },
      {
        key: 'created-last-7d',
        label: tOperations('overview.metrics.createdLast7d'),
        value: courseOverview.created_last_7d_course_count,
        tooltip: tOperations('overview.tooltips.createdLast7d'),
        quickFilterKey:
          COURSE_QUICK_FILTER_CREATED_LAST_7D as CourseQuickFilterKey,
      },
      {
        key: 'learning-30d',
        label: tOperations('overview.metrics.learningActive30d'),
        value: courseOverview.learning_active_30d_course_count,
        tooltip: tOperations('overview.tooltips.learningActive30d'),
        quickFilterKey:
          COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D as CourseQuickFilterKey,
      },
      {
        key: 'orders-30d',
        label: tOperations('overview.metrics.ordered30d'),
        value: courseOverview.paid_order_30d_course_count,
        tooltip: tOperations('overview.tooltips.ordered30d'),
        quickFilterKey:
          COURSE_QUICK_FILTER_PAID_ORDER_30D as CourseQuickFilterKey,
      },
    ],
    [courseOverview, tOperations],
  );

  const activeQuickFilterCard = useMemo(() => {
    if (!quickFilter) {
      return null;
    }
    return (
      overviewCards.find(card => card.quickFilterKey === quickFilter) ?? null
    );
  }, [overviewCards, quickFilter]);

  const collapsedFilterItems = [
    {
      key: 'shifu_bid',
      label: tOperations('filters.courseId'),
      component: (
        <ClearableTextInput
          value={filters.shifu_bid}
          onChange={value => handleFilterChange('shifu_bid', value)}
          placeholder={tOperations('filters.courseId')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'course_name',
      label: tOperations('filters.courseName'),
      component: (
        <ClearableTextInput
          value={filters.course_name}
          onChange={value => handleFilterChange('course_name', value)}
          placeholder={tOperations('filters.courseName')}
          clearLabel={clearLabel}
        />
      ),
    },
  ];

  const expandedPrimaryFilterItems = [
    ...collapsedFilterItems,
    {
      key: 'creator_keyword',
      label: tOperations('filters.creator'),
      component: (
        <ClearableTextInput
          value={filters.creator_keyword}
          onChange={value => handleFilterChange('creator_keyword', value)}
          placeholder={creatorPlaceholder}
          clearLabel={clearLabel}
        />
      ),
    },
  ];

  const expandedSecondaryFilterItems = [
    {
      key: 'course_status',
      label: tOperations('filters.status'),
      component: (
        <Select
          value={displayStatusValue}
          onValueChange={value =>
            handleFilterChange(
              'course_status',
              value === ALL_OPTION_VALUE ? '' : value,
            )
          }
        >
          <SelectTrigger className='h-9'>
            <SelectValue placeholder={tOperations('filters.status')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={ALL_OPTION_VALUE}
              className={SINGLE_SELECT_ITEM_CLASS}
            >
              {t('common.core.all')}
            </SelectItem>
            {statusOptions.map(option => (
              <SelectItem
                key={option.value}
                value={option.value}
                className={SINGLE_SELECT_ITEM_CLASS}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'created_date_range',
      label: tOperations('filters.createdAt'),
      component: (
        <AdminDateRangeFilter
          startValue={filters.start_time}
          endValue={filters.end_time}
          onChange={range => {
            handleFilterChange('start_time', range.start);
            handleFilterChange('end_time', range.end);
          }}
          placeholder={`${tOperations('filters.startTime')} ~ ${tOperations('filters.endTime')}`}
          resetLabel={t('module.order.filters.reset')}
          clearLabel={clearLabel}
        />
      ),
    },
    {
      key: 'updated_date_range',
      label: tOperations('table.updatedAt'),
      component: (
        <AdminDateRangeFilter
          startValue={filters.updated_start_time}
          endValue={filters.updated_end_time}
          onChange={range => {
            handleFilterChange('updated_start_time', range.start);
            handleFilterChange('updated_end_time', range.end);
          }}
          placeholder={`${tOperations('filters.startTime')} ~ ${tOperations('filters.endTime')}`}
          resetLabel={t('module.order.filters.reset')}
          clearLabel={clearLabel}
        />
      ),
    },
  ];

  const autoAdjustColumns = useCallback(
    (items: AdminOperationCourseItem[]) => {
      if (!items || items.length === 0) {
        setColumnWidths(prev => {
          const next = { ...prev };
          COLUMN_KEYS.forEach(key => {
            if (!isManualColumn(key)) {
              next[key] = DEFAULT_COLUMN_WIDTHS[key];
            }
          });
          const changed = COLUMN_KEYS.some(
            key => Math.abs(next[key] - prev[key]) > 0.5,
          );
          if (!changed) {
            return prev;
          }
          return next;
        });
        return;
      }

      const nextWidths: Partial<Record<ColumnKey, number>> = {};
      const columnValueExtractors: Record<
        ColumnKey,
        (course: AdminOperationCourseItem) => string[]
      > = {
        courseName: course => [course.course_name],
        courseId: course => [course.shifu_bid],
        status: course => [resolveCourseStatusLabel(course.course_status)],
        price: course => [formatMoney(course.price)],
        model: course => [course.course_model],
        coursePrompt: course => [
          course.has_course_prompt
            ? tOperations('table.detailAction')
            : EMPTY_STATE_LABEL,
        ],
        creator: course => [
          resolveActorDisplay(course, 'creator').primary,
          resolveActorDisplay(course, 'creator').secondary,
        ],
        modifier: course => [
          resolveActorDisplay(course, 'updater').primary,
          resolveActorDisplay(course, 'updater').secondary,
        ],
        updatedAt: course => [course.updated_at],
        createdAt: course => [course.created_at],
        action: () => [t('common.core.more')],
      };

      items.forEach(course => {
        COLUMN_KEYS.forEach(key => {
          const texts = columnValueExtractors[key](course).filter(Boolean);
          if (texts.length === 0) {
            return;
          }
          const multiplierMap: Partial<Record<ColumnKey, number>> = {
            courseName: 4.5,
            courseId: 5,
            status: 5,
            price: 4,
            model: 4.2,
            coursePrompt: 5.5,
            creator: 4.6,
            modifier: 4.6,
            updatedAt: 4.8,
            createdAt: 4.8,
            action: 4.2,
          };
          const multiplier = multiplierMap[key] ?? 7;
          const required = texts.reduce(
            (maxWidth, text) =>
              Math.max(maxWidth, estimateWidth(text, multiplier)),
            Number(DEFAULT_COLUMN_WIDTHS[key]),
          );
          if (
            !nextWidths[key] ||
            required > (nextWidths[key] ?? COLUMN_MIN_WIDTH)
          ) {
            nextWidths[key] = required;
          }
        });
      });

      setColumnWidths(prev => {
        const updated = { ...prev };
        COLUMN_KEYS.forEach(key => {
          if (isManualColumn(key)) {
            return;
          }
          const fallback = DEFAULT_COLUMN_WIDTHS[key];
          const calculated = nextWidths[key] ?? fallback;
          updated[key] = clampWidth(calculated);
        });
        const changed = COLUMN_KEYS.some(
          key => Math.abs(updated[key] - prev[key]) > 0.5,
        );
        if (!changed) {
          return prev;
        }
        return updated;
      });
    },
    [
      clampWidth,
      formatMoney,
      isManualColumn,
      resolveActorDisplay,
      resolveCourseStatusLabel,
      setColumnWidths,
      t,
      tOperations,
    ],
  );

  const renderResizeHandle = (key: ColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getResizeHandleProps(key)}
    />
  );

  useEffect(() => {
    autoAdjustColumns(courses);
  }, [autoAdjustColumns, courses]);

  if (!isReady) {
    return <Loading />;
  }

  if (error) {
    return (
      <div className='h-full p-0'>
        <ErrorDisplay
          errorCode={error.code || 0}
          errorMessage={error.message}
          onRetry={() =>
            fetchCourses(requestedPageRef.current, filters, quickFilter)
          }
        />
      </div>
    );
  }

  return (
    <div
      className='h-full p-0'
      data-testid='admin-operations-page'
    >
      <div className='max-w-7xl mx-auto h-full overflow-hidden flex flex-col'>
        <div
          className='mb-5'
          data-testid='admin-operations-header'
        >
          <h1 className='text-2xl font-semibold text-gray-900'>
            {tOperations('title')}
          </h1>
        </div>

        <div className='mb-5 rounded-xl border border-border bg-white p-4 shadow-sm'>
          <div className='mb-3'>
            <h2 className='text-base font-semibold text-foreground'>
              {tOperations('overview.title')}
            </h2>
          </div>
          <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-3 min-[1680px]:grid-cols-6'>
            {overviewCards.map(card => {
              const isActive = card.quickFilterKey
                ? quickFilter === card.quickFilterKey
                : !quickFilter;

              return (
                <button
                  type='button'
                  key={card.key}
                  className={cn(
                    'rounded-lg border px-3.5 py-2.5 text-left transition-colors',
                    isActive
                      ? 'border-primary bg-primary/5'
                      : 'border-border bg-muted/20 hover:bg-muted/40',
                  )}
                  onClick={() => applyQuickFilter(card.quickFilterKey)}
                >
                  <div className='flex items-center gap-1 text-sm text-muted-foreground'>
                    <span>{card.label}</span>
                    <TooltipProvider delayDuration={0}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span
                            aria-label={card.tooltip}
                            className='inline-flex h-4 w-4 items-center justify-center text-muted-foreground'
                            onClick={event => event.stopPropagation()}
                          >
                            <QuestionMarkCircleIcon className='h-4 w-4' />
                          </span>
                        </TooltipTrigger>
                        <TooltipContent className='max-w-56 text-left leading-5'>
                          {card.tooltip}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                  <div className='mt-1.5 text-[2rem] font-semibold leading-none text-foreground'>
                    {formatCount(card.value)}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div
          className='rounded-xl border border-border bg-white p-4 mb-5 shadow-sm transition-all'
          data-testid='admin-operations-filters'
        >
          <div className='space-y-4'>
            {activeQuickFilterCard ? (
              <div className='flex flex-wrap items-center gap-2'>
                <span className='text-sm text-muted-foreground'>
                  {tOperations('overview.activeFilter')}
                </span>
                <button
                  type='button'
                  aria-label={`${activeQuickFilterCard.label} ${clearLabel}`}
                  className='inline-flex items-center gap-1 rounded-full border border-border bg-muted/30 px-3 py-1 text-sm text-foreground transition-colors hover:bg-muted'
                  onClick={() => applyQuickFilter('')}
                >
                  <span>{activeQuickFilterCard.label}</span>
                  <X className='h-3.5 w-3.5' />
                </button>
              </div>
            ) : null}
            <div
              className={cn(
                'grid gap-4',
                expanded
                  ? 'grid-cols-1 xl:grid-cols-3'
                  : 'grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]',
              )}
            >
              {(expanded
                ? expandedPrimaryFilterItems
                : collapsedFilterItems
              ).map(item => (
                <div
                  key={item.key}
                  className='flex items-center'
                >
                  <span
                    className={cn(
                      "shrink-0 mr-2 text-sm font-medium text-foreground whitespace-nowrap text-right after:ml-0.5 after:content-[':']",
                      'w-20',
                    )}
                  >
                    {item.label}
                  </span>
                  <div className='flex-1 min-w-0'>{item.component}</div>
                </div>
              ))}

              {!expanded ? (
                <div className='flex items-center justify-end gap-2'>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={handleReset}
                  >
                    {t('module.order.filters.reset')}
                  </Button>
                  <Button
                    size='sm'
                    onClick={handleSearch}
                  >
                    {t('module.order.filters.search')}
                  </Button>
                  <Button
                    size='sm'
                    variant='ghost'
                    className='px-2 text-primary'
                    onClick={() => setExpanded(true)}
                  >
                    {t('common.core.expand')}
                    <ChevronDown className='ml-1 h-4 w-4' />
                  </Button>
                </div>
              ) : null}
            </div>

            {expanded ? (
              <div className='space-y-4'>
                <div className='grid gap-4 xl:grid-cols-3'>
                  {expandedSecondaryFilterItems.map(item => (
                    <div
                      key={item.key}
                      className='flex items-center'
                    >
                      <span
                        className={cn(
                          "shrink-0 mr-2 text-sm font-medium text-foreground whitespace-nowrap text-right after:ml-0.5 after:content-[':']",
                          'w-20',
                        )}
                      >
                        {item.label}
                      </span>
                      <div className='flex-1 min-w-0'>{item.component}</div>
                    </div>
                  ))}
                </div>

                <div className='flex items-center justify-end gap-2'>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={handleReset}
                  >
                    {t('module.order.filters.reset')}
                  </Button>
                  <Button
                    size='sm'
                    onClick={handleSearch}
                  >
                    {t('module.order.filters.search')}
                  </Button>
                  <Button
                    size='sm'
                    variant='ghost'
                    className='px-2 text-primary'
                    onClick={() => setExpanded(false)}
                  >
                    {t('common.core.collapse')}
                    <ChevronUp className='ml-1 h-4 w-4' />
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <AdminTableShell
          loading={loading}
          isEmpty={courses.length === 0}
          emptyContent={tOperations('emptyList')}
          emptyColSpan={11}
          withTooltipProvider
          tableWrapperClassName='max-h-[calc(100vh-18rem)] overflow-auto'
          table={emptyRow => (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('courseId')}
                  >
                    {tOperations('table.courseId')}
                    {renderResizeHandle('courseId')}
                  </TableHead>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('courseName')}
                  >
                    {tOperations('table.courseName')}
                    {renderResizeHandle('courseName')}
                  </TableHead>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('status')}
                  >
                    {tOperations('table.status')}
                    {renderResizeHandle('status')}
                  </TableHead>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('price')}
                  >
                    {tOperations('table.price')}
                    {renderResizeHandle('price')}
                  </TableHead>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('model')}
                  >
                    {tOperations('table.model')}
                    {renderResizeHandle('model')}
                  </TableHead>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('coursePrompt')}
                  >
                    {tOperations('table.coursePrompt')}
                    {renderResizeHandle('coursePrompt')}
                  </TableHead>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('creator')}
                  >
                    {tOperations('table.creator')}
                    {renderResizeHandle('creator')}
                  </TableHead>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('modifier')}
                  >
                    {tOperations('table.modifier')}
                    {renderResizeHandle('modifier')}
                  </TableHead>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('updatedAt')}
                  >
                    {tOperations('table.updatedAt')}
                    {renderResizeHandle('updatedAt')}
                  </TableHead>
                  <TableHead
                    className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                    style={getColumnStyle('createdAt')}
                  >
                    {tOperations('table.createdAt')}
                    {renderResizeHandle('createdAt')}
                  </TableHead>
                  <TableHead
                    className={getAdminStickyRightHeaderClass('text-center')}
                    style={getColumnStyle('action')}
                  >
                    {tOperations('table.action')}
                    {renderResizeHandle('action')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {emptyRow}
                {courses.map(course => {
                  const creatorDisplay = resolveActorDisplay(course, 'creator');
                  const updaterDisplay = resolveActorDisplay(course, 'updater');

                  return (
                    <TableRow key={course.shifu_bid}>
                      <TableCell
                        className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('courseId')}
                      >
                        {renderTooltipText(course.shifu_bid, 'mx-auto block')}
                      </TableCell>
                      <TableCell
                        className='whitespace-nowrap border-r border-border last:border-r-0 overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('courseName')}
                      >
                        <button
                          type='button'
                          className='mx-auto block max-w-full text-center text-primary transition-colors hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2'
                          onClick={() => handleDetailClick(course)}
                        >
                          {renderTooltipText(
                            course.course_name,
                            'truncate text-center',
                          )}
                        </button>
                      </TableCell>
                      <TableCell
                        className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('status')}
                      >
                        {renderTooltipText(
                          resolveCourseStatusLabel(course.course_status),
                          'mx-auto block text-foreground',
                        )}
                      </TableCell>
                      <TableCell
                        className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('price')}
                      >
                        {renderTooltipText(
                          formatMoney(course.price),
                          'mx-auto block text-foreground',
                        )}
                      </TableCell>
                      <TableCell
                        className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('model')}
                      >
                        {renderTooltipText(
                          course.course_model,
                          'mx-auto block text-foreground',
                        )}
                      </TableCell>
                      <TableCell
                        className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('coursePrompt')}
                      >
                        {course.has_course_prompt ? (
                          <button
                            type='button'
                            className='text-primary transition-colors hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2'
                            onClick={() => handlePromptDetailClick(course)}
                          >
                            {tOperations('table.detailAction')}
                          </button>
                        ) : (
                          renderTooltipText(undefined, 'text-foreground')
                        )}
                      </TableCell>
                      <TableCell
                        className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('creator')}
                      >
                        <div className='flex flex-col items-center gap-0.5 leading-tight'>
                          {renderTooltipText(
                            creatorDisplay.primary,
                            'mx-auto block text-foreground whitespace-nowrap text-center',
                          )}
                          {creatorDisplay.secondary
                            ? renderTooltipText(
                                creatorDisplay.secondary,
                                'mx-auto block text-xs text-muted-foreground text-center',
                              )
                            : null}
                        </div>
                      </TableCell>
                      <TableCell
                        className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('modifier')}
                      >
                        <div className='flex flex-col items-center gap-0.5 leading-tight'>
                          {renderTooltipText(
                            updaterDisplay.primary,
                            'mx-auto block text-foreground whitespace-nowrap text-center',
                          )}
                          {updaterDisplay.secondary
                            ? renderTooltipText(
                                updaterDisplay.secondary,
                                'mx-auto block text-xs text-muted-foreground text-center',
                              )
                            : null}
                        </div>
                      </TableCell>
                      <TableCell
                        className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('updatedAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(course.updated_at),
                          'mx-auto block',
                        )}
                      </TableCell>
                      <TableCell
                        className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                        style={getColumnStyle('createdAt')}
                      >
                        {renderTooltipText(
                          formatAdminUtcDateTime(course.created_at),
                          'mx-auto block',
                        )}
                      </TableCell>
                      <TableCell
                        className={getAdminStickyRightCellClass(
                          'whitespace-nowrap text-center',
                        )}
                        style={getColumnStyle('action')}
                      >
                        <div className='flex justify-center'>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <button
                                type='button'
                                className={cn(
                                  TABLE_INLINE_ACTION_BUTTON_CLASS,
                                  'gap-1',
                                )}
                              >
                                {t('common.core.more')}
                                <ChevronDown className='h-3.5 w-3.5' />
                              </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align='center'>
                              <DropdownMenuItem
                                onClick={() =>
                                  handleTransferCreatorClick(course)
                                }
                              >
                                {tOperations('actions.transferCreator')}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
          footer={
            <AdminPagination
              pageIndex={pageIndex}
              pageCount={pageCount}
              onPageChange={handlePageChange}
              prevLabel={t('module.order.paginationPrev', 'Previous')}
              nextLabel={t('module.order.paginationNext', 'Next')}
              prevAriaLabel={t(
                'module.order.paginationPrevAriaLabel',
                'Go to previous page',
              )}
              nextAriaLabel={t(
                'module.order.paginationNextAriaLabel',
                'Go to next page',
              )}
              className='justify-end w-auto mx-0'
            />
          }
        />
        <Dialog
          open={Boolean(promptDetailCourse)}
          onOpenChange={handlePromptDetailOpenChange}
        >
          <DialogContent className='w-[min(88vw,760px)] max-w-[760px] p-0'>
            <DialogHeader className='border-b border-border px-6 py-4 pr-12'>
              <div className='flex items-center justify-between gap-4'>
                <DialogTitle>
                  {tOperations('coursePromptDialog.title')}
                </DialogTitle>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='gap-2'
                  onClick={handleCopyCoursePrompt}
                  disabled={
                    !hasPromptDetailText ||
                    promptDetailLoading ||
                    Boolean(promptDetailError)
                  }
                >
                  <Copy className='h-4 w-4' />
                  {tOperations('coursePromptDialog.copy')}
                </Button>
              </div>
            </DialogHeader>
            <div className='min-h-[240px] max-h-[460px] overflow-auto px-6 py-5'>
              <section>
                <div className='rounded-lg border border-border bg-muted/20 p-4'>
                  {promptDetailLoading ? (
                    <div className='flex min-h-[180px] items-center justify-center'>
                      <Loading />
                    </div>
                  ) : null}
                  {!promptDetailLoading && promptDetailError ? (
                    <div className='flex min-h-[180px] flex-col items-center justify-center gap-3 text-center'>
                      <p className='text-sm leading-6 text-destructive'>
                        {promptDetailError}
                      </p>
                      <button
                        type='button'
                        className='text-sm font-medium text-primary transition-colors hover:text-primary/80'
                        onClick={() => {
                          if (promptDetailCourse) {
                            void handlePromptDetailClick(promptDetailCourse);
                          }
                        }}
                      >
                        {t('common.core.retry')}
                      </button>
                    </div>
                  ) : null}
                  {!promptDetailLoading && !promptDetailError ? (
                    <>
                      <div
                        ref={promptDetailContentRef}
                        className='break-words whitespace-pre-wrap text-sm leading-6 text-foreground'
                        style={
                          coursePromptExpanded || !canTogglePromptDetail
                            ? undefined
                            : COLLAPSED_TEXT_STYLE
                        }
                      >
                        {hasPromptDetailText
                          ? promptDetailText
                          : tOperations('coursePromptDialog.empty')}
                      </div>
                      {canTogglePromptDetail ? (
                        <div className='mt-3 flex justify-end'>
                          <button
                            type='button'
                            className='text-sm font-medium text-primary transition-colors hover:text-primary/80'
                            onClick={() =>
                              setCoursePromptExpanded(previous => !previous)
                            }
                          >
                            {coursePromptExpanded
                              ? t('common.core.collapse')
                              : t('common.core.expand')}
                          </button>
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </section>
            </div>
          </DialogContent>
        </Dialog>
        <Dialog
          open={transferDialogOpen}
          onOpenChange={handleTransferDialogOpenChange}
        >
          <DialogContent className='overflow-hidden p-0 gap-0 sm:max-w-[440px]'>
            <DialogHeader className='border-b border-border px-6 pb-4 pt-6'>
              <DialogTitle>
                {tOperations('transferCreatorDialog.title')}
              </DialogTitle>
              <p className='mt-2 text-sm leading-6 text-muted-foreground'>
                {transferHintText}
              </p>
            </DialogHeader>

            <div className='space-y-5 px-6 py-5'>
              <div className='rounded-xl border border-border bg-muted/[0.18] p-3.5'>
                <div className='space-y-3'>
                  <div className='space-y-1'>
                    <div className='text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground/90'>
                      {tOperations('table.courseName')}
                    </div>
                    <div className='text-[15px] font-medium leading-5 text-foreground'>
                      {transferCourseName}
                    </div>
                  </div>

                  <div className='h-px bg-border/80' />

                  <div className='space-y-1'>
                    <div className='text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground/90'>
                      {tOperations('transferCreatorDialog.currentCreator')}
                    </div>
                    <div className='text-[15px] font-medium leading-5 text-foreground'>
                      {transferCreatorDisplay.secondary ||
                        transferCreatorDisplay.primary ||
                        '--'}
                    </div>
                    {transferCreatorDisplay.primary &&
                    transferCreatorDisplay.secondary ? (
                      <div className='text-sm text-muted-foreground'>
                        {transferCreatorDisplay.primary}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className='space-y-2.5'>
                <Label
                  htmlFor='transfer-identifier'
                  className='text-sm font-medium text-foreground'
                >
                  {tOperations('transferCreatorDialog.identifier')}
                </Label>
                <Input
                  id='transfer-identifier'
                  value={transferIdentifier}
                  placeholder={transferIdentifierPlaceholder}
                  className='h-11 rounded-lg'
                  onChange={event => {
                    setTransferIdentifier(event.target.value);
                    if (transferError) {
                      setTransferError('');
                    }
                  }}
                  autoComplete='off'
                />
                {transferError ? (
                  <p className='text-sm text-destructive'>{transferError}</p>
                ) : null}
              </div>
            </div>

            <DialogFooter className='gap-2 border-t border-border bg-background px-6 py-4'>
              <Button
                variant='outline'
                onClick={() => handleTransferDialogOpenChange(false)}
                disabled={transferLoading}
                className='min-w-24'
              >
                {t('common.core.cancel')}
              </Button>
              <Button
                onClick={handleTransferSubmit}
                disabled={transferLoading || !transferTargetCourse}
                className='min-w-28'
              >
                {tOperations('transferCreatorDialog.confirm')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <AlertDialog
          open={transferConfirmOpen}
          onOpenChange={setTransferConfirmOpen}
        >
          <AlertDialogContent className='sm:max-w-[420px]'>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {tOperations('transferCreatorDialog.confirmTitle')}
              </AlertDialogTitle>
              <AlertDialogDescription>
                <span className='leading-8 text-muted-foreground'>
                  {tOperations(
                    'transferCreatorDialog.confirmDescriptionPrefix',
                  )}
                  <span className='mx-1 text-foreground'>
                    {transferCourseName}
                  </span>
                  {tOperations(
                    'transferCreatorDialog.confirmDescriptionCourseSuffix',
                  )}
                  <span className='mx-1 text-foreground'>
                    {transferCurrentCreatorText}
                  </span>
                  {tOperations(
                    'transferCreatorDialog.confirmDescriptionTargetPrefix',
                  )}
                  <span className='ml-1 font-semibold text-foreground'>
                    {transferTargetCreatorText}
                  </span>
                </span>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={transferLoading}>
                {t('common.core.cancel')}
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={handleTransferConfirm}
                disabled={transferLoading}
              >
                {tOperations('transferCreatorDialog.confirm')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
};

export default OperationsPage;
