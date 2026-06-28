'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import { ADMIN_TABLE_RESIZE_HANDLE_CLASS } from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import { useToast } from '@/hooks/useToast';
import { copyText } from '@/c-utils/textutils';
import { ErrorWithCode } from '@/lib/request';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import CourseCopyDialog from './CourseCopyDialog';
import CourseFiltersSection from './CourseFiltersSection';
import CourseOverviewSection from './CourseOverviewSection';
import CourseTransferCreatorDialog from './CourseTransferCreatorDialog';
import CoursePromptDialog from './CoursePromptDialog';
import CourseTableSection from './CourseTableSection';
import type {
  AdminOperationCourseItem,
  AdminOperationCourseListResponse,
  AdminOperationCourseOverview,
  AdminOperationCoursePromptResponse,
} from './operation-course-types';
import useOperatorGuard from './useOperatorGuard';
import {
  ALL_OPTION_VALUE,
  buildCopyCourseName,
  buildCreatedLast7DaysFilters,
  COLLAPSED_TEXT_STYLE,
  COLUMN_KEYS,
  COLUMN_MAX_WIDTH,
  COLUMN_MIN_WIDTH,
  COLUMN_WIDTH_STORAGE_KEY,
  COURSE_QUICK_FILTER_CREATED_LAST_7D,
  COURSE_QUICK_FILTER_DRAFT,
  COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D,
  COURSE_QUICK_FILTER_PAID_ORDER_30D,
  COURSE_QUICK_FILTER_PUBLISHED,
  COURSE_STATUS_PUBLISHED,
  COURSE_STATUS_UNPUBLISHED,
  createDefaultFilters,
  DEFAULT_COLUMN_WIDTHS,
  EMPTY_COURSE_OVERVIEW,
  EMPTY_STATE_LABEL,
  type ColumnKey,
  type CourseFilters,
  type CourseQuickFilterKey,
  type ErrorState,
  isValidTransferIdentifier,
  normalizeTransferIdentifier,
  PAGE_SIZE,
  SINGLE_SELECT_ITEM_CLASS,
  type TransferContactType,
} from './operationCoursePageShared';

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.operationsCourse.title')
 * t('module.operationsCourse.emptyList')
 * t('module.operationsCourse.actions.copyCourse')
 * t('module.operationsCourse.actions.transferCreator')
 * t('module.operationsCourse.detail.title')
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
 * t('module.operationsCourse.transferCreatorDialog.confirmDescription')
 * t('module.operationsCourse.copyCourseDialog.title')
 * t('module.operationsCourse.copyCourseDialog.description')
 * t('module.operationsCourse.copyCourseDialog.currentCreator')
 * t('module.operationsCourse.copyCourseDialog.contactType')
 * t('module.operationsCourse.copyCourseDialog.contactTypeEmail')
 * t('module.operationsCourse.copyCourseDialog.contactTypePhone')
 * t('module.operationsCourse.copyCourseDialog.newCourseName')
 * t('module.operationsCourse.copyCourseDialog.identifier')
 * t('module.operationsCourse.copyCourseDialog.contactPlaceholderEmail')
 * t('module.operationsCourse.copyCourseDialog.contactPlaceholderPhone')
 * t('module.operationsCourse.copyCourseDialog.identifierRequired')
 * t('module.operationsCourse.copyCourseDialog.confirm')
 * t('module.operationsCourse.copyCourseDialog.submitSuccess')
 * t('module.operationsCourse.copyCourseDialog.confirmTitle')
 * t('module.operationsCourse.copyCourseDialog.confirmDescription')
 */
