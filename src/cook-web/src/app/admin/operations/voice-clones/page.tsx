'use client';

import React from 'react';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import {
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import AdminTitle from '@/app/admin/components/AdminTitle';
import Loading from '@/components/loading';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { toast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import useOperatorGuard from '../useOperatorGuard';
import type {
  AdminOperationVoiceCloneFilters,
  AdminOperationVoiceCloneItem,
  AdminOperationVoiceCloneListResponse,
} from '../operation-voice-clone-types';

const PAGE_SIZE = 20;
const ALL_OPTION_VALUE = '__all__';
const EMPTY_LABEL = '--';
const STATUS_VALUES = [
  'queued',
  'processing',
  'billing_pending',
  'ready',
  'failed',
];
const BILLING_STATUS_VALUES = [
  'not_required',
  'reserved',
  'charged',
  'released',
  'failed',
];
const FILTER_SELECT_ITEM_CLASS =
  'pl-3 pr-8 data-[state=checked]:bg-muted data-[state=checked]:text-foreground';
const FILTER_SELECT_INDICATOR_CLASS = 'left-auto right-2';

const createDefaultFilters = (): AdminOperationVoiceCloneFilters => ({
  status: '',
  failure_reason: '',
  billing_status: '',
  start_time: '',
  end_time: '',
  user_keyword: '',
  course_keyword: '',
  voice_keyword: '',
  minimax_status_code: '',
});

const formatOwnerPrimary = (item: AdminOperationVoiceCloneItem) =>
  item.owner_nickname || item.owner_mobile || item.owner_email || EMPTY_LABEL;

const formatOwnerSecondary = (item: AdminOperationVoiceCloneItem) => {
  const contacts = [item.owner_mobile, item.owner_email].filter(Boolean);
  return contacts.join(' / ');
};

const formatDuration = (durationMs: number) => {
  if (!durationMs || durationMs <= 0) {
    return EMPTY_LABEL;
  }
  return `${(durationMs / 1000).toFixed(1)}s`;
};

const hasPositiveCredits = (value: string) => {
  const amount = Number(value || 0);
  return Number.isFinite(amount) && amount > 0;
};

const resolveVoiceIdentifier = (item: AdminOperationVoiceCloneItem) =>
  item.voice_id || item.voice_bid || EMPTY_LABEL;

const formatDisplayTime = (value: string) =>
  formatAdminUtcDateTime(value) || value || EMPTY_LABEL;

export default function AdminOperationVoiceClonesPage() {
  const { t } = useTranslation();
  const { isReady } = useOperatorGuard();
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const [items, setItems] = React.useState<AdminOperationVoiceCloneItem[]>([]);
  const [draftFilters, setDraftFilters] =
    React.useState<AdminOperationVoiceCloneFilters>(createDefaultFilters);
  const [appliedFilters, setAppliedFilters] =
    React.useState<AdminOperationVoiceCloneFilters>(createDefaultFilters);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [pageCount, setPageCount] = React.useState(0);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');
  const [detail, setDetail] =
    React.useState<AdminOperationVoiceCloneItem | null>(null);
  const [filtersExpanded, setFiltersExpanded] = React.useState(false);
  const requestIdRef = React.useRef(0);
  const filterControlClassName = 'min-w-0 flex-1 xl:max-w-[245px]';
  const filterLabelClassName = 'w-28 text-right';

  const setDraftFilter = React.useCallback(
    (key: keyof AdminOperationVoiceCloneFilters, value: string) => {
      setDraftFilters(current => ({ ...current, [key]: value }));
    },
    [],
  );

  const buildRequestParams = React.useCallback(() => {
    const params: Record<string, string | number> = {
      page_index: pageIndex,
      page_size: PAGE_SIZE,
    };
    Object.entries(appliedFilters).forEach(([key, value]) => {
      const normalized = value.trim();
      if (normalized) {
        params[key] = normalized;
      }
    });
    return params;
  }, [appliedFilters, pageIndex]);

  const fetchItems = React.useCallback(async () => {
    if (!isReady) {
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError('');
    try {
      const response = (await api.getAdminOperationVoiceClones(
        buildRequestParams(),
      )) as AdminOperationVoiceCloneListResponse;
      if (requestId !== requestIdRef.current) {
        return;
      }
      setItems(Array.isArray(response.items) ? response.items : []);
      setTotal(Number(response.total || 0));
      setPageCount(Number(response.page_count || 0));
    } catch (caughtError) {
      if (requestId !== requestIdRef.current) {
        return;
      }
      const typedError = caughtError as Partial<ErrorWithCode>;
      setError(
        typedError.message || t('module.operationsVoiceClone.loadFailed'),
      );
      setItems([]);
      setTotal(0);
      setPageCount(0);
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [buildRequestParams, isReady, t]);

  React.useEffect(() => {
    void fetchItems();
  }, [fetchItems]);

  const applyFilters = React.useCallback(() => {
    setAppliedFilters(draftFilters);
    setPageIndex(1);
  }, [draftFilters]);

  const resetFilters = React.useCallback(() => {
    const nextFilters = createDefaultFilters();
    setDraftFilters(nextFilters);
    setAppliedFilters(nextFilters);
    setPageIndex(1);
  }, []);

  const copyText = React.useCallback(
    async (value: string) => {
      if (!value) {
        return;
      }
      await navigator.clipboard.writeText(value);
      toast({ title: t('module.operationsVoiceClone.copySuccess') });
    },
    [t],
  );

  const resolveStatusLabel = React.useCallback(
    (status: string) =>
      t(`module.operationsVoiceClone.status.${status}`, status || EMPTY_LABEL),
    [t],
  );

  const resolveBillingStatusLabel = React.useCallback(
    (status: string) =>
      t(
        `module.operationsVoiceClone.billingStatus.${status}`,
        status || EMPTY_LABEL,
      ),
    [t],
  );

  const resolveFailureReasonLabel = React.useCallback(
    (item: AdminOperationVoiceCloneItem) => {
      const statusMessage = (item.status_msg || '').toLowerCase();
      if (statusMessage.includes('unable to decode audio')) {
        return t(
          'module.operationsVoiceClone.failureReason.unableToDecodeAudio',
        );
      }
      if (statusMessage.includes('unsupported audio file type')) {
        return t(
          'module.operationsVoiceClone.failureReason.unsupportedAudioType',
        );
      }
      if (statusMessage.includes('audio file is empty')) {
        return t('module.operationsVoiceClone.failureReason.emptyAudio');
      }
      if (statusMessage.includes('at least 10 seconds')) {
        return t('module.operationsVoiceClone.failureReason.sourceTooShort');
      }
      if (statusMessage.includes('no longer than 5 minutes')) {
        return t('module.operationsVoiceClone.failureReason.sourceTooLong');
      }
      if (statusMessage.includes('no longer than 8 seconds')) {
        return t('module.operationsVoiceClone.failureReason.promptTooLong');
      }
      if (statusMessage.includes('sensitive content')) {
        return t('module.operationsVoiceClone.failureReason.sensitiveContent');
      }
      if (statusMessage.includes('minimax voice clone failed')) {
        return t(
          'module.operationsVoiceClone.failureReason.minimaxProviderError',
        );
      }
      if (statusMessage.includes('billing capture is pending')) {
        return t('module.operationsVoiceClone.failureReason.billingPending');
      }
      if (statusMessage.includes('no longer available')) {
        return t('module.operationsVoiceClone.failureReason.audioExpired');
      }
      if (!item.failure_reason) {
        return EMPTY_LABEL;
      }
      return t(
        `module.operationsVoiceClone.failureReason.${item.failure_reason}`,
        item.failure_reason,
      );
    },
    [t],
  );

  const resolveFailureDetailLabel = React.useCallback(
    (item: AdminOperationVoiceCloneItem) => {
      const statusMessage = (item.status_msg || '').toLowerCase();
      if (!statusMessage) {
        return EMPTY_LABEL;
      }
      if (statusMessage.includes('unable to decode audio')) {
        return t(
          'module.operationsVoiceClone.failureDetail.unableToDecodeAudio',
        );
      }
      if (statusMessage.includes('unsupported audio file type')) {
        return t(
          'module.operationsVoiceClone.failureDetail.unsupportedAudioType',
        );
      }
      if (statusMessage.includes('audio file is empty')) {
        return t('module.operationsVoiceClone.failureDetail.emptyAudio');
      }
      if (statusMessage.includes('at least 10 seconds')) {
        return t('module.operationsVoiceClone.failureDetail.sourceTooShort');
      }
      if (statusMessage.includes('no longer than 5 minutes')) {
        return t('module.operationsVoiceClone.failureDetail.sourceTooLong');
      }
      if (statusMessage.includes('no longer than 8 seconds')) {
        return t('module.operationsVoiceClone.failureDetail.promptTooLong');
      }
      if (statusMessage.includes('invalid audio purpose')) {
        return t(
          'module.operationsVoiceClone.failureDetail.invalidAudioPurpose',
        );
      }
      if (statusMessage.includes('minimax_api_key is not configured')) {
        return t(
          'module.operationsVoiceClone.failureDetail.minimaxApiKeyMissing',
        );
      }
      if (statusMessage.includes('did not return file_id')) {
        return t(
          'module.operationsVoiceClone.failureDetail.minimaxFileIdMissing',
        );
      }
      if (statusMessage.includes('sensitive content')) {
        return t('module.operationsVoiceClone.failureDetail.sensitiveContent');
      }
      if (statusMessage.includes('billing capture is pending')) {
        return t('module.operationsVoiceClone.failureDetail.billingPending');
      }
      if (statusMessage.includes('audio resource is missing')) {
        return t(
          'module.operationsVoiceClone.failureDetail.audioResourceMissing',
        );
      }
      if (statusMessage.includes('no longer available')) {
        return t('module.operationsVoiceClone.failureDetail.audioExpired');
      }
      if (statusMessage.includes('minimax voice clone failed')) {
        return t(
          'module.operationsVoiceClone.failureDetail.minimaxProviderError',
          {
            message: item.status_msg,
          },
        );
      }
      return item.status_msg;
    },
    [t],
  );

  const userKeywordPlaceholder = React.useMemo(() => {
    const contactType = resolveContactMode(
      loginMethodsEnabled,
      defaultLoginMethod,
    );
    const methods = loginMethodsEnabled || [];
    const hasPhone = methods.includes('phone');
    const hasEmail = methods.includes('email');
    if (contactType === 'email' || (hasEmail && !hasPhone)) {
      return t(
        'module.operationsVoiceClone.filters.userKeywordPlaceholderEmail',
      );
    }
    if (hasPhone && !hasEmail) {
      return t(
        'module.operationsVoiceClone.filters.userKeywordPlaceholderPhone',
      );
    }
    return t('module.operationsVoiceClone.filters.userKeywordPlaceholder');
  }, [defaultLoginMethod, loginMethodsEnabled, t]);

  const filterItems = React.useMemo(
    () => [
      {
        key: 'user_keyword',
        label: t('module.operationsVoiceClone.filters.userKeyword'),
        component: (
          <AdminClearableInput
            value={draftFilters.user_keyword}
            placeholder={userKeywordPlaceholder}
            clearLabel={t('common.core.close')}
            onChange={value => setDraftFilter('user_keyword', value)}
            onSubmit={applyFilters}
          />
        ),
      },
      {
        key: 'voice_keyword',
        label: t('module.operationsVoiceClone.filters.voiceKeyword'),
        component: (
          <AdminClearableInput
            value={draftFilters.voice_keyword}
            placeholder={t(
              'module.operationsVoiceClone.filters.voiceKeywordPlaceholder',
            )}
            clearLabel={t('common.core.close')}
            onChange={value => setDraftFilter('voice_keyword', value)}
            onSubmit={applyFilters}
          />
        ),
      },
      {
        key: 'status',
        label: t('module.operationsVoiceClone.filters.status'),
        component: (
          <Select
            value={draftFilters.status || ALL_OPTION_VALUE}
            onValueChange={value =>
              setDraftFilter('status', value === ALL_OPTION_VALUE ? '' : value)
            }
          >
            <SelectTrigger className='h-9'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                value={ALL_OPTION_VALUE}
                className={FILTER_SELECT_ITEM_CLASS}
                indicatorClassName={FILTER_SELECT_INDICATOR_CLASS}
              >
                {t('common.core.all')}
              </SelectItem>
              {STATUS_VALUES.map(status => (
                <SelectItem
                  key={status}
                  value={status}
                  className={FILTER_SELECT_ITEM_CLASS}
                  indicatorClassName={FILTER_SELECT_INDICATOR_CLASS}
                >
                  {resolveStatusLabel(status)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ),
      },
      {
        key: 'course_keyword',
        label: t('module.operationsVoiceClone.filters.courseKeyword'),
        component: (
          <AdminClearableInput
            value={draftFilters.course_keyword}
            placeholder={t(
              'module.operationsVoiceClone.filters.courseKeywordPlaceholder',
            )}
            clearLabel={t('common.core.close')}
            onChange={value => setDraftFilter('course_keyword', value)}
            onSubmit={applyFilters}
          />
        ),
      },
      {
        key: 'created_time',
        label: t('module.operationsVoiceClone.filters.createdTime'),
        component: (
          <AdminDateRangeFilter
            startValue={draftFilters.start_time}
            endValue={draftFilters.end_time}
            placeholder={t(
              'module.operationsVoiceClone.filters.createdTimePlaceholder',
            )}
            resetLabel={t('module.operationsVoiceClone.filters.reset')}
            clearLabel={t('common.core.close')}
            onChange={range => {
              setDraftFilter('start_time', range.start);
              setDraftFilter('end_time', range.end);
            }}
          />
        ),
      },
      {
        key: 'billing_status',
        label: t('module.operationsVoiceClone.filters.billingStatus'),
        component: (
          <Select
            value={draftFilters.billing_status || ALL_OPTION_VALUE}
            onValueChange={value =>
              setDraftFilter(
                'billing_status',
                value === ALL_OPTION_VALUE ? '' : value,
              )
            }
          >
            <SelectTrigger className='h-9'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                value={ALL_OPTION_VALUE}
                className={FILTER_SELECT_ITEM_CLASS}
                indicatorClassName={FILTER_SELECT_INDICATOR_CLASS}
              >
                {t('common.core.all')}
              </SelectItem>
              {BILLING_STATUS_VALUES.map(status => (
                <SelectItem
                  key={status}
                  value={status}
                  className={FILTER_SELECT_ITEM_CLASS}
                  indicatorClassName={FILTER_SELECT_INDICATOR_CLASS}
                >
                  {resolveBillingStatusLabel(status)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ),
      },
      {
        key: 'failure_reason',
        label: t('module.operationsVoiceClone.filters.failureReason'),
        component: (
          <AdminClearableInput
            value={draftFilters.failure_reason}
            placeholder={t(
              'module.operationsVoiceClone.filters.failureReasonPlaceholder',
            )}
            clearLabel={t('common.core.close')}
            onChange={value => setDraftFilter('failure_reason', value)}
            onSubmit={applyFilters}
          />
        ),
      },
      {
        key: 'minimax_status_code',
        label: t('module.operationsVoiceClone.filters.minimaxStatusCode'),
        component: (
          <AdminClearableInput
            value={draftFilters.minimax_status_code}
            placeholder={t(
              'module.operationsVoiceClone.filters.minimaxStatusCodePlaceholder',
            )}
            clearLabel={t('common.core.close')}
            className='tabular-nums'
            onChange={value => setDraftFilter('minimax_status_code', value)}
            onSubmit={applyFilters}
          />
        ),
      },
    ],
    [
      applyFilters,
      draftFilters,
      resolveBillingStatusLabel,
      resolveStatusLabel,
      setDraftFilter,
      t,
      userKeywordPlaceholder,
    ],
  );

  if (!isReady) {
    return <Loading />;
  }

  return (
    <div className='flex min-h-0 flex-1 flex-col px-8 py-6'>
      <AdminBreadcrumb
        items={[{ label: t('module.operationsVoiceClone.title') }]}
      />
      <AdminTitle
        title={t('module.operationsVoiceClone.title')}
        description={t('module.operationsVoiceClone.description')}
      />

      <AdminFilter
        items={filterItems}
        expanded={filtersExpanded}
        onExpandedChange={setFiltersExpanded}
        onReset={resetFilters}
        onSearch={applyFilters}
        resetLabel={t('module.operationsVoiceClone.filters.reset')}
        searchLabel={t('module.operationsVoiceClone.filters.search')}
        expandLabel={t('common.core.expand')}
        collapseLabel={t('common.core.collapse')}
        collapsedCount={3}
        className='mb-4'
        contentClassName={filterControlClassName}
        collapsedLabelClassName={filterLabelClassName}
        expandedLabelClassName={filterLabelClassName}
        collapsedGridClassName='gap-x-6 xl:grid-cols-[repeat(3,minmax(0,325px))]'
        expandedGridClassName='gap-x-6 xl:grid-cols-[repeat(3,minmax(0,325px))]'
        surface='card'
      />

      {error ? (
        <div className='mb-4 rounded-md border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive'>
          {error}
        </div>
      ) : null}

      <AdminTableShell
        loading={loading}
        isEmpty={items.length === 0}
        emptyContent={t('module.operationsVoiceClone.empty')}
        emptyColSpan={9}
        containerClassName='min-h-0 flex-1'
        tableWrapperClassName='max-h-[calc(100vh-22rem)] overflow-auto'
        footnote={t('module.operationsVoiceClone.total', { total })}
        pagination={{
          pageIndex,
          pageCount,
          onPageChange: setPageIndex,
          prevLabel: t('module.operationsVoiceClone.pagination.prev'),
          nextLabel: t('module.operationsVoiceClone.pagination.next'),
          prevAriaLabel: t('module.operationsVoiceClone.pagination.prevAria'),
          nextAriaLabel: t('module.operationsVoiceClone.pagination.nextAria'),
          jumpInputAriaLabel: t(
            'module.operationsVoiceClone.pagination.jumpInputAria',
          ),
        }}
        table={emptyRow => (
          <Table className='table-fixed'>
            <TableHeader>
              <TableRow>
                <TableHead className='w-[170px]'>
                  {t('module.operationsVoiceClone.table.createdAt')}
                </TableHead>
                <TableHead className='w-[170px]'>
                  {t('module.operationsVoiceClone.table.updatedAt')}
                </TableHead>
                <TableHead className='w-[170px]'>
                  {t('module.operationsVoiceClone.table.owner')}
                </TableHead>
                <TableHead className='w-[260px]'>
                  {t('module.operationsVoiceClone.table.course')}
                </TableHead>
                <TableHead className='w-[260px]'>
                  {t('module.operationsVoiceClone.table.voice')}
                </TableHead>
                <TableHead className='w-[100px]'>
                  {t('module.operationsVoiceClone.table.status')}
                </TableHead>
                <TableHead className='w-[150px]'>
                  {t('module.operationsVoiceClone.table.failure')}
                </TableHead>
                <TableHead className='w-[120px]'>
                  {t('module.operationsVoiceClone.table.billing')}
                </TableHead>
                <TableHead
                  className={getAdminStickyRightHeaderClass('w-[112px]')}
                >
                  {t('module.operationsVoiceClone.table.actions')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map(item => (
                <TableRow key={item.voice_bid}>
                  <TableCell className='w-[170px] whitespace-nowrap'>
                    {formatDisplayTime(item.created_at)}
                  </TableCell>
                  <TableCell className='w-[170px] whitespace-nowrap'>
                    {formatDisplayTime(item.updated_at)}
                  </TableCell>
                  <TableCell className='w-[170px]'>
                    <div className='truncate'>{formatOwnerPrimary(item)}</div>
                    {formatOwnerSecondary(item) ? (
                      <div className='mt-1 truncate text-xs text-muted-foreground'>
                        {formatOwnerSecondary(item)}
                      </div>
                    ) : null}
                  </TableCell>
                  <TableCell className='w-[260px]'>
                    {item.shifu_bid ? (
                      <Link
                        href={`/admin/operations/${encodeURIComponent(item.shifu_bid)}`}
                        className='block truncate text-primary hover:underline'
                      >
                        {item.course_name || item.shifu_bid}
                      </Link>
                    ) : (
                      EMPTY_LABEL
                    )}
                    {item.shifu_bid ? (
                      <div className='mt-1 text-xs text-muted-foreground'>
                        {item.shifu_bid}
                      </div>
                    ) : null}
                  </TableCell>
                  <TableCell className='w-[260px]'>
                    <div className='truncate font-medium'>
                      {item.display_name || EMPTY_LABEL}
                    </div>
                    <div className='mt-1 truncate text-xs text-muted-foreground'>
                      {resolveVoiceIdentifier(item)}
                    </div>
                  </TableCell>
                  <TableCell>
                    <span
                      className={
                        item.status === 'failed'
                          ? 'text-destructive'
                          : 'text-foreground'
                      }
                    >
                      {resolveStatusLabel(item.status)}
                    </span>
                  </TableCell>
                  <TableCell className='w-[150px] truncate'>
                    {resolveFailureReasonLabel(item)}
                  </TableCell>
                  <TableCell>
                    <div>{resolveBillingStatusLabel(item.billing_status)}</div>
                    {hasPositiveCredits(item.charged_credits) ? (
                      <div className='mt-1 text-xs text-muted-foreground'>
                        {t('module.operationsVoiceClone.table.chargedCredits', {
                          credits: item.charged_credits,
                        })}
                      </div>
                    ) : null}
                  </TableCell>
                  <TableCell
                    className={getAdminStickyRightCellClass('w-[112px]')}
                  >
                    <div className='flex justify-start'>
                      <AdminRowActions
                        label={t('common.core.more')}
                        actions={[
                          {
                            key: 'detail',
                            label: t(
                              'module.operationsVoiceClone.actions.detail',
                            ),
                            onClick: () => setDetail(item),
                          },
                          {
                            key: 'copy',
                            label: t(
                              'module.operationsVoiceClone.actions.copy',
                            ),
                            onClick: () => void copyText(item.voice_bid),
                          },
                        ]}
                      />
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {emptyRow}
            </TableBody>
          </Table>
        )}
      />

      <Sheet
        open={Boolean(detail)}
        onOpenChange={open => {
          if (!open) {
            setDetail(null);
          }
        }}
      >
        <SheetContent className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[360px] md:w-[460px] lg:w-[560px]'>
          <SheetHeader className='border-b border-border px-6 py-4 pr-12'>
            <SheetTitle>
              {t('module.operationsVoiceClone.detail.title')}
            </SheetTitle>
            <SheetDescription>
              {detail?.display_name ||
                detail?.voice_id ||
                detail?.voice_bid ||
                t('module.operationsVoiceClone.detail.empty')}
            </SheetDescription>
          </SheetHeader>
          {detail ? (
            <div className='flex-1 overflow-y-auto px-6 py-5'>
              <div className='space-y-5 text-sm'>
                <DetailSection
                  title={t('module.operationsVoiceClone.detail.basic')}
                >
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.displayName')}
                    value={detail.display_name}
                  />
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.voiceId')}
                    value={resolveVoiceIdentifier(detail)}
                  />
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.owner')}
                    value={formatOwnerPrimary(detail)}
                  />
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.contact')}
                    value={formatOwnerSecondary(detail)}
                  />
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.course')}
                    value={detail.course_name}
                  />
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.courseId')}
                    value={detail.shifu_bid}
                  />
                </DetailSection>
                <DetailSection
                  title={t('module.operationsVoiceClone.detail.status')}
                >
                  <DetailRow
                    label={t('module.operationsVoiceClone.table.status')}
                    value={resolveStatusLabel(detail.status)}
                  />
                  <DetailRow
                    label={t('module.operationsVoiceClone.table.failure')}
                    value={resolveFailureReasonLabel(detail)}
                  />
                  <DetailRow
                    label={t(
                      'module.operationsVoiceClone.detail.failureDetail',
                    )}
                    value={resolveFailureDetailLabel(detail)}
                  />
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.retryCount')}
                    value={String(detail.retry_count || 0)}
                  />
                </DetailSection>
                <DetailSection
                  title={t('module.operationsVoiceClone.detail.billing')}
                >
                  <DetailRow
                    label={t(
                      'module.operationsVoiceClone.detail.billingStatus',
                    )}
                    value={resolveBillingStatusLabel(detail.billing_status)}
                  />
                  {hasPositiveCredits(detail.charged_credits) ? (
                    <DetailRow
                      label={t(
                        'module.operationsVoiceClone.detail.chargedCredits',
                      )}
                      value={detail.charged_credits}
                    />
                  ) : null}
                </DetailSection>
                <DetailSection
                  title={t('module.operationsVoiceClone.detail.audio')}
                >
                  <DetailRow
                    label={t(
                      'module.operationsVoiceClone.detail.sourceAudioDuration',
                    )}
                    value={formatDuration(detail.source_audio_duration_ms)}
                  />
                  <DetailRow
                    label={t(
                      'module.operationsVoiceClone.detail.normalizedAudioDuration',
                    )}
                    value={formatDuration(detail.normalized_audio_duration_ms)}
                  />
                  <DetailRow
                    label={t(
                      'module.operationsVoiceClone.detail.promptAudioDuration',
                    )}
                    value={formatDuration(detail.prompt_audio_duration_ms)}
                  />
                </DetailSection>
                <DetailSection
                  title={t('module.operationsVoiceClone.detail.time')}
                >
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.createdAt')}
                    value={formatDisplayTime(detail.created_at)}
                  />
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.updatedAt')}
                    value={formatDisplayTime(detail.updated_at)}
                  />
                  <DetailRow
                    label={t('module.operationsVoiceClone.detail.readyAt')}
                    value={formatDisplayTime(detail.ready_at)}
                  />
                </DetailSection>
                {detail.minimax_status_code != null ||
                detail.minimax_status_msg ||
                detail.minimax_trace_id ? (
                  <DetailSection
                    title={t('module.operationsVoiceClone.detail.minimax')}
                  >
                    <DetailRow
                      label={t(
                        'module.operationsVoiceClone.detail.minimaxStatusCode',
                      )}
                      value={
                        detail.minimax_status_code == null
                          ? ''
                          : String(detail.minimax_status_code)
                      }
                    />
                    <DetailRow
                      label={t(
                        'module.operationsVoiceClone.detail.minimaxStatusMsg',
                      )}
                      value={detail.minimax_status_msg}
                    />
                    <DetailRow
                      label={t(
                        'module.operationsVoiceClone.detail.minimaxTraceId',
                      )}
                      value={detail.minimax_trace_id}
                    />
                  </DetailSection>
                ) : null}
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className='rounded-lg border border-border p-4'>
      <h3 className='mb-3 font-medium'>{title}</h3>
      <div className='space-y-2'>{children}</div>
    </section>
  );
}

function DetailRow({ label, value }: { label: string; value?: string }) {
  return (
    <div className='grid gap-2 sm:grid-cols-[132px_minmax(0,1fr)]'>
      <div className='text-muted-foreground'>{label}</div>
      <div className='min-w-0 break-words'>{value || EMPTY_LABEL}</div>
    </div>
  );
}
