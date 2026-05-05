'use client';

import React, { useCallback, useRef, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSWRConfig } from 'swr';
import api from '@/api';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { useAdminResizableColumns } from '@/app/admin/hooks/useAdminResizableColumns';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
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
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { TooltipProvider } from '@/components/ui/tooltip';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import { BILLING_OVERVIEW_SWR_KEY } from '@/hooks/useBillingData';
import { buildBillingSwrKey, formatBillingCredits } from '@/lib/billing';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { cn } from '@/lib/utils';
import { ErrorWithCode } from '@/lib/request';
import { buildAdminOperationsCourseDetailUrl } from '../operation-course-routes';
import { buildAdminOperationsUserDetailUrl } from '../operation-user-routes';
import { formatOperatorUtcDateTime } from './dateTime';
import { normalizeLoginMethodLabelKey } from './loginMethodUtils';
import UserCreditGrantDialog from './UserCreditGrantDialog';
import useOperatorGuard from '../useOperatorGuard';
import type {
  AdminOperationUserCourseItem,
  AdminOperationUserItem,
  AdminOperationUserListResponse,
} from '../operation-user-types';

type UserFilters = {
  identifier: string;
  nickname: string;
  user_status: string;
  user_role: string;
  start_time: string;
  end_time: string;
};

type ErrorState = { message: string; code?: number };

const PAGE_SIZE = 20;
const ALL_OPTION_VALUE = '__all__';
const EMPTY_STATE_LABEL = '--';
const COLUMN_MIN_WIDTH = 90;
const COLUMN_MAX_WIDTH = 420;
const COLUMN_WIDTH_STORAGE_KEY = 'adminOperationsUsersColumnWidths';
const DEFAULT_COLUMN_WIDTHS = {
  userId: 260,
  mobile: 150,
  nickname: 120,
  status: 110,
  role: 120,
  loginMethods: 150,
  registrationSource: 130,
  learningCourses: 240,
  createdCourses: 240,
  totalPaidAmount: 140,
  availableCredits: 140,
  creditsExpireAt: 180,
  lastLoginAt: 180,
  lastLearningAt: 180,
  createdAt: 180,
  updatedAt: 180,
  action: 120,
} as const;
type ColumnKey = keyof typeof DEFAULT_COLUMN_WIDTHS;
const createDefaultFilters = (): UserFilters => ({
  identifier: '',
  nickname: '',
  user_status: '',
  user_role: '',
  start_time: '',
  end_time: '',
});