const OperationsPage = () => {
  const { t, i18n } = useTranslation();
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
  const [copyDialogOpen, setCopyDialogOpen] = useState(false);
  const [copyTargetCourse, setCopyTargetCourse] =
    useState<AdminOperationCourseItem | null>(null);
  const [copyContactType, setCopyContactType] = useState<TransferContactType>(
    defaultTransferContactType,
  );
  const [copyIdentifier, setCopyIdentifier] = useState('');
  const [copyLoading, setCopyLoading] = useState(false);
  const [copyError, setCopyError] = useState('');
  const [copyConfirmOpen, setCopyConfirmOpen] = useState(false);
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
  const transferRequestIdRef = useRef(0);
  const copyRequestIdRef = useRef(0);
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

  const fetchCourseOverview = useCallback(async () => {
    try {
      const response = (await api.getAdminOperationCoursesOverview({})) as
        | AdminOperationCourseOverview
        | undefined;
      setCourseOverview(response ?? EMPTY_COURSE_OVERVIEW);
    } catch {
      setCourseOverview(EMPTY_COURSE_OVERVIEW);
    }
  }, []);

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
    void (async () => {
      await fetchCoursesRef.current?.(1, createDefaultFilters(), '');
      void fetchCourseOverview();
    })();
  }, [fetchCourseOverview, isGuest, isInitialized, isReady]);

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
      transferRequestIdRef.current += 1;
      setTransferTargetCourse(null);
      setTransferContactType(defaultTransferContactType);
      setTransferIdentifier('');
      setTransferError('');
      setTransferConfirmOpen(false);
      setTransferLoading(false);
    },
    [defaultTransferContactType],
  );

  const closeCopyDialog = useCallback(() => {
    copyRequestIdRef.current += 1;
    setCopyDialogOpen(false);
    setCopyTargetCourse(null);
    setCopyContactType(defaultTransferContactType);
    setCopyIdentifier('');
    setCopyError('');
    setCopyConfirmOpen(false);
    setCopyLoading(false);
  }, [defaultTransferContactType]);

  const handleCopyDialogOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen && copyLoading) {
        return;
      }
      setCopyDialogOpen(nextOpen);
      if (nextOpen) {
        return;
      }
      closeCopyDialog();
    },
    [closeCopyDialog, copyLoading],
  );

  const handleCopyCourseClick = useCallback(
    (course: AdminOperationCourseItem) => {
      setCopyTargetCourse(course);
      setCopyContactType(defaultTransferContactType);
      setCopyIdentifier('');
      setCopyError('');
      setCopyConfirmOpen(false);
      setCopyLoading(false);
      setCopyDialogOpen(true);
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
      preferredContactType?: TransferContactType,
    ) => {
      const resolvedContactType =
        preferredContactType || (isEmailMode ? 'email' : 'phone');
      if (kind === 'creator') {
        return resolvedContactType === 'email'
          ? user.creator_email
          : user.creator_mobile;
      }
      return resolvedContactType === 'email'
        ? user.updater_email
        : user.updater_mobile;
    },
    [isEmailMode],
  );

  const resolveActorDisplay = useCallback(
    (
      course: AdminOperationCourseItem,
      kind: 'creator' | 'updater',
      preferredContactType?: TransferContactType,
    ) => {
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
        primary:
          normalizeTransferIdentifier(
            preferredContactType || (isEmailMode ? 'email' : 'phone'),
            resolvePrimaryContact(course, kind, preferredContactType) || '',
          ) || '',
        secondary: nickname || defaultUserName,
      };
    },
    [defaultUserName, isEmailMode, resolvePrimaryContact],
  );

  const transferCreatorDisplay = useMemo(() => {
    if (!transferTargetCourse) {
      return { primary: '--', secondary: '' };
    }
    return resolveActorDisplay(
      transferTargetCourse,
      'creator',
      transferContactType,
    );
  }, [resolveActorDisplay, transferContactType, transferTargetCourse]);
  const transferCourseName = transferTargetCourse?.course_name?.trim() || '--';
  const copyCreatorDisplay = useMemo(() => {
    if (!copyTargetCourse) {
      return { primary: '--', secondary: '' };
    }
    return resolveActorDisplay(copyTargetCourse, 'creator', copyContactType);
  }, [copyContactType, copyTargetCourse, resolveActorDisplay]);
  const copyCourseName = copyTargetCourse?.course_name?.trim() || '--';
  const copyCourseNameFallback = useMemo(
    () => tOperations('copyCourseDialog.courseNameFallback'),
    [tOperations],
  );
  const copyCourseNameSuffix = useMemo(
    () => tOperations('copyCourseDialog.courseNameSuffix'),
    [tOperations],
  );
  const copyNewCourseName = useMemo(
    () =>
      buildCopyCourseName(
        copyTargetCourse?.course_name,
        copyCourseNameFallback,
        copyCourseNameSuffix,
      ),
    [
      copyCourseNameFallback,
      copyCourseNameSuffix,
      copyTargetCourse?.course_name,
    ],
  );

  const normalizedTransferIdentifier = useMemo(
    () => normalizeTransferIdentifier(transferContactType, transferIdentifier),
    [transferContactType, transferIdentifier],
  );
  const normalizedCopyIdentifier = useMemo(
    () => normalizeTransferIdentifier(copyContactType, copyIdentifier),
    [copyContactType, copyIdentifier],
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
  const copyIdentifierPlaceholder = useMemo(
    () =>
      copyContactType === 'email'
        ? tOperations('copyCourseDialog.contactPlaceholderEmail')
        : tOperations('copyCourseDialog.contactPlaceholderPhone'),
    [copyContactType, tOperations],
  );
  const transferHintText = useMemo(
    () => tOperations('transferCreatorDialog.description'),
    [tOperations],
  );
  const copyHintText = useMemo(
    () => tOperations('copyCourseDialog.description'),
    [tOperations],
  );
  const transferCurrentCreatorText = transferCurrentCreatorIdentifier || '--';
  const transferTargetCreatorText = normalizedTransferIdentifier || '--';
  const copyTargetCreatorText = normalizedCopyIdentifier || '--';

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

  useEffect(() => {
    if (!copyDialogOpen) {
      return;
    }
    if (!transferContactOptions.includes(copyContactType)) {
      setCopyContactType(defaultTransferContactType);
    }
  }, [
    copyContactType,
    copyDialogOpen,
    defaultTransferContactType,
    transferContactOptions,
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

  const handleCopySubmit = useCallback(() => {
    if (!copyTargetCourse) {
      return;
    }

    if (!isValidTransferIdentifier(copyContactType, normalizedCopyIdentifier)) {
      setCopyError(tOperations('copyCourseDialog.identifierRequired'));
      return;
    }

    setCopyError('');
    setCopyConfirmOpen(true);
  }, [
    copyContactType,
    copyTargetCourse,
    normalizedCopyIdentifier,
    tOperations,
  ]);

  const handleTransferConfirm = useCallback(async () => {
    if (!transferTargetCourse) {
      return;
    }

    const requestId = transferRequestIdRef.current + 1;
    transferRequestIdRef.current = requestId;
    setTransferConfirmOpen(false);
    setTransferError('');
    setTransferLoading(true);
    try {
      await api.transferAdminOperationCourseCreator({
        shifu_bid: transferTargetCourse.shifu_bid,
        contact_type: transferContactType,
        identifier: normalizedTransferIdentifier,
      });
      if (requestId !== transferRequestIdRef.current) {
        return;
      }
      toast({
        title: tOperations('transferCreatorDialog.submitSuccess'),
      });
      handleTransferDialogOpenChange(false);
      await fetchCourses(requestedPageRef.current, filters, quickFilter);
    } catch (error) {
      if (requestId !== transferRequestIdRef.current) {
        return;
      }
      setTransferError(
        error instanceof Error ? error.message : t('common.core.unknownError'),
      );
      setTransferLoading(false);
    } finally {
      if (requestId === transferRequestIdRef.current) {
        setTransferLoading(false);
      }
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

  const handleCopyConfirm = useCallback(async () => {
    if (!copyTargetCourse) {
      return;
    }

    const requestId = copyRequestIdRef.current + 1;
    copyRequestIdRef.current = requestId;
    setCopyConfirmOpen(false);
    setCopyError('');
    setCopyLoading(true);
    try {
      await api.copyAdminOperationCourse({
        shifu_bid: copyTargetCourse.shifu_bid,
        contact_type: copyContactType,
        identifier: normalizedCopyIdentifier,
        new_course_name: copyNewCourseName,
      });
      if (requestId !== copyRequestIdRef.current) {
        return;
      }
      toast({
        title: tOperations('copyCourseDialog.submitSuccess'),
      });
      closeCopyDialog();
      await Promise.all([
        fetchCourseOverview(),
        fetchCourses(requestedPageRef.current, filters, quickFilter),
      ]);
    } catch (error) {
      if (requestId !== copyRequestIdRef.current) {
        return;
      }
      setCopyError(
        error instanceof Error ? error.message : t('common.core.unknownError'),
      );
      setCopyLoading(false);
    } finally {
      if (requestId === copyRequestIdRef.current) {
        setCopyLoading(false);
      }
    }
  }, [
    closeCopyDialog,
    copyContactType,
    copyNewCourseName,
    copyTargetCourse,
    fetchCourses,
    fetchCourseOverview,
    filters,
    normalizedCopyIdentifier,
    quickFilter,
    t,
    tOperations,
    toast,
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
        <AdminClearableInput
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
        <AdminClearableInput
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
        <AdminClearableInput
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
        <AdminBreadcrumb items={[{ label: tOperations('title') }]} />
        <AdminTitle
          data-testid='admin-operations-header'
          title={tOperations('title')}
        />

        <CourseOverviewSection
          title={tOperations('overview.title')}
          cards={overviewCards}
          locale={i18n.language}
          onQuickFilter={applyQuickFilter}
        />

        <CourseFiltersSection
          items={[
            ...expandedPrimaryFilterItems,
            ...expandedSecondaryFilterItems,
          ]}
          expanded={expanded}
          activeQuickFilterCard={activeQuickFilterCard}
          clearLabel={clearLabel}
          activeFilterLabel={tOperations('overview.activeFilter')}
          resetLabel={t('module.order.filters.reset')}
          searchLabel={t('module.order.filters.search')}
          expandLabel={t('common.core.expand')}
          collapseLabel={t('common.core.collapse')}
          onExpandedChange={setExpanded}
          onReset={handleReset}
          onSearch={handleSearch}
          onQuickFilter={applyQuickFilter}
        />

        <CourseTableSection
          loading={loading}
          courses={courses}
          pageIndex={pageIndex}
          pageCount={pageCount}
          getColumnStyle={getColumnStyle}
          renderResizeHandle={renderResizeHandle}
          resolveActorDisplay={resolveActorDisplay}
          resolveCourseStatusLabel={resolveCourseStatusLabel}
          formatMoney={formatMoney}
          onPageChange={handlePageChange}
          onPromptDetailClick={handlePromptDetailClick}
          onCopyCourseClick={handleCopyCourseClick}
          onTransferCreatorClick={handleTransferCreatorClick}
        />
        <CoursePromptDialog
          course={promptDetailCourse}
          text={promptDetailText}
          loading={promptDetailLoading}
          error={promptDetailError}
          expanded={coursePromptExpanded}
          canToggle={canTogglePromptDetail}
          hasText={hasPromptDetailText}
          collapsedStyle={COLLAPSED_TEXT_STYLE}
          contentRef={promptDetailContentRef}
          onOpenChange={handlePromptDetailOpenChange}
          onCopy={handleCopyCoursePrompt}
          onRetry={course => void handlePromptDetailClick(course)}
          onToggleExpanded={() =>
            setCoursePromptExpanded(previous => !previous)
          }
        />
        <CourseCopyDialog
          open={copyDialogOpen}
          confirmOpen={copyConfirmOpen}
          loading={copyLoading}
          targetCourse={copyTargetCourse}
          courseName={copyCourseName}
          newCourseName={copyNewCourseName}
          creatorDisplay={copyCreatorDisplay}
          contactOptions={transferContactOptions}
          contactType={copyContactType}
          identifier={copyIdentifier}
          identifierPlaceholder={copyIdentifierPlaceholder}
          error={copyError}
          targetCreatorText={copyTargetCreatorText}
          hintText={copyHintText}
          onOpenChange={handleCopyDialogOpenChange}
          onConfirmOpenChange={setCopyConfirmOpen}
          onContactTypeChange={setCopyContactType}
          onIdentifierChange={value => {
            setCopyIdentifier(value);
            if (copyError) {
              setCopyError('');
            }
          }}
          onSubmit={handleCopySubmit}
          onConfirm={handleCopyConfirm}
        />

        <CourseTransferCreatorDialog
          open={transferDialogOpen}
          confirmOpen={transferConfirmOpen}
          loading={transferLoading}
          targetCourse={transferTargetCourse}
          courseName={transferCourseName}
          creatorDisplay={transferCreatorDisplay}
          contactOptions={transferContactOptions}
          contactType={transferContactType}
          identifier={transferIdentifier}
          identifierPlaceholder={transferIdentifierPlaceholder}
          error={transferError}
          currentCreatorText={transferCurrentCreatorText}
          targetCreatorText={transferTargetCreatorText}
          hintText={transferHintText}
          onOpenChange={handleTransferDialogOpenChange}
          onConfirmOpenChange={setTransferConfirmOpen}
          onContactTypeChange={setTransferContactType}
          onIdentifierChange={value => {
            setTransferIdentifier(value);
            if (transferError) {
              setTransferError('');
            }
          }}
          onSubmit={handleTransferSubmit}
          onConfirm={handleTransferConfirm}
        />
      </div>
    </div>
  );
};

export default OperationsPage;
