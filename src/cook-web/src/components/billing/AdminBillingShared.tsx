'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Badge } from '@/components/ui/Badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { resolveBillingEmptyLabel } from '@/lib/billing';
import { cn } from '@/lib/utils';

type BillingTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export type AdminBillingCreatorTarget = {
  creator_bid?: string | null;
  creator_mobile?: string | null;
  creator_nickname?: string | null;
};

export type AdminBillingConfigStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'exception';

export type AdminBillingConfigStatusRecord = {
  status: AdminBillingConfigStatus;
  note?: string;
};

export type AdminBillingConfigStatusMap = Record<
  string,
  AdminBillingConfigStatusRecord
>;

export const ADMIN_BILLING_TABS_LIST_CLASSNAME =
  'h-auto w-fit justify-start rounded-xl bg-[var(--base-muted,#F5F5F5)] p-1 text-[var(--base-muted-foreground,#737373)]';
export const ADMIN_BILLING_TABS_TRIGGER_CLASSNAME =
  'h-auto rounded-lg px-7 py-2 text-sm font-medium text-[var(--base-muted-foreground,#737373)] data-[state=active]:bg-white data-[state=active]:text-[var(--base-foreground,#0A0A0A)] data-[state=active]:shadow-sm';
export const ADMIN_BILLING_CONFIG_STATUS_EVENT =
  'admin-billing-config-status-change';

export type AdminBillingOpsState = {
  config_status?: AdminBillingConfigStatusMap;
};

let configStatusCache: AdminBillingConfigStatusMap = {};

function cloneConfigStatusMap(
  value: AdminBillingConfigStatusMap,
): AdminBillingConfigStatusMap {
  return Object.fromEntries(
    Object.entries(value).map(([key, record]) => [
      key,
      { status: record.status, note: record.note || '' },
    ]),
  );
}

function dispatchAdminBillingStateChange(
  eventName: string,
  value: Record<string, unknown>,
): void {
  if (typeof window === 'undefined') {
    return;
  }

  window.dispatchEvent(new CustomEvent(eventName, { detail: value }));
}

export function readAdminBillingConfigStatusMap(): AdminBillingConfigStatusMap {
  return cloneConfigStatusMap(configStatusCache);
}

export function applyAdminBillingOpsState(
  state?: AdminBillingOpsState | null,
): void {
  if (!state) {
    return;
  }
  if (state.config_status) {
    configStatusCache = cloneConfigStatusMap(state.config_status);
    dispatchAdminBillingStateChange(
      ADMIN_BILLING_CONFIG_STATUS_EVENT,
      configStatusCache,
    );
  }
}

export async function setAdminBillingConfigStatusState(
  creatorBid: string,
  record: AdminBillingConfigStatusRecord,
): Promise<AdminBillingConfigStatusMap> {
  const normalizedCreatorBid = String(creatorBid || '').trim();
  const previous = readAdminBillingConfigStatusMap();
  const next = cloneConfigStatusMap(previous);

  if (!normalizedCreatorBid) {
    return next;
  }

  next[normalizedCreatorBid] = {
    status: record.status,
    note: String(record.note || '').trim(),
  };
  configStatusCache = cloneConfigStatusMap(next);
  dispatchAdminBillingStateChange(
    ADMIN_BILLING_CONFIG_STATUS_EVENT,
    configStatusCache,
  );
  try {
    await api.updateAdminBillingConfigStatus({
      creator_bid: normalizedCreatorBid,
      status: record.status,
      note: record.note || '',
    });
  } catch (error) {
    configStatusCache = cloneConfigStatusMap(previous);
    dispatchAdminBillingStateChange(
      ADMIN_BILLING_CONFIG_STATUS_EVENT,
      configStatusCache,
    );
    throw error;
  }
  return next;
}

