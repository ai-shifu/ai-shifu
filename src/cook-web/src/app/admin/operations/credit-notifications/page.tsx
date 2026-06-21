'use client';

import React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { toast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import useOperatorGuard from '../useOperatorGuard';
import type {
  AdminOperationCreditNotificationDryRunResponse,
  AdminOperationCreditNotificationItem,
  AdminOperationCreditNotificationListResponse,
  AdminOperationCreditNotificationOverview,
  AdminOperationCreditNotificationPolicy,
  AdminOperationCreditNotificationPolicyResolvedLists,
  AdminOperationCreditNotificationRequeueResponse,
  AdminOperationCreditNotificationTemplateListResponse,
  AdminOperationCreditNotificationTemplateOption,
  AdminOperationCreditNotificationTemplateSyncResponse,
} from '../operation-credit-notification-types';
import { CreditNotificationConfigTab } from './CreditNotificationConfigTab';
import { CreditNotificationRecordsTab } from './CreditNotificationRecordsTab';
import { getTemplateOptionsForType } from './CreditNotificationTypeConfigCard';
import {
  clonePolicy,
  createDefaultFilters,
  createDefaultPolicy,
  CREDIT_NOTIFICATION_TABS_LIST_CLASSNAME,
  CREDIT_NOTIFICATION_TABS_TRIGGER_CLASSNAME,
  DEFAULT_TAB,
  EMPTY_LABEL,
  type ErrorState,
  type KnownNotificationType,
  normalizePolicy,
  type NotificationOverviewCardKey,
  NOTIFICATION_TYPES,
  normalizeTab,
  PAGE_SIZE,
  type NotificationFilters,
  type PageTab,
} from './creditNotificationUtils';
import { useCreditNotificationDryRun } from './useCreditNotificationDryRun';
import { useCreditNotificationTemplateSyncState } from './useCreditNotificationTemplateSyncState';

const normalizeResolvedPolicyLists = (
  payload: unknown,
): AdminOperationCreditNotificationPolicyResolvedLists => {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return {};
  }
  const resolvedLists = (payload as { resolved_lists?: unknown })
    .resolved_lists;
  if (
    !resolvedLists ||
    typeof resolvedLists !== 'object' ||
    Array.isArray(resolvedLists)
  ) {
    return {};
  }
  return resolvedLists as AdminOperationCreditNotificationPolicyResolvedLists;
};

