import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';
import api from '@/api';
import AdminTableShell from '@/components/admin/AdminTableShell';
import {
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/components/admin/adminTableStyles';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
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
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import type {
  AdminBillingEntitlementItem,
  BillingCustomization,
  BillingPagedResponse,
} from '@/types/billing';
import {
  buildBillingSwrKey,
  formatBillingDateTime,
  registerBillingTranslationUsage,
  resolveBillingEmptyLabel,
} from '@/lib/billing';
import { AdminBillingEntitlementDialog } from './AdminBillingEntitlementDialog';
import {
  AdminBillingIdentityCell,
  AdminBillingSectionCard,
  ADMIN_BILLING_CONFIG_STATUS_EVENT,
  applyAdminBillingOpsState,
  readAdminBillingConfigStatusMap,
  resolveAdminBillingCreatorPrimary,
  resolveAdminBillingCreatorSecondary,
  resolveAdminBillingPaginationFootnote,
  setAdminBillingConfigStatusState,
  type AdminBillingConfigStatus,
  type AdminBillingConfigStatusMap,
  type AdminBillingOpsState,
} from './AdminBillingShared';

const ADMIN_BILLING_ENTITLEMENTS_PAGE_SIZE = 10;
const BILLING_PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;
const STATUS_DOT = '●';
const INLINE_SEPARATOR = '·';

function resolveConfigStatusFallback(
  item: AdminBillingEntitlementItem,
): AdminBillingConfigStatus {
  if (item.effective_from) {
    return 'completed';
  }
  return 'pending';
}

function parseEntitlementTime(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function resolveEntitlementSortBucket(
  item: AdminBillingEntitlementItem,
): number {
  const hasManualGrant =
    item.source_type === 'manual' ||
    item.branding_enabled ||
    item.custom_domain_enabled ||
    item.custom_wechat_enabled ||
    item.custom_payment_enabled;

  if (hasManualGrant) {
    return 0;
  }

  if (item.product_bid) {
    return 1;
  }

  return 2;
}

function hasIndependentEntitlementConfig(
  item: AdminBillingEntitlementItem,
): boolean {
  return Boolean(
    item.branding_enabled ||
    item.custom_domain_enabled ||
    item.custom_wechat_enabled ||
    item.custom_payment_enabled,
  );
}

function EntitlementSummaryBadges({
  labels,
  emptyLabel,
}: {
  labels: string[];
  emptyLabel: string;
}) {
  if (!labels.length) {
    return <span className='text-sm text-slate-500'>{emptyLabel}</span>;
  }

  return (
    <div className='flex flex-wrap gap-2'>
      {labels.map(label => (
        <Badge
          key={label}
          variant='outline'
          className='border-slate-200 bg-white text-slate-700'
        >
          {label}
        </Badge>
      ))}
    </div>
  );
}

function resolveEntitlementWindowLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  locale: string,
  item: AdminBillingEntitlementItem,
): { primary: string; secondary: string } {
  const startAt =
    formatBillingDateTime(item.effective_from, locale) ||
    resolveBillingEmptyLabel(t);
  const endAt = formatBillingDateTime(item.effective_to, locale);

  if (endAt) {
    return {
      primary: t('module.billing.admin.entitlements.window.endsAt', {
        date: endAt,
      }),
      secondary: t('module.billing.admin.entitlements.window.startedAt', {
        date: startAt,
      }),
    };
  }

  return {
    primary: t('module.billing.admin.entitlements.window.activeNow'),
    secondary: t('module.billing.admin.entitlements.window.startedAt', {
      date: startAt,
    }),
  };
}

function resolveConfigStatusLabel(
  t: (key: string) => string,
  status: AdminBillingConfigStatus,
): string {
  return t(`module.billing.admin.entitlements.configStatus.${status}`);
}

function resolveConfigStatusTextClass(
  status: AdminBillingConfigStatus,
): string {
  switch (status) {
    case 'completed':
      return 'text-emerald-700';
    case 'in_progress':
      return 'text-amber-700';
    case 'exception':
      return 'text-rose-700';
    case 'pending':
      return 'text-sky-700';
    default:
      return 'text-slate-700';
  }
}

function resolveNextConfigStatus(
  status: AdminBillingConfigStatus,
): AdminBillingConfigStatus {
  switch (status) {
    case 'pending':
      return 'in_progress';
    case 'in_progress':
      return 'completed';
    case 'completed':
      return 'pending';
    case 'exception':
      return 'pending';
    default:
      return 'pending';
  }
}

function AdminBillingConfigStatusControl({
  status,
  note,
  onStatusChange,
  t,
}: {
  status: AdminBillingConfigStatus;
  note?: string;
  onStatusChange: (status: AdminBillingConfigStatus) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  const nextStatus = resolveNextConfigStatus(status);

  return (
    <div className='space-y-2'>
      <Button
        variant='ghost'
        size='sm'
        className='h-auto rounded-md px-0 py-0 text-left hover:bg-transparent'
        onClick={() => onStatusChange(nextStatus)}
      >
        <span
          className={`inline-flex items-center gap-1 px-0 py-0 text-xs font-medium transition-colors ${resolveConfigStatusTextClass(status)}`}
        >
          <span
            aria-hidden='true'
            className='text-[10px] leading-none'
          >
            {STATUS_DOT}
          </span>
          <span>{resolveConfigStatusLabel(t, status)}</span>
        </span>
      </Button>
      {note ? (
        <div className='line-clamp-2 text-xs text-slate-500'>{note}</div>
      ) : null}
    </div>
  );
}

function resolvePaymentIntegrationSummary(
  data: BillingCustomization | undefined,
  t: (key: string) => string,
): string {
  if (!data) {
    return t('module.billing.admin.entitlements.customization.loading');
  }

  const paymentIntegrations = data.integrations.filter(
    integration =>
      integration.provider !== 'wechat_oauth' &&
      integration.status !== 'unconfigured',
  );
  if (!paymentIntegrations.length) {
    return resolveBillingEmptyLabel(t);
  }
  return paymentIntegrations
    .map(
      integration =>
        `${t(`module.billing.admin.entitlements.customization.providers.${integration.provider}`)} · ${t(`module.billing.admin.entitlements.customization.integrationStatus.${integration.status}`)}`,
    )
    .join(' / ');
}

function resolveDomainSummary(
  data: BillingCustomization | undefined,
  t: (key: string) => string,
): React.ReactNode {
  if (!data) {
    return t('module.billing.admin.entitlements.customization.loading');
  }
  const domain = data.domains.items[0];
  if (!domain?.host) {
    return resolveBillingEmptyLabel(t);
  }
  return (
    <div className='min-w-0 space-y-1'>
      <div className='truncate font-medium text-slate-900'>{domain.host}</div>
      <div className='text-xs text-slate-500'>
        {t(`module.billing.domains.status.${domain.status}`)} {INLINE_SEPARATOR}{' '}
        {t(`module.billing.domains.ssl.${domain.ssl_status}`)}
      </div>
    </div>
  );
}

type RealEffectStatus =
  | 'active'
  | 'pending'
  | 'inactive'
  | 'unconfigured'
  | 'exception';

function resolveBrandingEffect(data?: BillingCustomization): RealEffectStatus {
  if (!data?.capabilities.branding) {
    return 'unconfigured';
  }
  return data.branding.logo_square_url || data.branding.logo_wide_url
    ? 'active'
    : 'pending';
}

function resolveDomainEffect(data?: BillingCustomization): RealEffectStatus {
  if (!data?.capabilities.custom_domain) {
    return 'unconfigured';
  }
  if (data.domains.items.some(item => item.is_effective)) {
    return 'active';
  }
  if (
    data.domains.items.some(
      item => item.status === 'failed' || item.ssl_status === 'failed',
    )
  ) {
    return 'exception';
  }
  return data.domains.items.length ? 'pending' : 'unconfigured';
}

function resolvePaymentEffect(data?: BillingCustomization): RealEffectStatus {
  if (!data?.capabilities.custom_payment) {
    return 'unconfigured';
  }
  const integrations = data.integrations.filter(
    item => item.provider !== 'wechat_oauth',
  );
  if (integrations.some(item => item.status === 'verified')) {
    return 'active';
  }
  if (integrations.some(item => item.status === 'failed')) {
    return 'exception';
  }
  if (integrations.some(item => item.status !== 'unconfigured')) {
    return 'pending';
  }
  return 'unconfigured';
}

function resolveConfigurationProgress(
  data: BillingCustomization | undefined,
  t: (key: string) => string,
): { label: string; detail: string; tone: string } {
  if (!data) {
    return {
      label: t('module.billing.admin.entitlements.configProgress.loading'),
      detail: '',
      tone: 'text-slate-500',
    };
  }

  const enabledItems = [
    data.capabilities.branding ? resolveBrandingEffect(data) : null,
    data.capabilities.custom_domain ? resolveDomainEffect(data) : null,
    data.capabilities.custom_payment ? resolvePaymentEffect(data) : null,
  ].filter((status): status is RealEffectStatus => Boolean(status));

  if (!enabledItems.length) {
    return {
      label: t('module.billing.admin.entitlements.configProgress.unconfigured'),
      detail: '',
      tone: 'text-slate-500',
    };
  }

  const exceptionCount = enabledItems.filter(
    status => status === 'exception',
  ).length;
  const activeCount = enabledItems.filter(status => status === 'active').length;
  const total = enabledItems.length;
  if (exceptionCount > 0) {
    return {
      label: t('module.billing.admin.entitlements.configProgress.exception'),
      detail: `${activeCount}/${total}`,
      tone: 'text-red-600',
    };
  }
  if (activeCount === total) {
    return {
      label: t('module.billing.admin.entitlements.configProgress.complete'),
      detail: `${activeCount}/${total}`,
      tone: 'text-emerald-700',
    };
  }
  if (activeCount > 0) {
    return {
      label: t('module.billing.admin.entitlements.configProgress.partial'),
      detail: `${activeCount}/${total}`,
      tone: 'text-amber-700',
    };
  }
  return {
    label: t('module.billing.admin.entitlements.configProgress.unconfigured'),
    detail: `0/${total}`,
    tone: 'text-slate-500',
  };
}

function ConfigurationProgressCell({ data }: { data?: BillingCustomization }) {
  const { t } = useTranslation();
  const progress = resolveConfigurationProgress(data, t);
  return (
    <div className='space-y-1'>
      <div className={`font-medium ${progress.tone}`}>{progress.label}</div>
      {progress.detail ? (
        <div className='text-xs text-slate-500'>{progress.detail}</div>
      ) : null}
    </div>
  );
}

function BillingLogoPreview({ data }: { data?: BillingCustomization }) {
  const { t } = useTranslation();
  const [open, setOpen] = React.useState(false);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const logos = React.useMemo(
    () =>
      [
        {
          label: t('module.billing.customization.branding.wideLogo'),
          url: data?.branding.logo_wide_url || '',
          shape: 'wide' as const,
        },
        {
          label: t('module.billing.customization.branding.squareLogo'),
          url: data?.branding.logo_square_url || '',
          shape: 'square' as const,
        },
      ].filter(item => item.url),
    [data?.branding.logo_square_url, data?.branding.logo_wide_url, t],
  );

  if (!logos.length) {
    return <>{resolveBillingEmptyLabel(t)}</>;
  }

  const safeActiveIndex = Math.min(activeIndex, logos.length - 1);
  const activeLogo = logos[safeActiveIndex];
  const goPrevious = () => {
    setActiveIndex(current => (current + logos.length - 1) % logos.length);
  };
  const goNext = () => {
    setActiveIndex(current => (current + 1) % logos.length);
  };

  return (
    <>
      <div className='flex items-center gap-2'>
        {logos.slice(0, 2).map((logo, index) => (
          <button
            key={logo.url}
            type='button'
            data-clickable='true'
            className={
              logo.shape === 'square'
                ? 'flex h-11 w-11 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50 transition-colors hover:border-blue-300'
                : 'flex h-11 w-16 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50 transition-colors hover:border-blue-300'
            }
            aria-label={t(
              'module.billing.admin.entitlements.logoPreview.open',
              {
                label: logo.label,
              },
            )}
            onClick={() => {
              setActiveIndex(index);
              setOpen(true);
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={logo.url}
              alt={logo.label}
              className='max-h-full max-w-full object-contain'
            />
          </button>
        ))}
      </div>

      <Dialog
        open={open}
        onOpenChange={setOpen}
      >
        <DialogContent className='max-w-3xl'>
          <DialogHeader>
            <DialogTitle>
              {t('module.billing.admin.entitlements.logoPreview.title')}
            </DialogTitle>
            <DialogDescription>{activeLogo.label}</DialogDescription>
          </DialogHeader>

          <div className='flex items-center gap-3'>
            <Button
              type='button'
              variant='outline'
              size='icon'
              disabled={logos.length < 2}
              aria-label={t(
                'module.billing.admin.entitlements.logoPreview.previous',
              )}
              onClick={goPrevious}
            >
              <ChevronLeft className='h-4 w-4' />
            </Button>
            <div className='flex min-h-[320px] flex-1 items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 p-6'>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={activeLogo.url}
                alt={activeLogo.label}
                className='max-h-[440px] max-w-full object-contain'
              />
            </div>
            <Button
              type='button'
              variant='outline'
              size='icon'
              disabled={logos.length < 2}
              aria-label={t(
                'module.billing.admin.entitlements.logoPreview.next',
              )}
              onClick={goNext}
            >
              <ChevronRight className='h-4 w-4' />
            </Button>
          </div>

          {logos.length > 1 ? (
            <div className='flex justify-center gap-2'>
              {logos.map((logo, index) => (
                <button
                  key={logo.url}
                  type='button'
                  data-clickable='true'
                  className={`h-2 rounded-full transition-all ${
                    index === safeActiveIndex
                      ? 'w-6 bg-blue-600'
                      : 'w-2 bg-slate-300 hover:bg-slate-400'
                  }`}
                  aria-label={logo.label}
                  onClick={() => setActiveIndex(index)}
                />
              ))}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

function AdminBillingCustomizationSummaryRow({
  creatorBid,
}: {
  creatorBid: string;
}) {
  const { t } = useTranslation();
  const { data } = useSWR<BillingCustomization>(
    buildBillingSwrKey('admin-billing-customization-row', creatorBid),
    async () =>
      (await api.getAdminBillingCustomization(
        {
          creator_bid: creatorBid,
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingCustomization,
    { revalidateOnFocus: false },
  );

  return (
    <>
      <TableCell className='w-[130px] min-w-[130px] text-slate-700'>
        <ConfigurationProgressCell data={data} />
      </TableCell>
      <TableCell className='w-[210px] min-w-[210px] text-slate-700'>
        {resolveDomainSummary(data, t)}
      </TableCell>
      <TableCell className='w-[120px] min-w-[120px] text-slate-700'>
        <BillingLogoPreview data={data} />
      </TableCell>
      <TableCell className='w-[220px] min-w-[220px] text-slate-700'>
        {resolvePaymentIntegrationSummary(data, t)}
      </TableCell>
    </>
  );
}

export function AdminBillingEntitlementsTable() {
  const { t, i18n } = useTranslation();
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [selectedItem, setSelectedItem] =
    React.useState<AdminBillingEntitlementItem | null>(null);
  const [pageIndex, setPageIndex] = React.useState(1);
  const [configStatusMap, setConfigStatusMap] =
    React.useState<AdminBillingConfigStatusMap>({});
  registerBillingTranslationUsage(t);

  React.useEffect(() => {
    setConfigStatusMap(readAdminBillingConfigStatusMap());
  }, []);

  const { data: opsState } = useSWR<AdminBillingOpsState>(
    buildBillingSwrKey('admin-billing-ops-state-entitlements'),
    async () =>
      (await api.getAdminBillingOpsState(
        {},
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as AdminBillingOpsState,
    { revalidateOnFocus: false },
  );

  React.useEffect(() => {
    if (!opsState) {
      return;
    }
    applyAdminBillingOpsState(opsState);
    setConfigStatusMap(readAdminBillingConfigStatusMap());
  }, [opsState]);

  React.useEffect(() => {
    const handleConfigStatusChange = () => {
      setConfigStatusMap(readAdminBillingConfigStatusMap());
    };
    window.addEventListener(
      ADMIN_BILLING_CONFIG_STATUS_EVENT,
      handleConfigStatusChange,
    );
    return () => {
      window.removeEventListener(
        ADMIN_BILLING_CONFIG_STATUS_EVENT,
        handleConfigStatusChange,
      );
    };
  }, []);
  const { data: entitlementsCountPage } = useSWR<
    BillingPagedResponse<AdminBillingEntitlementItem>
  >(
    buildBillingSwrKey('admin-billing-entitlements-count'),
    async () =>
      (await api.getAdminBillingEntitlements(
        {
          page_index: 1,
          page_size: 1,
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingEntitlementItem>,
    {
      revalidateOnFocus: false,
      keepPreviousData: true,
    },
  );

  const entitlementsTotal = Math.max(
    Number(entitlementsCountPage?.total || 0),
    0,
  );

  const { data: entitlementsPage, error } = useSWR<
    BillingPagedResponse<AdminBillingEntitlementItem>
  >(
    entitlementsCountPage
      ? buildBillingSwrKey('admin-billing-entitlements-all', entitlementsTotal)
      : null,
    async () =>
      (await api.getAdminBillingEntitlements(
        {
          page_index: 1,
          page_size: Math.max(entitlementsTotal, 1),
        },
        BILLING_PASSIVE_REQUEST_CONFIG,
      )) as BillingPagedResponse<AdminBillingEntitlementItem>,
    {
      revalidateOnFocus: false,
      keepPreviousData: true,
    },
  );

  const items = React.useMemo(
    () => entitlementsPage?.items || [],
    [entitlementsPage?.items],
  );

  const configuredItems = React.useMemo(
    () => items.filter(hasIndependentEntitlementConfig),
    [items],
  );

  const sortedItems = React.useMemo(() => {
    return [...configuredItems].sort((left, right) => {
      const bucketDiff =
        resolveEntitlementSortBucket(left) -
        resolveEntitlementSortBucket(right);
      if (bucketDiff !== 0) {
        return bucketDiff;
      }

      const leftEndAt = parseEntitlementTime(left.effective_to);
      const rightEndAt = parseEntitlementTime(right.effective_to);
      if (leftEndAt && rightEndAt && leftEndAt !== rightEndAt) {
        return leftEndAt - rightEndAt;
      }
      if (leftEndAt || rightEndAt) {
        return leftEndAt ? -1 : 1;
      }

      const startDiff =
        parseEntitlementTime(right.effective_from) -
        parseEntitlementTime(left.effective_from);
      if (startDiff !== 0) {
        return startDiff;
      }

      return String(left.creator_mobile || left.creator_bid).localeCompare(
        String(right.creator_mobile || right.creator_bid),
      );
    });
  }, [configuredItems]);

  const total = sortedItems.length;
  const pageCount = total
    ? Math.ceil(total / ADMIN_BILLING_ENTITLEMENTS_PAGE_SIZE)
    : 1;
  const safePageIndex = Math.min(pageIndex, pageCount);
  const pagedItems = sortedItems.slice(
    (safePageIndex - 1) * ADMIN_BILLING_ENTITLEMENTS_PAGE_SIZE,
    safePageIndex * ADMIN_BILLING_ENTITLEMENTS_PAGE_SIZE,
  );

  React.useEffect(() => {
    if (pageIndex !== safePageIndex) {
      setPageIndex(safePageIndex);
    }
  }, [pageIndex, safePageIndex]);

  return (
    <AdminBillingSectionCard
      title={t('module.billing.admin.entitlements.title')}
      description={t('module.billing.admin.entitlements.description')}
      error={error ? t('module.billing.admin.entitlements.loadError') : null}
      actions={
        <Button
          type='button'
          className='shrink-0'
          onClick={() => {
            setSelectedItem(null);
            setDialogOpen(true);
          }}
        >
          {t('module.billing.admin.entitlements.grant.open')}
        </Button>
      }
      disableContentShell
    >
      <AdminTableShell
        loading={!entitlementsPage && !error}
        isEmpty={!sortedItems.length}
        emptyContent={t('module.billing.admin.entitlements.empty')}
        emptyColSpan={9}
        stickyActionEmpty={{
          contentColSpan: 8,
          actionClassName: getAdminStickyRightCellClass(
            'w-[112px] min-w-[112px]',
          ),
        }}
        pagination={{
          pageIndex: safePageIndex,
          pageCount,
          onPageChange: setPageIndex,
          prevLabel: t('module.dashboard.pagination.prev'),
          nextLabel: t('module.dashboard.pagination.next'),
          prevAriaLabel: t('module.dashboard.pagination.prev'),
          nextAriaLabel: t('module.dashboard.pagination.next'),
        }}
        footnote={resolveAdminBillingPaginationFootnote(
          t,
          safePageIndex,
          pageCount,
          total,
        )}
        table={emptyRow => (
          <Table className='min-w-[1400px]'>
            <TableHeader>
              <TableRow>
                <TableHead className='w-[170px] min-w-[170px]'>
                  {t('module.billing.admin.entitlements.table.creator')}
                </TableHead>
                <TableHead className='w-[210px] min-w-[210px]'>
                  {t('module.billing.admin.entitlements.table.features')}
                </TableHead>
                <TableHead className='w-[130px] min-w-[130px]'>
                  {t('module.billing.admin.entitlements.table.configProgress')}
                </TableHead>
                <TableHead className='w-[210px] min-w-[210px]'>
                  {t('module.billing.admin.entitlements.table.domain')}
                </TableHead>
                <TableHead className='w-[120px] min-w-[120px]'>
                  {t('module.billing.admin.entitlements.table.logo')}
                </TableHead>
                <TableHead className='w-[220px] min-w-[220px]'>
                  {t('module.billing.admin.entitlements.table.payment')}
                </TableHead>
                <TableHead className='w-[150px] min-w-[150px]'>
                  {t('module.billing.admin.entitlements.table.status')}
                </TableHead>
                <TableHead className='w-[180px] min-w-[180px]'>
                  {t('module.billing.admin.entitlements.table.window')}
                </TableHead>
                <TableHead
                  className={getAdminStickyRightHeaderClass(
                    'w-[112px] min-w-[112px] text-center',
                  )}
                >
                  {t('module.billing.admin.entitlements.table.actions')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {pagedItems.map(item => {
                const brandLabels = [
                  item.branding_enabled
                    ? t('module.billing.entitlements.flags.branding')
                    : '',
                  item.custom_domain_enabled
                    ? t('module.billing.entitlements.flags.customDomain')
                    : '',
                ].filter(Boolean);
                const paymentLabels = [
                  item.custom_payment_enabled
                    ? t('module.billing.entitlements.flags.customPayment')
                    : '',
                ].filter(Boolean);
                const windowLabel = resolveEntitlementWindowLabel(
                  t,
                  i18n.language,
                  item,
                );
                const configRecord = configStatusMap[item.creator_bid];
                const configStatus =
                  configRecord?.status || resolveConfigStatusFallback(item);

                return (
                  <TableRow key={`${item.creator_bid}-${item.source_kind}`}>
                    <TableCell className='w-[170px] min-w-[170px] font-medium text-slate-900'>
                      <AdminBillingIdentityCell
                        primary={resolveAdminBillingCreatorPrimary(item)}
                        secondary={resolveAdminBillingCreatorSecondary(t, item)}
                      />
                    </TableCell>
                    <TableCell className='w-[210px] min-w-[210px]'>
                      <EntitlementSummaryBadges
                        labels={[...brandLabels, ...paymentLabels]}
                        emptyLabel={t(
                          'module.billing.admin.entitlements.notEnabled',
                        )}
                      />
                    </TableCell>
                    <AdminBillingCustomizationSummaryRow
                      creatorBid={item.creator_bid}
                    />
                    <TableCell className='w-[160px] min-w-[160px]'>
                      <AdminBillingConfigStatusControl
                        status={configStatus}
                        note={configRecord?.note}
                        t={t}
                        onStatusChange={nextStatus => {
                          setConfigStatusMap(current => {
                            const next = {
                              ...current,
                              [item.creator_bid]: {
                                status: nextStatus,
                                note: current[item.creator_bid]?.note || '',
                              },
                            };
                            void setAdminBillingConfigStatusState(
                              item.creator_bid,
                              next[item.creator_bid],
                            );
                            return next;
                          });
                        }}
                      />
                    </TableCell>
                    <TableCell className='w-[190px] min-w-[190px] text-slate-700'>
                      <div className='space-y-1.5'>
                        <div className='font-medium text-slate-900'>
                          {windowLabel.primary}
                        </div>
                        <div className='text-sm text-slate-500'>
                          {configStatus === 'exception'
                            ? configRecord?.note ||
                              t(
                                'module.billing.admin.entitlements.statusReason.exceptionDefault',
                              )
                            : configStatus === 'pending'
                              ? t(
                                  'module.billing.admin.entitlements.statusReason.inactive',
                                )
                              : configStatus === 'in_progress'
                                ? t(
                                    'module.billing.admin.entitlements.statusReason.inProgress',
                                  )
                                : windowLabel.secondary}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell
                      className={getAdminStickyRightCellClass(
                        'w-[112px] min-w-[112px] text-center',
                      )}
                    >
                      <Button
                        type='button'
                        variant='ghost'
                        size='sm'
                        className='h-auto px-0 py-0 text-sm font-semibold text-[#2563EB] hover:bg-transparent hover:text-[#1D4ED8]'
                        onClick={() => {
                          setSelectedItem(item);
                          setDialogOpen(true);
                        }}
                      >
                        {t(
                          'module.billing.admin.entitlements.actions.viewDetail',
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      />

      <AdminBillingEntitlementDialog
        open={dialogOpen}
        initialItem={selectedItem}
        initialConfigRecord={
          selectedItem ? configStatusMap[selectedItem.creator_bid] : null
        }
        onOpenChange={setDialogOpen}
      />
    </AdminBillingSectionCard>
  );
}