export function resolveAdminBillingCreatorPrimary(
  item: AdminBillingCreatorTarget & {
    creator_identify?: string | null;
  },
): string {
  return (
    String(item.creator_mobile || '').trim() ||
    String(item.creator_identify || '').trim() ||
    String(item.creator_bid || '').trim() ||
    ''
  );
}

export function resolveAdminBillingCreatorSecondary(
  t: BillingTranslator,
  item: AdminBillingCreatorTarget,
): string {
  return (
    String(item.creator_nickname || '').trim() ||
    t('module.user.defaultUserName')
  );
}

export function resolveAdminBillingProductName(
  t: BillingTranslator,
  productNameKey?: string | null,
  fallback?: string | null,
  options?: Record<string, unknown>,
): string {
  const normalizedKey = String(productNameKey || '').trim();
  if (normalizedKey) {
    const translated = t(normalizedKey, options);
    if (translated && translated !== normalizedKey) {
      return translated;
    }
  }

  const normalizedFallback = String(fallback || '').trim();
  return normalizedFallback || resolveBillingEmptyLabel(t);
}

export function resolveAdminBillingPaginationFootnote(
  t: BillingTranslator,
  _page: number,
  _pageCount: number,
  total: number,
): string | null {
  const normalizedTotal = Math.max(Number(total || 0), 0);
  if (normalizedTotal <= 0) {
    return null;
  }
  return t('module.billing.admin.pagination.total', {
    total: normalizedTotal,
  });
}

export function AdminBillingIdentityCell({
  primary,
  secondary,
  tertiary,
  highlight,
}: {
  primary?: string | null;
  secondary?: string | null;
  tertiary?: string | null;
  highlight?: string | null;
}) {
  const { t } = useTranslation();
  const resolvedPrimary =
    String(primary || '').trim() || resolveBillingEmptyLabel(t);
  const resolvedSecondary = String(secondary || '').trim();
  const resolvedTertiary = String(tertiary || '').trim();

  return (
    <div className='space-y-1.5'>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='font-medium text-slate-900'>{resolvedPrimary}</div>
        {highlight ? (
          <Badge
            variant='outline'
            className='border-amber-200 bg-amber-50 text-amber-700'
          >
            {highlight}
          </Badge>
        ) : null}
      </div>
      {resolvedSecondary ? (
        <div className='text-sm text-slate-500'>{resolvedSecondary}</div>
      ) : null}
      {resolvedTertiary ? (
        <div className='text-xs text-slate-500'>{resolvedTertiary}</div>
      ) : null}
    </div>
  );
}

export function AdminBillingSectionCard({
  title,
  description,
  error,
  actions,
  loading = false,
  loadingRows = 3,
  tableClassName,
  disableContentShell = false,
  children,
  footer,
}: {
  title: string;
  description?: string | null;
  error?: string | null;
  actions?: React.ReactNode;
  loading?: boolean;
  loadingRows?: number;
  tableClassName?: string;
  disableContentShell?: boolean;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='flex-row items-start justify-between gap-4 space-y-0'>
        <div className='space-y-2'>
          <CardTitle className='text-lg text-slate-900'>{title}</CardTitle>
          {description ? (
            <CardDescription className='leading-6 text-slate-600'>
              {description}
            </CardDescription>
          ) : null}
        </div>
        {actions ? <div className='shrink-0'>{actions}</div> : null}
      </CardHeader>

      <CardContent className='space-y-4'>
        {error ? (
          <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
            {error}
          </div>
        ) : null}

        {disableContentShell ? (
          children
        ) : (
          <div
            className={cn(
              'overflow-hidden rounded-[24px] border border-slate-200 bg-slate-50/60',
              tableClassName,
            )}
          >
            {loading ? (
              <div className='space-y-3 px-4 py-4'>
                {Array.from({ length: loadingRows }).map((_, index) => (
                  <Skeleton
                    key={index}
                    className='h-12 rounded-2xl'
                  />
                ))}
              </div>
            ) : (
              children
            )}
          </div>
        )}

        {footer}
      </CardContent>
    </Card>
  );
}