export default function AdminOperationCreditNotificationsPage() {
  const { t } = useTranslation();
  const { isReady } = useOperatorGuard();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTabFromUrl = React.useMemo(
    () => normalizeTab(searchParams.get('tab')),
    [searchParams],
  );
  const [activeTab, setActiveTab] = React.useState<PageTab>(activeTabFromUrl);
  const [items, setItems] = React.useState<
    AdminOperationCreditNotificationItem[]
  >([]);
  const [draftFilters, setDraftFilters] =
    React.useState<NotificationFilters>(createDefaultFilters);
  const [appliedFilters, setAppliedFilters] =
    React.useState<NotificationFilters>(createDefaultFilters);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [pageCount, setPageCount] = React.useState(0);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [overview, setOverview] =
    React.useState<AdminOperationCreditNotificationOverview>({
      total: 0,
      pending: 0,
      sent: 0,
      failed: 0,
      skipped: 0,
    });
  const [activeOverviewCardKey, setActiveOverviewCardKey] =
    React.useState<NotificationOverviewCardKey | null>(null);
  const [recordsError, setRecordsError] = React.useState<ErrorState | null>(
    null,
  );
  const [policy, setPolicy] =
    React.useState<AdminOperationCreditNotificationPolicy>(createDefaultPolicy);
  const [configError, setConfigError] = React.useState('');
  const [configLoaded, setConfigLoaded] = React.useState(false);
  const [configLoading, setConfigLoading] = React.useState(false);
  const [templateOptions, setTemplateOptions] = React.useState<
    AdminOperationCreditNotificationTemplateOption[]
  >([]);
  const [templateListSource, setTemplateListSource] = React.useState<
    'provider' | 'local' | ''
  >('');
  const [templateListError, setTemplateListError] = React.useState('');
  const [savedPolicy, setSavedPolicy] =
    React.useState<AdminOperationCreditNotificationPolicy>(createDefaultPolicy);
  const [resolvedLists, setResolvedLists] =
    React.useState<AdminOperationCreditNotificationPolicyResolvedLists>({});
  const [pendingNavigation, setPendingNavigation] = React.useState<
    { type: 'tab'; tab: PageTab } | { type: 'href'; href: string } | null
  >(null);
  const requestIdRef = React.useRef(0);
  const configLoadStartedRef = React.useRef(false);
  const isConfigDirty = React.useMemo(
    () => JSON.stringify(policy) !== JSON.stringify(savedPolicy),
    [policy, savedPolicy],
  );

  React.useEffect(() => {
    setActiveTab(activeTabFromUrl);
  }, [activeTabFromUrl]);

  const updateTab = React.useCallback(
    (nextTab: PageTab) => {
      if (activeTab === 'config' && nextTab !== 'config' && isConfigDirty) {
        setPendingNavigation({ type: 'tab', tab: nextTab });
        return;
      }
      setActiveTab(nextTab);
      const nextParams = new URLSearchParams(searchParams.toString());
      if (nextTab === DEFAULT_TAB) {
        nextParams.delete('tab');
      } else {
        nextParams.set('tab', nextTab);
      }
      const nextQuery = nextParams.toString();
      router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, {
        scroll: false,
      });
    },
    [activeTab, isConfigDirty, pathname, router, searchParams],
  );

  const resolveTypeLabel = React.useCallback(
    (value: string) =>
      t(
        `module.operationsCreditNotifications.type.${value}`,
        value || EMPTY_LABEL,
      ),
    [t],
  );

  const resolveDeliveryStatusLabel = React.useCallback(
    (value: string) =>
      t(
        `module.operationsCreditNotifications.deliveryStatus.${value}`,
        value || EMPTY_LABEL,
      ),
    [t],
  );

  const resolveSkipReasonLabel = React.useCallback(
    (value: string) =>
      t(
        `module.operationsCreditNotifications.skipReason.${value}`,
        value || EMPTY_LABEL,
      ),
    [t],
  );

  const updatePolicy = React.useCallback(
    (updater: (draft: AdminOperationCreditNotificationPolicy) => void) => {
      setPolicy(currentPolicy => {
        const nextPolicy = clonePolicy(currentPolicy);
        updater(nextPolicy);
        return nextPolicy;
      });
    },
    [],
  );

  const { dryRunError, dryRunResult, runDryRun } =
    useCreditNotificationDryRun(t);
  const {
    clearTemplateSyncResult,
    syncTemplate,
    templateSyncError,
    templateSyncLoading,
    templateSyncResults,
  } = useCreditNotificationTemplateSyncState({
    policyTypes: policy.types,
    setTemplateOptions,
    t,
  });

  const fetchConfig = React.useCallback(async () => {
    const response = await api.getAdminOperationCreditNotificationConfig({});
    const nextPolicy = normalizePolicy(response);
    setPolicy(nextPolicy);
    setSavedPolicy(clonePolicy(nextPolicy));
    setResolvedLists(normalizeResolvedPolicyLists(response));
    setConfigLoaded(true);
    setConfigError('');
  }, []);

  const fetchTemplateOptions = React.useCallback(async () => {
    try {
      const response = (await api.getAdminOperationCreditNotificationTemplates(
        {},
      )) as AdminOperationCreditNotificationTemplateListResponse;
      setTemplateOptions(response.items || []);
      setTemplateListSource(response.source || '');
      setTemplateListError(
        response.provider_available ? '' : response.error_code,
      );
    } catch (requestError) {
      const resolvedError = requestError as ErrorWithCode;
      setTemplateOptions([]);
      setTemplateListSource('');
      setTemplateListError(resolvedError.message || 'template_list_failed');
    }
  }, []);

  const fetchOverview = React.useCallback(async () => {
    const response = (await api.getAdminOperationCreditNotificationsOverview(
      {},
    )) as AdminOperationCreditNotificationOverview;
    setOverview({
      total: response.total || 0,
      pending: response.pending || 0,
      sent: response.sent || 0,
      failed: response.failed || 0,
      skipped: response.skipped || 0,
    });
  }, []);

  const fetchRecords = React.useCallback(
    async (targetPage: number, nextFilters: NotificationFilters) => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      setLoading(true);
      setRecordsError(null);
      try {
        const response = (await api.getAdminOperationCreditNotifications({
          page_index: targetPage,
          page_size: PAGE_SIZE,
          creator_keyword: nextFilters.creator_keyword.trim(),
          notification_type: nextFilters.notification_type.trim(),
          status: nextFilters.status.trim(),
          delivery_status: nextFilters.delivery_status.trim(),
          skip_reason:
            nextFilters.delivery_status.trim() === 'not_sent'
              ? nextFilters.skip_reason.trim()
              : '',
          source_type: nextFilters.source_type.trim(),
          start_time: nextFilters.start_time.trim(),
          end_time: nextFilters.end_time.trim(),
        })) as AdminOperationCreditNotificationListResponse;
        if (requestId !== requestIdRef.current) {
          return;
        }
        setItems(response.items || []);
        setPageIndex(response.page || targetPage);
        setPageCount(response.page_count || 0);
        setTotal(response.total || 0);
      } catch (requestError) {
        if (requestId !== requestIdRef.current) {
          return;
        }
        const resolvedError = requestError as ErrorWithCode;
        setRecordsError({
          message:
            resolvedError.message ||
            t('module.operationsCreditNotifications.loadError'),
          code: resolvedError.code,
        });
        setItems([]);
        setPageCount(0);
        setTotal(0);
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [t],
  );

  const loadConfigResources = React.useCallback(async () => {
    if (configLoadStartedRef.current) {
      return;
    }
    configLoadStartedRef.current = true;
    setConfigLoading(true);
    setConfigError('');
    try {
      await Promise.all([fetchConfig(), fetchTemplateOptions()]);
    } catch (requestError) {
      configLoadStartedRef.current = false;
      const resolvedError = requestError as ErrorWithCode;
      setConfigLoaded(false);
      setConfigError(
        resolvedError.message ||
          t('module.operationsCreditNotifications.config.loadFailed'),
      );
    } finally {
      setConfigLoading(false);
    }
  }, [fetchConfig, fetchTemplateOptions, t]);

  React.useEffect(() => {
    if (!isReady) {
      return;
    }
    const initialFilters = createDefaultFilters();
    void Promise.all([
      fetchOverview().catch(() => {
        setOverview({ total: 0, pending: 0, sent: 0, failed: 0, skipped: 0 });
      }),
      fetchRecords(1, initialFilters),
    ]);
  }, [fetchOverview, fetchRecords, isReady]);

  React.useEffect(() => {
    if (!isReady || activeTab !== 'config') {
      return;
    }
    void loadConfigResources();
  }, [activeTab, isReady, loadConfigResources]);

  const updateDraftFilter = React.useCallback(
    (field: keyof NotificationFilters, value: string) => {
      setDraftFilters(current => ({
        ...current,
        [field]: value,
        ...(field === 'delivery_status' && value !== 'not_sent'
          ? { skip_reason: '' }
          : {}),
      }));
    },
    [],
  );

  const searchRecords = React.useCallback(() => {
    const nextFilters = { ...draftFilters };
    setActiveOverviewCardKey(null);
    setAppliedFilters(nextFilters);
    setPageIndex(1);
    void fetchRecords(1, nextFilters);
  }, [draftFilters, fetchRecords]);

  const applyOverviewFilter = React.useCallback(
    (cardKey: NotificationOverviewCardKey) => {
      const statusByCard: Record<NotificationOverviewCardKey, string> = {
        total: '',
        pending: 'pending',
        sent: 'sent',
        failed: 'failed',
        skipped: 'not_sent',
      };
      const nextFilters = {
        ...draftFilters,
        status: '',
        delivery_status: statusByCard[cardKey],
        skip_reason: '',
      };
      setActiveOverviewCardKey(cardKey === 'total' ? null : cardKey);
      setDraftFilters(nextFilters);
      setAppliedFilters(nextFilters);
      setPageIndex(1);
      void fetchRecords(1, nextFilters);
    },
    [draftFilters, fetchRecords],
  );

  const clearOverviewFilter = React.useCallback(() => {
    applyOverviewFilter('total');
  }, [applyOverviewFilter]);

  const resetRecords = React.useCallback(() => {
    const nextFilters = createDefaultFilters();
    setActiveOverviewCardKey(null);
    setDraftFilters(nextFilters);
    setAppliedFilters(nextFilters);
    setPageIndex(1);
    void fetchRecords(1, nextFilters);
  }, [fetchRecords]);

  const saveConfig = React.useCallback(async () => {
    if (!configLoaded) {
      setConfigError(
        t('module.operationsCreditNotifications.config.loadRequired'),
      );
      return false;
    }
    try {
      const policyToSave = clonePolicy(policy);
      NOTIFICATION_TYPES.forEach(notificationType => {
        if (policyToSave.types[notificationType].template_code.trim()) {
          return;
        }
        const recommendedTemplate = getTemplateOptionsForType(
          templateOptions,
          notificationType,
        )[0];
        if (recommendedTemplate) {
          policyToSave.types[notificationType].template_code =
            recommendedTemplate.template_code;
        }
      });
      const response =
        await api.updateAdminOperationCreditNotificationConfig(policyToSave);
      const nextPolicy = normalizePolicy(response);
      setPolicy(nextPolicy);
      setSavedPolicy(clonePolicy(nextPolicy));
      setResolvedLists(normalizeResolvedPolicyLists(response));
      setConfigLoaded(true);
      setConfigError('');
      toast({
        title: t('module.operationsCreditNotifications.config.saved'),
      });
      return true;
    } catch (requestError) {
      const resolvedError = requestError as ErrorWithCode;
      setConfigError(
        resolvedError.message ||
          t('module.operationsCreditNotifications.config.invalidConfig'),
      );
      return false;
    }
  }, [configLoaded, policy, t, templateOptions]);

  const proceedPendingNavigation = React.useCallback(
    (target: NonNullable<typeof pendingNavigation>) => {
      if (target.type === 'tab') {
        setActiveTab(target.tab);
        const nextParams = new URLSearchParams(searchParams.toString());
        if (target.tab === DEFAULT_TAB) {
          nextParams.delete('tab');
        } else {
          nextParams.set('tab', target.tab);
        }
        const nextQuery = nextParams.toString();
        router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, {
          scroll: false,
        });
        return;
      }
      router.push(target.href, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const discardPendingChanges = React.useCallback(() => {
    if (!pendingNavigation) {
      return;
    }
    const target = pendingNavigation;
    setPolicy(clonePolicy(savedPolicy));
    setConfigError('');
    setPendingNavigation(null);
    proceedPendingNavigation(target);
  }, [pendingNavigation, proceedPendingNavigation, savedPolicy]);

  const saveAndProceed = React.useCallback(async () => {
    if (!pendingNavigation) {
      return;
    }
    const target = pendingNavigation;
    const saved = await saveConfig();
    if (!saved) {
      return;
    }
    setPendingNavigation(null);
    proceedPendingNavigation(target);
  }, [pendingNavigation, proceedPendingNavigation, saveConfig]);

  React.useEffect(() => {
    if (!(activeTab === 'config' && isConfigDirty)) {
      return undefined;
    }
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [activeTab, isConfigDirty]);

  React.useEffect(() => {
    if (!(activeTab === 'config' && isConfigDirty)) {
      return undefined;
    }
    const handleDocumentClick = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      const target = event.target as Element | null;
      const anchor = target?.closest<HTMLAnchorElement>('a[href]');
      if (!anchor) {
        return;
      }
      const hrefAttribute = anchor.getAttribute('href') || '';
      if (
        !hrefAttribute ||
        hrefAttribute.startsWith('#') ||
        anchor.target === '_blank'
      ) {
        return;
      }
      const nextUrl = new URL(hrefAttribute, window.location.href);
      if (nextUrl.origin !== window.location.origin) {
        return;
      }
      const currentPath = `${window.location.pathname}${window.location.search}`;
      const nextPath = `${nextUrl.pathname}${nextUrl.search}`;
      if (nextPath === currentPath) {
        return;
      }
      event.preventDefault();
      setPendingNavigation({ type: 'href', href: nextPath });
    };
    document.addEventListener('click', handleDocumentClick, true);
    return () =>
      document.removeEventListener('click', handleDocumentClick, true);
  }, [activeTab, isConfigDirty]);

  const dryRun = React.useCallback(async () => {
    await runDryRun(draftFilters.notification_type);
  }, [draftFilters.notification_type, runDryRun]);

  const requeue = React.useCallback(
    async (notificationBid: string) => {
      try {
        const response = (await api.requeueAdminOperationCreditNotification({
          notification_bid: notificationBid,
        })) as AdminOperationCreditNotificationRequeueResponse;
        if (!response.enqueued) {
          toast({
            title: t(
              'module.operationsCreditNotifications.messages.requeueFailed',
            ),
            description:
              response.message ||
              response.status ||
              t('common.core.unknownError'),
          });
          return;
        }
        toast({
          title: t('module.operationsCreditNotifications.messages.requeueDone'),
        });
        await Promise.all([
          fetchRecords(pageIndex, appliedFilters),
          fetchOverview().catch(() => undefined),
        ]);
      } catch (requestError) {
        const resolvedError = requestError as ErrorWithCode;
        toast({
          title: t(
            'module.operationsCreditNotifications.messages.requeueFailed',
          ),
          description: resolvedError.message || t('common.core.unknownError'),
        });
      }
    },
    [appliedFilters, fetchOverview, fetchRecords, pageIndex, t],
  );

  const handlePageChange = React.useCallback(
    (nextPage: number) => {
      setPageIndex(nextPage);
      void fetchRecords(nextPage, appliedFilters);
    },
    [appliedFilters, fetchRecords],
  );

  if (!isReady) {
    return <Loading />;
  }

  return (
    <div className='flex h-full min-h-0 flex-col p-0'>
      <AdminBreadcrumb
        items={[{ label: t('module.operationsCreditNotifications.title') }]}
      />
      <Tabs
        value={activeTab}
        className='flex min-h-0 flex-1 flex-col overflow-hidden'
        onValueChange={value => updateTab(value as PageTab)}
      >
        <AdminTitle
          title={t('module.operationsCreditNotifications.title')}
          description={t('module.operationsCreditNotifications.subtitle')}
          tabs={
            <TabsList
              className={CREDIT_NOTIFICATION_TABS_LIST_CLASSNAME}
              data-testid='admin-credit-notification-tabs'
            >
              <TabsTrigger
                value='records'
                className={CREDIT_NOTIFICATION_TABS_TRIGGER_CLASSNAME}
              >
                {t('module.operationsCreditNotifications.tabs.records')}
              </TabsTrigger>
              <TabsTrigger
                value='config'
                className={CREDIT_NOTIFICATION_TABS_TRIGGER_CLASSNAME}
              >
                {t('module.operationsCreditNotifications.tabs.config')}
              </TabsTrigger>
            </TabsList>
          }
        />

        <TabsContent
          value='records'
          className='mt-0 min-h-0 flex-1 overflow-auto pr-1'
        >
          <CreditNotificationRecordsTab
            items={items}
            loading={loading}
            error={recordsError}
            total={total}
            overview={overview}
            activeOverviewCardKey={activeOverviewCardKey}
            pageIndex={pageIndex}
            pageCount={pageCount}
            draftFilters={draftFilters}
            updateDraftFilter={updateDraftFilter}
            searchRecords={searchRecords}
            resetRecords={resetRecords}
            applyOverviewFilter={applyOverviewFilter}
            clearOverviewFilter={clearOverviewFilter}
            handlePageChange={handlePageChange}
            requeue={requeue}
            resolveDeliveryStatusLabel={resolveDeliveryStatusLabel}
            resolveSkipReasonLabel={resolveSkipReasonLabel}
            resolveTypeLabel={resolveTypeLabel}
          />
        </TabsContent>

        <TabsContent
          value='config'
          className='mt-0 min-h-0 flex-1 overflow-hidden'
        >
          <CreditNotificationConfigTab
            policy={policy}
            configLoaded={configLoaded}
            configLoading={configLoading}
            configError={configError}
            dryRunResult={dryRunResult}
            dryRunError={dryRunError}
            templateSyncError={templateSyncError}
            templateSyncResults={templateSyncResults}
            templateSyncLoading={templateSyncLoading}
            templateOptions={templateOptions}
            templateListSource={templateListSource}
            templateListError={templateListError}
            resolvedLists={resolvedLists}
            updatePolicy={updatePolicy}
            syncTemplate={syncTemplate}
            dryRun={dryRun}
            saveConfig={saveConfig}
            clearTemplateSyncResult={clearTemplateSyncResult}
            resolveTypeLabel={resolveTypeLabel}
          />
        </TabsContent>
      </Tabs>
      <AlertDialog
        open={Boolean(pendingNavigation)}
        onOpenChange={open => {
          if (!open) {
            setPendingNavigation(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogCancel
            aria-label={t(
              'module.operationsCreditNotifications.config.unsavedDialog.cancel',
            )}
            className='absolute right-4 top-4 mt-0 h-8 w-8 rounded-full border-0 p-0 text-muted-foreground shadow-none hover:bg-muted hover:text-foreground'
          >
            <X className='h-4 w-4' />
          </AlertDialogCancel>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t(
                'module.operationsCreditNotifications.config.unsavedDialog.title',
              )}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t(
                'module.operationsCreditNotifications.config.unsavedDialog.description',
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className='gap-2 sm:justify-end sm:space-x-0'>
            <AlertDialogAction
              type='button'
              className='border border-input bg-white text-muted-foreground shadow-sm hover:bg-muted hover:text-foreground'
              onClick={discardPendingChanges}
            >
              {t(
                'module.operationsCreditNotifications.config.unsavedDialog.discard',
              )}
            </AlertDialogAction>
            <AlertDialogAction
              type='button'
              onClick={event => {
                event.preventDefault();
                void saveAndProceed();
              }}
            >
              {t(
                'module.operationsCreditNotifications.config.unsavedDialog.save',
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
