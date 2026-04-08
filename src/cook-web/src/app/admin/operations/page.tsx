'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp, X } from 'lucide-react';
import api from '@/api';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import { useToast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { cn } from '@/lib/utils';
import { buildAdminOperationsCourseDetailUrl } from './operation-course-routes';
import type {
  AdminOperationCourseItem,
  AdminOperationCourseListResponse,
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

type ErrorState = { message: string; code?: number };

const PAGE_SIZE = 20;
const ALL_OPTION_VALUE = '__all__';
const COURSE_STATUS_PUBLISHED = 'published';
const COURSE_STATUS_UNPUBLISHED = 'unpublished';
const COLUMN_MIN_WIDTH = 80;
const COLUMN_MAX_WIDTH = 360;
const COLUMN_WIDTH_STORAGE_KEY = 'adminOperationsColumnWidths';
const DEFAULT_COLUMN_WIDTHS = {
  courseId: 260,
  courseName: 180,
  price: 90,
  status: 110,
  creator: 170,
  modifier: 170,
  createdAt: 170,
  updatedAt: 170,
  action: 115,
} as const;
type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;
type ColumnWidthState = Record<ColumnKey, number>;
const COLUMN_KEYS = Object.keys(DEFAULT_COLUMN_WIDTHS) as ColumnKey[];
const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 data-[state=checked]:bg-muted data-[state=checked]:text-foreground [&>span:first-child]:hidden';

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

const clampWidth = (value: number): number =>
  Math.min(COLUMN_MAX_WIDTH, Math.max(COLUMN_MIN_WIDTH, value));

const createColumnWidthState = (
  overrides?: Partial<ColumnWidthState>,
): ColumnWidthState => {
  const widths: ColumnWidthState = { ...DEFAULT_COLUMN_WIDTHS };
  COLUMN_KEYS.forEach(key => {
    const nextValue = overrides?.[key];
    if (typeof nextValue === 'number' && Number.isFinite(nextValue)) {
      widths[key] = clampWidth(nextValue);
    } else {
      widths[key] = clampWidth(widths[key]);
    }
  });
  return widths;
};

const loadStoredColumnWidths = (): ColumnWidthState => {
  if (typeof window === 'undefined') {
    return createColumnWidthState();
  }
  try {
    const serialized = window.localStorage.getItem(COLUMN_WIDTH_STORAGE_KEY);
    if (!serialized) {
      return createColumnWidthState();
    }
    const parsed = JSON.parse(serialized) as Partial<ColumnWidthState>;
    return createColumnWidthState(parsed);
  } catch {
    return createColumnWidthState();
  }
};

const renderPagination = (
  pageIndex: number,
  pageCount: number,
  onPageChange: (page: number) => void,
) => {
  const items: React.ReactElement[] = [];
  const maxVisiblePages = 5;

  if (pageCount <= maxVisiblePages + 2) {
    for (let index = 1; index <= pageCount; index += 1) {
      items.push(
        <PaginationItem key={index}>
          <PaginationLink
            href='#'
            isActive={pageIndex === index}
            onClick={event => {
              event.preventDefault();
              onPageChange(index);
            }}
          >
            {index}
          </PaginationLink>
        </PaginationItem>,
      );
    }
    return items;
  }

  items.push(
    <PaginationItem key={1}>
      <PaginationLink
        href='#'
        isActive={pageIndex === 1}
        onClick={event => {
          event.preventDefault();
          onPageChange(1);
        }}
      >
        {1}
      </PaginationLink>
    </PaginationItem>,
  );

  if (pageIndex > 3) {
    items.push(
      <PaginationItem key='start-ellipsis'>
        <PaginationEllipsis />
      </PaginationItem>,
    );
  }

  let rangeStart = Math.max(2, pageIndex - 1);
  let rangeEnd = Math.min(pageCount - 1, pageIndex + 1);

  if (pageIndex <= 3) {
    rangeStart = 2;
    rangeEnd = 4;
  }
  if (pageIndex >= pageCount - 2) {
    rangeEnd = pageCount - 1;
    rangeStart = pageCount - 3;
  }

  for (let index = rangeStart; index <= rangeEnd; index += 1) {
    items.push(
      <PaginationItem key={index}>
        <PaginationLink
          href='#'
          isActive={pageIndex === index}
          onClick={event => {
            event.preventDefault();
            onPageChange(index);
          }}
        >
          {index}
        </PaginationLink>
      </PaginationItem>,
    );
  }

  if (pageIndex < pageCount - 2) {
    items.push(
      <PaginationItem key='end-ellipsis'>
        <PaginationEllipsis />
      </PaginationItem>,
    );
  }

  items.push(
    <PaginationItem key={pageCount}>
      <PaginationLink
        href='#'
        isActive={pageIndex === pageCount}
        onClick={event => {
          event.preventDefault();
          onPageChange(pageCount);
        }}
      >
        {pageCount}
      </PaginationLink>
    </PaginationItem>,
  );

  return items;
};

const renderTooltipText = (text?: string, className?: string) => {
  const value = text && text.trim().length > 0 ? text : '--';
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            'inline-block max-w-full overflow-hidden text-ellipsis whitespace-nowrap align-bottom',
            className,
          )}
        >
          {value}
        </span>
      </TooltipTrigger>
      <TooltipContent side='top'>{value}</TooltipContent>
    </Tooltip>
  );
};

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
 * t('module.operationsCourse.table.courseId')
 * t('module.operationsCourse.table.courseName')
 * t('module.operationsCourse.table.price')
 * t('module.operationsCourse.table.status')
 * t('module.operationsCourse.table.creator')
 * t('module.operationsCourse.table.modifier')
 * t('module.operationsCourse.table.createdAt')
 * t('module.operationsCourse.table.updatedAt')
 * t('module.operationsCourse.table.action')
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
  const [filters, setFilters] = useState<CourseFilters>(createDefaultFilters);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [expanded, setExpanded] = useState(false);
  const [columnWidths, setColumnWidths] = useState<ColumnWidthState>(() =>
    loadStoredColumnWidths(),
  );
  const columnResizeRef = useRef<{
    key: ColumnKey;
    startX: number;
    startWidth: number;
  } | null>(null);
  const manualResizeRef = useRef<Record<ColumnKey, boolean>>(
    COLUMN_KEYS.reduce(
      (acc, key) => ({ ...acc, [key]: false }),
      {} as Record<ColumnKey, boolean>,
    ),
  );
  const initializedManualRef = useRef(false);
  const requestedPageRef = useRef(1);
  const requestIdRef = useRef(0);
  const fetchCoursesRef = useRef<
    | ((targetPage: number, nextFilters?: CourseFilters) => Promise<void>)
    | undefined
  >(undefined);

  const formatMoney = useCallback(
    (value?: string) =>
      `${currencySymbol || ''}${value && value.trim() ? value : '0'}`,
    [currencySymbol],
  );
  const defaultUserName = useMemo(() => t('module.user.defaultUserName'), [t]);
  const displayStatusValue = filters.course_status || ALL_OPTION_VALUE;

  useEffect(() => {
    if (initializedManualRef.current) {
      return;
    }
    initializedManualRef.current = true;
    COLUMN_KEYS.forEach(key => {
      const storedWidth = columnWidths[key];
      const defaultWidth = DEFAULT_COLUMN_WIDTHS[key];
      if (Math.abs(storedWidth - defaultWidth) > 0.5) {
        manualResizeRef.current[key] = true;
      }
    });
  }, [columnWidths]);

  useEffect(() => {
    const hasManualResize = Object.values(manualResizeRef.current).some(
      Boolean,
    );
    if (!hasManualResize || typeof window === 'undefined') {
      return;
    }
    try {
      window.localStorage.setItem(
        COLUMN_WIDTH_STORAGE_KEY,
        JSON.stringify(columnWidths),
      );
    } catch {
      // Ignore storage errors.
    }
  }, [columnWidths]);

  const fetchCourses = useCallback(
    async (targetPage: number, nextFilters?: CourseFilters) => {
      const resolvedFilters = nextFilters ?? filters;
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
          start_time: resolvedFilters.start_time,
          end_time: resolvedFilters.end_time,
          updated_start_time: resolvedFilters.updated_start_time,
          updated_end_time: resolvedFilters.updated_end_time,
        })) as AdminOperationCourseListResponse;
        if (requestId !== requestIdRef.current) {
          return;
        }
        setCourses(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 1);
      } catch (err) {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setPageIndex(targetPage);
        if (err instanceof ErrorWithCode) {
          setError({ message: err.message, code: err.code });
        } else if (err instanceof Error) {
          setError({ message: err.message });
        } else {
          setError({ message: t('common.core.unknownError') });
        }
      } finally {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setLoading(false);
      }
    },
    [filters, t],
  );

  useEffect(() => {
    fetchCoursesRef.current = fetchCourses;
  }, [fetchCourses]);

  useEffect(() => {
    if (!isInitialized || isGuest || !isReady) {
      return;
    }
    fetchCoursesRef.current?.(1, createDefaultFilters());
  }, [isGuest, isInitialized, isReady]);

  const handleFilterChange = (key: keyof CourseFilters, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const handleSearch = () => {
    fetchCourses(1, filters);
  };

  const handleReset = () => {
    const cleared = createDefaultFilters();
    setFilters(cleared);
    fetchCourses(1, cleared);
  };

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > pageCount || nextPage === pageIndex) {
      return;
    }
    fetchCourses(nextPage);
  };

  const handleDetailClick = (course: AdminOperationCourseItem) => {
    const detailUrl = buildAdminOperationsCourseDetailUrl(course.shifu_bid);
    if (!detailUrl) {
      return;
    }
    router.push(detailUrl);
  };

  const handleTransferCreatorClick = () => {
    toast({
      title: t('common.core.waitingForCompletion'),
    });
  };

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

  const startColumnResize = useCallback(
    (key: ColumnKey, clientX: number) => {
      columnResizeRef.current = {
        key,
        startX: clientX,
        startWidth: columnWidths[key],
      };
      manualResizeRef.current[key] = true;
    },
    [columnWidths],
  );

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const info = columnResizeRef.current;
      if (!info) {
        return;
      }
      const delta = event.clientX - info.startX;
      const desiredWidth = info.startWidth + delta;
      const nextWidth = clampWidth(desiredWidth);
      setColumnWidths(prev => {
        if (Math.abs(prev[info.key] - nextWidth) < 0.5) {
          return prev;
        }
        return { ...prev, [info.key]: nextWidth };
      });
    };

    const handleMouseUp = () => {
      columnResizeRef.current = null;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  const getColumnStyle = useCallback(
    (key: ColumnKey) => {
      const width = columnWidths[key];
      return {
        width,
        minWidth: width,
        maxWidth: width,
      };
    },
    [columnWidths],
  );

  const estimateWidth = (text: string, multiplier = 7) => {
    if (!text) {
      return COLUMN_MIN_WIDTH;
    }
    const approx = text.length * multiplier + 16;
    return approx;
  };

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
            if (!manualResizeRef.current[key]) {
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
        courseId: course => [course.shifu_bid],
        courseName: course => [course.course_name],
        price: course => [formatMoney(course.price)],
        status: course => [resolveCourseStatusLabel(course.course_status)],
        creator: course => [
          resolveActorDisplay(course, 'creator').primary,
          resolveActorDisplay(course, 'creator').secondary,
        ],
        modifier: course => [
          resolveActorDisplay(course, 'updater').primary,
          resolveActorDisplay(course, 'updater').secondary,
        ],
        createdAt: course => [course.created_at],
        updatedAt: course => [course.updated_at],
        action: () => [t('common.core.more')],
      };

      items.forEach(course => {
        COLUMN_KEYS.forEach(key => {
          const texts = columnValueExtractors[key](course).filter(Boolean);
          if (texts.length === 0) {
            return;
          }
          const multiplierMap: Partial<Record<ColumnKey, number>> = {
            courseId: 5,
            courseName: 4.5,
            price: 4,
            status: 5,
            creator: 4.6,
            modifier: 4.6,
            createdAt: 4.8,
            updatedAt: 4.8,
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
          if (manualResizeRef.current[key]) {
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
    [formatMoney, resolveActorDisplay, resolveCourseStatusLabel, t],
  );

  const renderResizeHandle = (key: ColumnKey) => (
    <span
      className='absolute top-0 right-0 h-full w-2 cursor-col-resize select-none'
      onMouseDown={event => {
        event.preventDefault();
        startColumnResize(key, event.clientX);
      }}
      aria-hidden='true'
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
          onRetry={() => fetchCourses(requestedPageRef.current)}
        />
      </div>
    );
  }

  return (
    <div className='h-full p-0'>
      <div className='max-w-7xl mx-auto h-full overflow-hidden flex flex-col'>
        <div className='mb-5'>
          <h1 className='text-2xl font-semibold text-gray-900'>
            {tOperations('title')}
          </h1>
        </div>

        <div className='rounded-xl border border-border bg-white p-4 mb-5 shadow-sm transition-all'>
          <div className='space-y-4'>
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

        <div className='max-h-[calc(100vh-18rem)] overflow-auto rounded-xl border border-border bg-white shadow-sm'>
          {loading ? (
            <div className='flex items-center justify-center h-40'>
              <Loading />
            </div>
          ) : (
            <TooltipProvider delayDuration={150}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className='relative border-r border-border last:border-r-0 sticky top-0 z-30 bg-muted text-center'
                      style={getColumnStyle('courseId')}
                    >
                      {tOperations('table.courseId')}
                      {renderResizeHandle('courseId')}
                    </TableHead>
                    <TableHead
                      className='relative border-r border-border last:border-r-0 sticky top-0 z-30 bg-muted text-center'
                      style={getColumnStyle('courseName')}
                    >
                      {tOperations('table.courseName')}
                      {renderResizeHandle('courseName')}
                    </TableHead>
                    <TableHead
                      className='relative border-r border-border last:border-r-0 sticky top-0 z-30 bg-muted text-center'
                      style={getColumnStyle('price')}
                    >
                      {tOperations('table.price')}
                      {renderResizeHandle('price')}
                    </TableHead>
                    <TableHead
                      className='relative border-r border-border last:border-r-0 sticky top-0 z-30 bg-muted text-center'
                      style={getColumnStyle('status')}
                    >
                      {tOperations('table.status')}
                      {renderResizeHandle('status')}
                    </TableHead>
                    <TableHead
                      className='relative border-r border-border last:border-r-0 sticky top-0 z-30 bg-muted text-center'
                      style={getColumnStyle('creator')}
                    >
                      {tOperations('table.creator')}
                      {renderResizeHandle('creator')}
                    </TableHead>
                    <TableHead
                      className='relative border-r border-border last:border-r-0 sticky top-0 z-30 bg-muted text-center'
                      style={getColumnStyle('modifier')}
                    >
                      {tOperations('table.modifier')}
                      {renderResizeHandle('modifier')}
                    </TableHead>
                    <TableHead
                      className='relative border-r border-border last:border-r-0 sticky top-0 z-30 bg-muted text-center'
                      style={getColumnStyle('createdAt')}
                    >
                      {tOperations('table.createdAt')}
                      {renderResizeHandle('createdAt')}
                    </TableHead>
                    <TableHead
                      className='relative border-r border-border last:border-r-0 sticky top-0 z-30 bg-muted text-center'
                      style={getColumnStyle('updatedAt')}
                    >
                      {tOperations('table.updatedAt')}
                      {renderResizeHandle('updatedAt')}
                    </TableHead>
                    <TableHead
                      className='sticky right-0 top-0 z-40 bg-muted text-center shadow-[-4px_0_4px_rgba(0,0,0,0.02)] before:content-[""] before:absolute before:left-0 before:inset-y-0 before:w-px before:bg-border'
                      style={getColumnStyle('action')}
                    >
                      {tOperations('table.action')}
                      {renderResizeHandle('action')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {courses.length === 0 && (
                    <TableEmpty colSpan={9}>
                      {tOperations('emptyList')}
                    </TableEmpty>
                  )}
                  {courses.map(course => {
                    const creatorDisplay = resolveActorDisplay(
                      course,
                      'creator',
                    );
                    const updaterDisplay = resolveActorDisplay(
                      course,
                      'updater',
                    );

                    return (
                      <TableRow key={course.shifu_bid}>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                          style={getColumnStyle('courseId')}
                        >
                          {renderTooltipText(course.shifu_bid)}
                        </TableCell>
                        <TableCell
                          className='whitespace-nowrap border-r border-border last:border-r-0 overflow-hidden text-ellipsis'
                          style={getColumnStyle('courseName')}
                        >
                          <button
                            type='button'
                            className='max-w-full truncate text-left text-primary transition-colors hover:text-primary/80 focus-visible:outline-none'
                            onClick={() => handleDetailClick(course)}
                            title={course.course_name || '--'}
                          >
                            {course.course_name || '--'}
                          </button>
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                          style={getColumnStyle('price')}
                        >
                          {renderTooltipText(
                            formatMoney(course.price),
                            'text-foreground',
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                          style={getColumnStyle('status')}
                        >
                          {renderTooltipText(
                            resolveCourseStatusLabel(course.course_status),
                            'text-foreground',
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                          style={getColumnStyle('creator')}
                        >
                          <div className='flex flex-col gap-0.5 leading-tight'>
                            {renderTooltipText(
                              creatorDisplay.primary,
                              'text-foreground whitespace-nowrap',
                            )}
                            {creatorDisplay.secondary
                              ? renderTooltipText(
                                  creatorDisplay.secondary,
                                  'text-xs text-muted-foreground',
                                )
                              : null}
                          </div>
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                          style={getColumnStyle('modifier')}
                        >
                          <div className='flex flex-col gap-0.5 leading-tight'>
                            {renderTooltipText(
                              updaterDisplay.primary,
                              'text-foreground whitespace-nowrap',
                            )}
                            {updaterDisplay.secondary
                              ? renderTooltipText(
                                  updaterDisplay.secondary,
                                  'text-xs text-muted-foreground',
                                )
                              : null}
                          </div>
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                          style={getColumnStyle('createdAt')}
                        >
                          {renderTooltipText(course.created_at)}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis'
                          style={getColumnStyle('updatedAt')}
                        >
                          {renderTooltipText(course.updated_at)}
                        </TableCell>
                        <TableCell
                          className='sticky right-0 z-10 bg-white shadow-[-4px_0_4px_rgba(0,0,0,0.02)] before:content-[""] before:absolute before:left-0 before:inset-y-0 before:w-px before:bg-border whitespace-nowrap text-center'
                          style={getColumnStyle('action')}
                        >
                          <div className='flex justify-center'>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <button
                                  type='button'
                                  className='inline-flex h-8 items-center justify-center gap-1 rounded-md px-2 text-sm font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none'
                                >
                                  {t('common.core.more')}
                                  <ChevronDown className='h-3.5 w-3.5' />
                                </button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align='center'>
                                <DropdownMenuItem
                                  onClick={handleTransferCreatorClick}
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
            </TooltipProvider>
          )}
        </div>

        <div className='mt-4 mb-4 flex justify-end'>
          <Pagination className='justify-end w-auto mx-0'>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  href='#'
                  onClick={event => {
                    event.preventDefault();
                    if (pageIndex > 1) {
                      handlePageChange(pageIndex - 1);
                    }
                  }}
                  aria-disabled={pageIndex <= 1}
                  className={
                    pageIndex <= 1 ? 'pointer-events-none opacity-50' : ''
                  }
                >
                  {t('module.order.paginationPrev', 'Previous')}
                </PaginationPrevious>
              </PaginationItem>

              {renderPagination(pageIndex, pageCount, handlePageChange)}

              <PaginationItem>
                <PaginationNext
                  href='#'
                  onClick={event => {
                    event.preventDefault();
                    if (pageIndex < pageCount) {
                      handlePageChange(pageIndex + 1);
                    }
                  }}
                  aria-disabled={pageIndex >= pageCount}
                  className={
                    pageIndex >= pageCount
                      ? 'pointer-events-none opacity-50'
                      : ''
                  }
                >
                  {t('module.order.paginationNext', 'Next')}
                </PaginationNext>
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      </div>
    </div>
  );
};

export default OperationsPage;