const renderTooltipText = (text?: string, className?: string) => {
  return (
    <AdminTooltipText
      text={text}
      emptyValue={EMPTY_STATE_LABEL}
      className={className}
    />
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

type CourseDialogState = {
  user: AdminOperationUserItem;
  courses: AdminOperationUserCourseItem[];
  type: 'learning' | 'created';
};

type CourseListPreviewProps = {
  courses: AdminOperationUserCourseItem[];
  emptyLabel: string;
  ariaLabel: string;
  onView: () => void;
};

const CourseListPreview = ({
  courses,
  emptyLabel,
  ariaLabel,
  onView,
}: CourseListPreviewProps) => {
  if (!courses.length) {
    return (
      <div className='py-1 text-center text-sm text-muted-foreground'>
        {emptyLabel}
      </div>
    );
  }

  return (
    <button
      type='button'
      aria-label={`${ariaLabel} (${courses.length})`}
      className='py-1 text-center text-sm font-semibold text-primary transition-colors hover:text-primary/80'
      onClick={onView}
    >
      {courses.length}
    </button>
  );
};

/**
 * t('module.operationsUser.title')
 * t('module.operationsUser.emptyList')
 * t('module.operationsUser.filters.mobile')
 * t('module.operationsUser.filters.email')
 * t('module.operationsUser.filters.nickname')
 * t('module.operationsUser.filters.status')
 * t('module.operationsUser.filters.role')
 * t('module.operationsUser.filters.createdAt')
 * t('module.operationsUser.table.userId')
 * t('module.operationsUser.table.mobile')
 * t('module.operationsUser.table.email')
 * t('module.operationsUser.table.guestUser')
 * t('module.operationsUser.table.nickname')
 * t('module.operationsUser.table.status')
 * t('module.operationsUser.table.role')
 * t('module.operationsUser.table.loginMethods')
 * t('module.operationsUser.table.registrationSource')
 * t('module.operationsUser.table.learningCourses')
 * t('module.operationsUser.table.createdCourses')
 * t('module.operationsUser.table.totalPaidAmount')
 * t('module.operationsUser.table.availableCredits')
 * t('module.operationsUser.table.creditsExpireAt')
 * t('module.operationsUser.table.lastLoginAt')
 * t('module.operationsUser.table.lastLearningAt')
 * t('module.operationsUser.table.createdAt')
 * t('module.operationsUser.table.updatedAt')
 * t('module.operationsUser.table.action')
 * t('module.operationsUser.actions.grantCredits')
 * t('module.operationsUser.actions.moreForUser')
 * t('module.operationsUser.courseSummary.empty')
 * t('module.operationsUser.courseSummary.dialog.learningTitle')
 * t('module.operationsUser.courseSummary.dialog.createdTitle')
 * t('module.operationsUser.courseSummary.dialog.description')
 * t('module.operationsUser.courseSummary.dialog.courseName')
 * t('module.operationsUser.courseSummary.dialog.courseId')
 * t('module.operationsUser.courseSummary.dialog.status')
 * t('module.operationsUser.statusLabels.unregistered')
 * t('module.operationsUser.statusLabels.registered')
 * t('module.operationsUser.statusLabels.paid')
 * t('module.operationsUser.statusLabels.unknown')
 * t('module.operationsCourse.statusLabels.published')
 * t('module.operationsCourse.statusLabels.unpublished')
 * t('module.operationsUser.roleLabels.regular')
 * t('module.operationsUser.roleLabels.creator')
 * t('module.operationsUser.roleLabels.operator')
 * t('module.operationsUser.roleLabels.learner')
 * t('module.operationsUser.roleLabels.unknown')
 * t('module.operationsUser.loginMethodLabels.phone')
 * t('module.operationsUser.loginMethodLabels.email')
 * t('module.operationsUser.loginMethodLabels.google')
 * t('module.operationsUser.loginMethodLabels.wechat')
 * t('module.operationsUser.loginMethodLabels.unknown')
 * t('module.operationsUser.registrationSourceLabels.phone')
 * t('module.operationsUser.registrationSourceLabels.email')
 * t('module.operationsUser.registrationSourceLabels.google')
 * t('module.operationsUser.registrationSourceLabels.wechat')
 * t('module.operationsUser.registrationSourceLabels.imported')
 * t('module.operationsUser.registrationSourceLabels.unknown')
 * t('module.user.defaultUserName')
 */
export default function AdminOperationUsersPage() {
  const { t, i18n } = useTranslation();
  const { t: tOperationsUsers } = useTranslation('module.operationsUser');
  const { t: tOperationsCourse } = useTranslation('module.operationsCourse');
  const { isReady } = useOperatorGuard();
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const currencySymbol = useEnvStore(
    (state: EnvStoreState) => state.currencySymbol || '',
  );
  const defaultUserName = React.useMemo(
    () => t('module.user.defaultUserName'),
    [t],
  );
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ErrorState | null>(null);
  const [users, setUsers] = useState<AdminOperationUserItem[]>([]);
  const [pageIndex, setPageIndex] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [courseDialog, setCourseDialog] = useState<CourseDialogState | null>(
    null,
  );
  const [grantDialogUser, setGrantDialogUser] =
    useState<AdminOperationUserItem | null>(null);
  const [draftFilters, setDraftFilters] = useState<UserFilters>(() =>
    createDefaultFilters(),
  );
  const [appliedFilters, setAppliedFilters] = useState<UserFilters>(() =>
    createDefaultFilters(),
  );
  const requestIdRef = useRef(0);
  const { mutate } = useSWRConfig();
  const lastRequestedPageRef = useRef(1);
  const { getColumnStyle, getResizeHandleProps } =
    useAdminResizableColumns<ColumnKey>({
      storageKey: COLUMN_WIDTH_STORAGE_KEY,
      defaultWidths: DEFAULT_COLUMN_WIDTHS,
      minWidth: COLUMN_MIN_WIDTH,
      maxWidth: COLUMN_MAX_WIDTH,
    });

  const resolveStatusLabel = useCallback(
    (status: string) => {
      const normalized =
        status === 'trial' ? 'registered' : status || 'unknown';
      return tOperationsUsers(`statusLabels.${normalized}`);
    },
    [tOperationsUsers],
  );

  const resolveRoleLabel = useCallback(
    (role: string) => {
      const normalized = role || 'unknown';
      return tOperationsUsers(`roleLabels.${normalized}`);
    },
    [tOperationsUsers],
  );

  const resolveLoginMethodLabel = useCallback(
    (method: string) => {
      const normalized = normalizeLoginMethodLabelKey(method);
      return tOperationsUsers(`loginMethodLabels.${normalized}`);
    },
    [tOperationsUsers],
  );

  const resolveRegistrationSourceLabel = useCallback(
    (source: string) => {
      const normalized = source || 'unknown';
      return tOperationsUsers(`registrationSourceLabels.${normalized}`);
    },
    [tOperationsUsers],
  );

  const resolveCourseStatusLabel = useCallback(
    (status: string) => {
      if (status === 'published') {
        return tOperationsCourse('statusLabels.published');
      }
      if (status === 'unpublished') {
        return tOperationsCourse('statusLabels.unpublished');
      }
      const unknownLabel = tOperationsCourse('statusLabels.unknown');
      return status ? `${unknownLabel} (${status})` : unknownLabel;
    },
    [tOperationsCourse],
  );

  const contactType = React.useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const identifierLabel = React.useMemo(
    () =>
      contactType === 'email'
        ? tOperationsUsers('filters.email')
        : tOperationsUsers('filters.mobile'),
    [contactType, tOperationsUsers],
  );
  const contactColumnLabel = React.useMemo(
    () =>
      contactType === 'email'
        ? tOperationsUsers('table.email')
        : tOperationsUsers('table.mobile'),
    [contactType, tOperationsUsers],
  );
  const guestUserLabel = React.useMemo(
    () => tOperationsUsers('table.guestUser'),
    [tOperationsUsers],
  );
  const resolveCreditsExpireAtLabel = React.useCallback(
    (user: AdminOperationUserItem) => {
      if (user.credits_expire_at) {
        return formatOperatorUtcDateTime(user.credits_expire_at);
      }
      if (Number(user.available_credits || 0) > 0) {
        return tOperationsUsers('credits.longTerm');
      }
      return EMPTY_STATE_LABEL;
    },
    [tOperationsUsers],
  );

  const fetchUsers = useCallback(
    async (targetPage: number, filters: UserFilters) => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      lastRequestedPageRef.current = targetPage;
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getAdminOperationUsers({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          identifier: filters.identifier.trim(),
          nickname: filters.nickname.trim(),
          user_status: filters.user_status,
          user_role: filters.user_role,
          start_time: filters.start_time,
          end_time: filters.end_time,
        })) as AdminOperationUserListResponse;
        if (requestId !== requestIdRef.current) {
          return;
        }
        setUsers(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 0);
      } catch (requestError) {
        if (requestId !== requestIdRef.current) {
          return;
        }
        const resolvedError = requestError as ErrorWithCode;
        setError({
          message: resolvedError.message || t('common.core.networkError'),
          code: resolvedError.code,
        });
        setUsers([]);
        setPageCount(0);
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [t],
  );

  React.useEffect(() => {
    if (!isReady) {
      return;
    }
    void fetchUsers(1, appliedFilters);
  }, [appliedFilters, fetchUsers, isReady]);

  const handleSearch = () => {
    const nextFilters = { ...draftFilters };
    setAppliedFilters(nextFilters);
    setPageIndex(1);
  };

  const handleReset = () => {
    const nextFilters = createDefaultFilters();
    setDraftFilters(nextFilters);
    setAppliedFilters(nextFilters);
    setPageIndex(1);
  };

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage === pageIndex) {
      return;
    }
    setPageIndex(nextPage);
    void fetchUsers(nextPage, appliedFilters);
  };

  const handleGrantSuccess = useCallback(() => {
    void fetchUsers(pageIndex, appliedFilters);
    void mutate(
      buildBillingSwrKey(BILLING_OVERVIEW_SWR_KEY, getBrowserTimeZone()),
    );
  }, [appliedFilters, fetchUsers, mutate, pageIndex]);

  const renderResizeHandle = (key: ColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getResizeHandleProps(key)}
    />
  );

  const statusOptions = [
    {
      value: ALL_OPTION_VALUE,
      label: t('common.core.all'),
    },
    {
      value: 'unregistered',
      label: resolveStatusLabel('unregistered'),
    },
    {
      value: 'registered',
      label: resolveStatusLabel('registered'),
    },
    {
      value: 'paid',
      label: resolveStatusLabel('paid'),
    },
  ];

  const roleOptions = [
    {
      value: ALL_OPTION_VALUE,
      label: t('common.core.all'),
    },
    {
      value: 'regular',
      label: resolveRoleLabel('regular'),
    },
    {
      value: 'creator',
      label: resolveRoleLabel('creator'),
    },
    {
      value: 'learner',
      label: resolveRoleLabel('learner'),
    },
    {
      value: 'operator',
      label: resolveRoleLabel('operator'),
    },
  ];

  const collapsedFilterItems = [
    {
      key: 'identifier',
      label: identifierLabel,
      component: (
        <ClearableTextInput
          value={draftFilters.identifier}
          placeholder={identifierLabel}
          clearLabel={t('common.core.close')}
          onChange={value =>
            setDraftFilters(current => ({
              ...current,
              identifier: value,
            }))
          }
        />
      ),
    },
    {
      key: 'nickname',
      label: tOperationsUsers('filters.nickname'),
      component: (
        <ClearableTextInput
          value={draftFilters.nickname}
          placeholder={tOperationsUsers('filters.nickname')}
          clearLabel={t('common.core.close')}
          onChange={value =>
            setDraftFilters(current => ({
              ...current,
              nickname: value,
            }))
          }
        />
      ),
    },
  ];

  const expandedFirstRowFilterItems = [
    ...collapsedFilterItems,
    {
      key: 'user_status',
      label: tOperationsUsers('filters.status'),
      component: (
        <Select
          value={draftFilters.user_status || ALL_OPTION_VALUE}
          onValueChange={value =>
            setDraftFilters(current => ({
              ...current,
              user_status: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger>
            <SelectValue placeholder={tOperationsUsers('filters.status')} />
          </SelectTrigger>
          <SelectContent>
            {statusOptions.map(option => (
              <SelectItem
                key={option.value}
                value={option.value}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
  ];

  const expandedSecondRowFilterItems = [
    {
      key: 'user_role',
      label: tOperationsUsers('filters.role'),
      component: (
        <Select
          value={draftFilters.user_role || ALL_OPTION_VALUE}
          onValueChange={value =>
            setDraftFilters(current => ({
              ...current,
              user_role: value === ALL_OPTION_VALUE ? '' : value,
            }))
          }
        >
          <SelectTrigger>
            <SelectValue placeholder={tOperationsUsers('filters.role')} />
          </SelectTrigger>
          <SelectContent>
            {roleOptions.map(option => (
              <SelectItem
                key={option.value}
                value={option.value}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: 'created_at',
      label: tOperationsUsers('filters.createdAt'),
      component: (
        <AdminDateRangeFilter
          startValue={draftFilters.start_time}
          endValue={draftFilters.end_time}
          placeholder={`${t('module.operationsCourse.filters.startTime')} ~ ${t('module.operationsCourse.filters.endTime')}`}
          resetLabel={t('module.order.filters.reset')}
          clearLabel={t('common.core.close')}
          onChange={({ start, end }) =>
            setDraftFilters(current => ({
              ...current,
              start_time: start,
              end_time: end,
            }))
          }
        />
      ),
    },
  ];

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
            fetchUsers(lastRequestedPageRef.current, appliedFilters)
          }
        />
      </div>
    );
  }

  return (
    <div className='h-full p-0'>
      <TooltipProvider delayDuration={150}>
        <div className='max-w-7xl mx-auto h-full overflow-hidden flex flex-col'>
          <div className='mb-5'>
            <h1 className='text-2xl font-semibold text-gray-900'>
              {tOperationsUsers('title')}
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
                  ? expandedFirstRowFilterItems
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
                    {expandedSecondRowFilterItems.map(item => (
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
                    <div className='flex items-center justify-end gap-2 xl:self-end'>
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
                </div>
              ) : null}
            </div>
          </div>

          <AdminTableShell
            loading={loading}
            isEmpty={users.length === 0}
            emptyContent={tOperationsUsers('emptyList')}
            emptyColSpan={17}
            tableWrapperClassName='max-h-[calc(100vh-18rem)] overflow-auto'
            table={emptyRow => (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('userId')}
                    >
                      {tOperationsUsers('table.userId')}
                      {renderResizeHandle('userId')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('mobile')}
                    >
                      {contactColumnLabel}
                      {renderResizeHandle('mobile')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('nickname')}
                    >
                      {tOperationsUsers('table.nickname')}
                      {renderResizeHandle('nickname')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('status')}
                    >
                      {tOperationsUsers('table.status')}
                      {renderResizeHandle('status')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('role')}
                    >
                      {tOperationsUsers('table.role')}
                      {renderResizeHandle('role')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('loginMethods')}
                    >
                      {tOperationsUsers('table.loginMethods')}
                      {renderResizeHandle('loginMethods')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('registrationSource')}
                    >
                      {tOperationsUsers('table.registrationSource')}
                      {renderResizeHandle('registrationSource')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('learningCourses')}
                    >
                      {tOperationsUsers('table.learningCourses')}
                      {renderResizeHandle('learningCourses')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('createdCourses')}
                    >
                      {tOperationsUsers('table.createdCourses')}
                      {renderResizeHandle('createdCourses')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('totalPaidAmount')}
                    >
                      {tOperationsUsers('table.totalPaidAmount')}
                      {renderResizeHandle('totalPaidAmount')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('availableCredits')}
                    >
                      {tOperationsUsers('table.availableCredits')}
                      {renderResizeHandle('availableCredits')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('creditsExpireAt')}
                    >
                      {tOperationsUsers('table.creditsExpireAt')}
                      {renderResizeHandle('creditsExpireAt')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('lastLoginAt')}
                    >
                      {tOperationsUsers('table.lastLoginAt')}
                      {renderResizeHandle('lastLoginAt')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('lastLearningAt')}
                    >
                      {tOperationsUsers('table.lastLearningAt')}
                      {renderResizeHandle('lastLearningAt')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('createdAt')}
                    >
                      {tOperationsUsers('table.createdAt')}
                      {renderResizeHandle('createdAt')}
                    </TableHead>
                    <TableHead
                      className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                      style={getColumnStyle('updatedAt')}
                    >
                      {tOperationsUsers('table.updatedAt')}
                      {renderResizeHandle('updatedAt')}
                    </TableHead>
                    <TableHead
                      className={getAdminStickyRightHeaderClass('text-center')}
                      style={getColumnStyle('action')}
                    >
                      {tOperationsUsers('table.action')}
                      {renderResizeHandle('action')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emptyRow}
                  {users.map(user => {
                    const primaryContact =
                      contactType === 'email'
                        ? user.email?.trim() || ''
                        : user.mobile?.trim() || '';
                    const isGuestUser =
                      !user.mobile?.trim() && !user.email?.trim();
                    const userDetailUrl = buildAdminOperationsUserDetailUrl(
                      user.user_bid,
                    );
                    const loginMethods = user.login_methods.length
                      ? user.login_methods
                          .map(resolveLoginMethodLabel)
                          .join(' / ')
                      : EMPTY_STATE_LABEL;
                    const registrationSource = resolveRegistrationSourceLabel(
                      user.registration_source,
                    );
                    return (
                      <TableRow key={user.user_bid}>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('userId')}
                        >
                          {userDetailUrl ? (
                            <Link
                              href={userDetailUrl}
                              className='text-primary transition-colors hover:text-primary/80 hover:underline'
                            >
                              {renderTooltipText(user.user_bid)}
                            </Link>
                          ) : (
                            renderTooltipText(user.user_bid)
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('mobile')}
                        >
                          {isGuestUser ? (
                            <span className='text-sm text-muted-foreground'>
                              {guestUserLabel}
                            </span>
                          ) : userDetailUrl && primaryContact ? (
                            <Link
                              href={userDetailUrl}
                              className='text-primary transition-colors hover:text-primary/80 hover:underline'
                            >
                              {renderTooltipText(primaryContact)}
                            </Link>
                          ) : (
                            renderTooltipText(primaryContact)
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('nickname')}
                        >
                          {renderTooltipText(user.nickname || defaultUserName)}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('status')}
                        >
                          {renderTooltipText(
                            resolveStatusLabel(user.user_status),
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('role')}
                        >
                          {renderTooltipText(resolveRoleLabel(user.user_role))}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('loginMethods')}
                        >
                          {renderTooltipText(loginMethods)}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('registrationSource')}
                        >
                          {renderTooltipText(registrationSource)}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('learningCourses')}
                        >
                          <CourseListPreview
                            courses={user.learning_courses}
                            emptyLabel={EMPTY_STATE_LABEL}
                            ariaLabel={tOperationsUsers(
                              'table.learningCourses',
                            )}
                            onView={() =>
                              setCourseDialog({
                                user,
                                courses: user.learning_courses,
                                type: 'learning',
                              })
                            }
                          />
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('createdCourses')}
                        >
                          <CourseListPreview
                            courses={user.created_courses}
                            emptyLabel={EMPTY_STATE_LABEL}
                            ariaLabel={tOperationsUsers('table.createdCourses')}
                            onView={() =>
                              setCourseDialog({
                                user,
                                courses: user.created_courses,
                                type: 'created',
                              })
                            }
                          />
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('totalPaidAmount')}
                        >
                          {renderTooltipText(
                            `${currencySymbol}${user.total_paid_amount || '0'}`,
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('availableCredits')}
                        >
                          {userDetailUrl && user.available_credits ? (
                            <Link
                              href={`${userDetailUrl}#credits`}
                              className='text-primary transition-colors hover:text-primary/80 hover:underline'
                            >
                              {renderTooltipText(
                                user.available_credits
                                  ? formatBillingCredits(
                                      Number(user.available_credits),
                                      i18n.language,
                                    )
                                  : EMPTY_STATE_LABEL,
                              )}
                            </Link>
                          ) : (
                            renderTooltipText(
                              user.available_credits
                                ? formatBillingCredits(
                                    Number(user.available_credits),
                                    i18n.language,
                                  )
                                : EMPTY_STATE_LABEL,
                            )
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('creditsExpireAt')}
                        >
                          {renderTooltipText(resolveCreditsExpireAtLabel(user))}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('lastLoginAt')}
                        >
                          {renderTooltipText(
                            formatOperatorUtcDateTime(user.last_login_at),
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('lastLearningAt')}
                        >
                          {renderTooltipText(
                            formatOperatorUtcDateTime(user.last_learning_at),
                          )}
                        </TableCell>
                        <TableCell
                          className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('createdAt')}
                        >
                          {renderTooltipText(
                            formatOperatorUtcDateTime(user.created_at),
                          )}
                        </TableCell>
                        <TableCell
                          className='whitespace-nowrap overflow-hidden text-ellipsis text-center'
                          style={getColumnStyle('updatedAt')}
                        >
                          {renderTooltipText(
                            formatOperatorUtcDateTime(user.updated_at),
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
                                  aria-label={tOperationsUsers(
                                    'actions.moreForUser',
                                    {
                                      user: user.user_bid,
                                    },
                                  )}
                                  className='inline-flex h-8 items-center justify-center gap-1 rounded-md px-2 text-sm font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none'
                                >
                                  {t('common.core.more')}
                                  <ChevronDown className='h-3.5 w-3.5' />
                                </button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align='center'>
                                <DropdownMenuItem
                                  onClick={() => setGrantDialogUser(user)}
                                >
                                  {tOperationsUsers('actions.grantCredits')}
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
              pageCount > 1 ? (
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
              ) : null
            }
          />
          <Dialog
            open={Boolean(courseDialog)}
            onOpenChange={open => {
              if (!open) {
                setCourseDialog(null);
              }
            }}
          >
            <DialogContent className='sm:max-w-3xl'>
              <DialogHeader className='space-y-2'>
                <DialogTitle>
                  {courseDialog?.type === 'learning'
                    ? tOperationsUsers('courseSummary.dialog.learningTitle')
                    : tOperationsUsers('courseSummary.dialog.createdTitle')}
                </DialogTitle>
                <DialogDescription>
                  {tOperationsUsers('courseSummary.dialog.description', {
                    user:
                      courseDialog?.user.nickname ||
                      defaultUserName ||
                      courseDialog?.user.email ||
                      courseDialog?.user.mobile ||
                      courseDialog?.user.user_bid ||
                      EMPTY_STATE_LABEL,
                  })}
                </DialogDescription>
              </DialogHeader>

              <div className='rounded-lg border border-border'>
                <div className='max-h-[60vh] overflow-auto'>
                  <Table className='table-fixed'>
                    <colgroup>
                      <col className='w-[34%]' />
                      <col className='w-[46%]' />
                      <col className='w-[20%]' />
                    </colgroup>
                    <TableHeader>
                      <TableRow>
                        <TableHead className='bg-muted text-center sticky top-0 z-20'>
                          {tOperationsUsers('courseSummary.dialog.courseName')}
                        </TableHead>
                        <TableHead className='bg-muted text-center sticky top-0 z-20'>
                          {tOperationsUsers('courseSummary.dialog.courseId')}
                        </TableHead>
                        <TableHead className='bg-muted text-center sticky top-0 z-20'>
                          {tOperationsUsers('courseSummary.dialog.status')}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {courseDialog?.courses?.length ? (
                        courseDialog.courses.map(course => {
                          const courseDetailUrl =
                            buildAdminOperationsCourseDetailUrl(
                              course.shifu_bid,
                            );
                          return (
                            <TableRow
                              key={`${courseDialog.type}-${course.shifu_bid}`}
                            >
                              <TableCell className='max-w-0 whitespace-nowrap overflow-hidden text-ellipsis'>
                                {courseDetailUrl ? (
                                  <Link
                                    href={courseDetailUrl}
                                    className='inline-block max-w-full text-primary transition-colors hover:text-primary/80 hover:underline'
                                  >
                                    <AdminTooltipText
                                      text={course.course_name}
                                      emptyValue={EMPTY_STATE_LABEL}
                                    />
                                  </Link>
                                ) : (
                                  <AdminTooltipText
                                    text={course.course_name}
                                    emptyValue={EMPTY_STATE_LABEL}
                                  />
                                )}
                              </TableCell>
                              <TableCell className='max-w-0 whitespace-nowrap overflow-hidden text-ellipsis'>
                                <AdminTooltipText
                                  text={course.shifu_bid}
                                  emptyValue={EMPTY_STATE_LABEL}
                                />
                              </TableCell>
                              <TableCell className='max-w-0 whitespace-nowrap overflow-hidden text-ellipsis text-center'>
                                <AdminTooltipText
                                  text={resolveCourseStatusLabel(
                                    course.course_status,
                                  )}
                                  emptyValue={EMPTY_STATE_LABEL}
                                />
                              </TableCell>
                            </TableRow>
                          );
                        })
                      ) : (
                        <TableEmpty colSpan={3}>
                          {tOperationsUsers('courseSummary.empty')}
                        </TableEmpty>
                      )}
                    </TableBody>
                  </Table>
                </div>
              </div>
            </DialogContent>
          </Dialog>
          <UserCreditGrantDialog
            open={Boolean(grantDialogUser)}
            user={grantDialogUser}
            onOpenChange={nextOpen => {
              if (!nextOpen) {
                setGrantDialogUser(null);
              }
            }}
            onGranted={handleGrantSuccess}
          />
        </div>
      </TooltipProvider>
    </div>
  );
}
