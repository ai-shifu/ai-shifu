'use client';

import React from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { Textarea } from '@/components/ui/Textarea';
import { toast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import useOperatorGuard from '../useOperatorGuard';
import type {
  AdminOperationCreditNotificationDryRunResponse,
  AdminOperationCreditNotificationItem,
  AdminOperationCreditNotificationListResponse,
  AdminOperationCreditNotificationRequeueResponse,
} from '../operation-credit-notification-types';

type NotificationFilters = {
  creator_bid: string;
  mobile: string;
  notification_type: string;
  status: string;
  source_bid: string;
};

type ErrorState = { message: string; code?: number };

const PAGE_SIZE = 20;
const EMPTY_LABEL = '--';

const createDefaultFilters = (): NotificationFilters => ({
  creator_bid: '',
  mobile: '',
  notification_type: '',
  status: '',
  source_bid: '',
});

const stringifyConfig = (value: unknown) =>
  JSON.stringify(value ?? {}, null, 2);

const formatValue = (value?: string | null) => {
  const normalized = String(value || '').trim();
  return normalized || EMPTY_LABEL;
};

export default function AdminOperationCreditNotificationsPage() {
  const { t } = useTranslation();
  const { isReady } = useOperatorGuard();
  const [items, setItems] = React.useState<
    AdminOperationCreditNotificationItem[]
  >([]);
  const [filters, setFilters] =
    React.useState<NotificationFilters>(createDefaultFilters);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [pageCount, setPageCount] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<ErrorState | null>(null);
  const [configText, setConfigText] = React.useState('{}');
  const [configError, setConfigError] = React.useState('');
  const [dryRunResult, setDryRunResult] =
    React.useState<AdminOperationCreditNotificationDryRunResponse | null>(null);
  const requestIdRef = React.useRef(0);

  const resolveTypeLabel = React.useCallback(
    (value: string) =>
      t(
        `module.operationsCreditNotifications.type.${value}`,
        value || EMPTY_LABEL,
      ),
    [t],
  );

  const resolveStatusLabel = React.useCallback(
    (value: string) =>
      t(
        `module.operationsCreditNotifications.status.${value}`,
        value || EMPTY_LABEL,
      ),
    [t],
  );

  const fetchConfig = React.useCallback(async () => {
    const response = await api.getAdminOperationCreditNotificationConfig({});
    setConfigText(stringifyConfig(response));
    setConfigError('');
  }, []);

  const fetchRecords = React.useCallback(
    async (targetPage: number, nextFilters: NotificationFilters) => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      setLoading(true);
      setError(null);
      try {
        const response = (await api.getAdminOperationCreditNotifications({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          creator_bid: nextFilters.creator_bid.trim(),
          mobile: nextFilters.mobile.trim(),
          notification_type: nextFilters.notification_type.trim(),
          status: nextFilters.status.trim(),
          source_bid: nextFilters.source_bid.trim(),
        })) as AdminOperationCreditNotificationListResponse;
        if (requestId !== requestIdRef.current) {
          return;
        }
        setItems(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 0);
      } catch (requestError) {
        if (requestId !== requestIdRef.current) {
          return;
        }
        const resolvedError = requestError as ErrorWithCode;
        setError({
          message:
            resolvedError.message ||
            t('module.operationsCreditNotifications.loadError'),
          code: resolvedError.code,
        });
        setItems([]);
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
    fetchConfig().catch(() => {
      setConfigText('{}');
    });
    void fetchRecords(1, filters);
  }, [fetchConfig, fetchRecords, filters, isReady]);

  const updateFilter = React.useCallback(
    (field: keyof NotificationFilters, value: string) => {
      const nextFilters = {
        ...filters,
        [field]: value,
      };
      setFilters(nextFilters);
      setPageIndex(1);
      void fetchRecords(1, nextFilters);
    },
    [fetchRecords, filters],
  );

  const saveConfig = React.useCallback(async () => {
    try {
      const parsed = JSON.parse(configText);
      const response =
        await api.updateAdminOperationCreditNotificationConfig(parsed);
      setConfigText(stringifyConfig(response));
      setConfigError('');
      toast({
        title: t('module.operationsCreditNotifications.config.saved'),
      });
    } catch (requestError) {
      if (requestError instanceof SyntaxError) {
        setConfigError(
          t('module.operationsCreditNotifications.config.invalidJson'),
        );
        return;
      }
      const resolvedError = requestError as ErrorWithCode;
      setConfigError(resolvedError.message || t('common.core.submitFailed'));
    }
  }, [configText, t]);

  const dryRun = React.useCallback(async () => {
    try {
      const response = (await api.dryRunAdminOperationCreditNotifications({
        notification_type: filters.notification_type.trim(),
        creator_bid: filters.creator_bid.trim(),
      })) as AdminOperationCreditNotificationDryRunResponse;
      setDryRunResult(response);
    } catch (requestError) {
      const resolvedError = requestError as ErrorWithCode;
      setError({
        message: resolvedError.message || t('common.core.submitFailed'),
        code: resolvedError.code,
      });
    }
  }, [filters.creator_bid, filters.notification_type, t]);

  const requeue = React.useCallback(
    async (notificationBid: string) => {
      const response = (await api.requeueAdminOperationCreditNotification({
        notification_bid: notificationBid,
      })) as AdminOperationCreditNotificationRequeueResponse;
      if (response.enqueued) {
        toast({
          title: t('module.operationsCreditNotifications.messages.requeueDone'),
        });
      }
      void fetchRecords(pageIndex, filters);
    },
    [fetchRecords, filters, pageIndex, t],
  );

  if (!isReady) {
    return <Loading />;
  }

  return (
    <div className='flex h-full min-h-0 flex-col gap-5 p-0'>
      <div>
        <h1 className='text-2xl font-semibold text-gray-900'>
          {t('module.operationsCreditNotifications.title')}
        </h1>
        <p className='mt-1 text-sm text-gray-500'>
          {t('module.operationsCreditNotifications.subtitle')}
        </p>
      </div>

      <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]'>
        <section className='min-w-0 rounded-md border border-gray-200 bg-white p-4'>
          <div className='mb-4 flex flex-wrap items-end gap-3'>
            <Input
              className='h-9 w-44'
              value={filters.creator_bid}
              placeholder={t(
                'module.operationsCreditNotifications.filters.creatorBid',
              )}
              onChange={event =>
                updateFilter('creator_bid', event.target.value)
              }
            />
            <Input
              className='h-9 w-36'
              value={filters.mobile}
              placeholder={t(
                'module.operationsCreditNotifications.filters.mobile',
              )}
              onChange={event => updateFilter('mobile', event.target.value)}
            />
            <Input
              className='h-9 w-44'
              value={filters.notification_type}
              placeholder={t(
                'module.operationsCreditNotifications.filters.notificationType',
              )}
              onChange={event =>
                updateFilter('notification_type', event.target.value)
              }
            />
            <Input
              className='h-9 w-40'
              value={filters.status}
              placeholder={t(
                'module.operationsCreditNotifications.filters.status',
              )}
              onChange={event => updateFilter('status', event.target.value)}
            />
            <Input
              className='h-9 w-44'
              value={filters.source_bid}
              placeholder={t(
                'module.operationsCreditNotifications.filters.sourceBid',
              )}
              onChange={event => updateFilter('source_bid', event.target.value)}
            />
            <Button
              type='button'
              variant='outline'
              size='sm'
              onClick={() => fetchRecords(pageIndex, filters)}
            >
              <RefreshCw className='mr-2 h-4 w-4' />
              {t('module.operationsCreditNotifications.actions.refresh')}
            </Button>
            <Button
              type='button'
              size='sm'
              onClick={dryRun}
            >
              {t('module.operationsCreditNotifications.actions.dryRun')}
            </Button>
          </div>

          {error ? (
            <ErrorDisplay
              errorCode={error.code || 0}
              errorMessage={error.message}
            />
          ) : null}

          {loading ? (
            <Loading />
          ) : (
            <Table containerClassName='max-h-[560px] rounded-md border border-gray-200'>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    {t(
                      'module.operationsCreditNotifications.table.notification',
                    )}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.creator')}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.source')}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.template')}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.error')}
                  </TableHead>
                  <TableHead>
                    {t('module.operationsCreditNotifications.table.createdAt')}
                  </TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.length === 0 ? (
                  <TableEmpty colSpan={7}>
                    {t('module.operationsCreditNotifications.empty')}
                  </TableEmpty>
                ) : (
                  items.map(item => (
                    <TableRow key={item.notification_bid}>
                      <TableCell className='min-w-[220px]'>
                        <div className='font-medium text-gray-900'>
                          {resolveTypeLabel(item.notification_type)}
                        </div>
                        <Badge
                          variant={
                            item.status === 'failed_provider'
                              ? 'destructive'
                              : 'secondary'
                          }
                          className='mt-1'
                        >
                          {resolveStatusLabel(item.status)}
                        </Badge>
                        <div className='mt-1 text-xs text-gray-500'>
                          {formatValue(item.notification_bid)}
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[180px]'>
                        <div>{formatValue(item.creator_bid)}</div>
                        <div className='text-xs text-gray-500'>
                          {formatValue(item.mobile_snapshot)}
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[220px]'>
                        <div>{formatValue(item.source_type)}</div>
                        <div className='text-xs text-gray-500'>
                          {formatValue(item.source_bid)}
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[160px]'>
                        {formatValue(item.template_code)}
                      </TableCell>
                      <TableCell className='min-w-[220px]'>
                        <div>{formatValue(item.error_code)}</div>
                        <div className='text-xs text-gray-500'>
                          {formatValue(item.error_message)}
                        </div>
                      </TableCell>
                      <TableCell className='min-w-[180px]'>
                        {formatValue(item.created_at)}
                      </TableCell>
                      <TableCell>
                        <Button
                          type='button'
                          variant='outline'
                          size='sm'
                          disabled={item.status !== 'failed_provider'}
                          onClick={() => requeue(item.notification_bid)}
                        >
                          {t(
                            'module.operationsCreditNotifications.actions.requeue',
                          )}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}

          <AdminPagination
            className='mt-4 justify-end'
            pageIndex={pageIndex}
            pageCount={pageCount}
            onPageChange={nextPage => {
              setPageIndex(nextPage);
              void fetchRecords(nextPage, filters);
            }}
            prevLabel={t('module.order.paginationPrev', 'Previous')}
            nextLabel={t('module.order.paginationNext', 'Next')}
            prevAriaLabel={t('module.order.paginationPrev', 'Previous')}
            nextAriaLabel={t('module.order.paginationNext', 'Next')}
            hideWhenSinglePage
          />
        </section>

        <aside className='flex min-w-0 flex-col gap-4'>
          <section className='rounded-md border border-gray-200 bg-white p-4'>
            <h2 className='text-base font-semibold text-gray-900'>
              {t('module.operationsCreditNotifications.config.title')}
            </h2>
            <p className='mt-1 text-sm text-gray-500'>
              {t('module.operationsCreditNotifications.config.description')}
            </p>
            <Textarea
              className='mt-3 min-h-[360px] font-mono text-xs'
              value={configText}
              onChange={event => setConfigText(event.target.value)}
            />
            {configError ? (
              <p className='mt-2 text-sm text-red-600'>{configError}</p>
            ) : null}
            <Button
              type='button'
              className='mt-3'
              onClick={saveConfig}
            >
              {t('module.operationsCreditNotifications.actions.applyConfig')}
            </Button>
          </section>

          <section className='rounded-md border border-gray-200 bg-white p-4'>
            <h2 className='text-base font-semibold text-gray-900'>
              {t('module.operationsCreditNotifications.dryRun.title')}
            </h2>
            {dryRunResult ? (
              <pre className='mt-3 max-h-[260px] overflow-auto rounded bg-gray-50 p-3 text-xs text-gray-700'>
                {JSON.stringify(dryRunResult, null, 2)}
              </pre>
            ) : (
              <p className='mt-2 text-sm text-gray-500'>
                {t('module.operationsCreditNotifications.dryRun.empty')}
              </p>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
