import React, { useCallback, useMemo, useState } from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Skeleton } from '@/components/ui/Skeleton';
import { toast } from '@/hooks/useToast';
import { useBillingEntitlements } from '@/hooks/useBillingData';
import {
  formatBillingDateTime,
  registerBillingTranslationUsage,
} from '@/lib/billing';
import type {
  BillingDomainBinding,
  BillingDomainBindingsResponse,
  BillingDomainBindingMutationResult,
  CreatorBrandingConfig,
} from '@/types/billing';

type BrandingFieldProps = {
  label: string;
  value: string | null;
};

type DomainAction = 'bind' | 'verify' | 'disable';

function BrandingField({ label, value }: BrandingFieldProps) {
  return (
    <div className='rounded-2xl border border-slate-200 bg-slate-50/80 p-4'>
      <p className='text-xs font-medium uppercase tracking-[0.2em] text-slate-400'>
        {label}
      </p>
      <p className='mt-2 break-all text-sm text-slate-700'>{value || '—'}</p>
    </div>
  );
}

function resolveDomainStatusClass(
  status: BillingDomainBinding['status'],
): string {
  switch (status) {
    case 'verified':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700';
    case 'failed':
      return 'border-rose-200 bg-rose-50 text-rose-700';
    case 'disabled':
      return 'border-slate-200 bg-slate-100 text-slate-600';
    default:
      return 'border-amber-200 bg-amber-50 text-amber-700';
  }
}

function resolveDomainSslClass(
  sslStatus: BillingDomainBinding['ssl_status'],
): string {
  switch (sslStatus) {
    case 'issued':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700';
    case 'pending':
      return 'border-sky-200 bg-sky-50 text-sky-700';
    default:
      return 'border-slate-200 bg-slate-100 text-slate-600';
  }
}

export function BillingDomainsTab() {
  const { t, i18n } = useTranslation();
  registerBillingTranslationUsage(t);
  const {
    data: entitlements,
    error: entitlementError,
    isLoading: entitlementsLoading,
  } = useBillingEntitlements();
  const {
    data: domainBindings,
    error: domainError,
    isLoading: domainLoading,
    mutate: mutateDomainBindings,
  } = useSWR<BillingDomainBindingsResponse>(
    ['admin-billing-domain-bindings'],
    async () =>
      (await api.getAdminBillingDomainBindings(
        {},
      )) as BillingDomainBindingsResponse,
    {
      revalidateOnFocus: false,
    },
  );
  const branding = useEnvStore(
    useShallow(
      (state: EnvStoreState): CreatorBrandingConfig => ({
        logo_wide_url: state.logoWideUrl || null,
        logo_square_url: state.logoSquareUrl || null,
        favicon_url: state.faviconUrl || null,
        home_url: state.homeUrl || null,
      }),
    ),
  );
  const [host, setHost] = useState('');
  const [submittingAction, setSubmittingAction] = useState('');

  const isLoading = entitlementsLoading || domainLoading;
  const hasError = entitlementError || domainError;
  const items = domainBindings?.items || [];
  const customDomainEnabled =
    domainBindings?.custom_domain_enabled ??
    entitlements?.custom_domain_enabled ??
    false;
  const brandingEnabled = entitlements?.branding_enabled ?? false;
  const effectiveBinding = useMemo(
    () => items.find(item => item.is_effective) || null,
    [items],
  );

  const submitAction = useCallback(
    async (
      action: DomainAction,
      payload: {
        domain_binding_bid?: string;
        host?: string;
        verification_token?: string;
      },
    ) => {
      const actionKey = `${action}:${payload.domain_binding_bid || payload.host || 'creator'}`;
      setSubmittingAction(actionKey);
      try {
        const response = (await api.bindAdminBillingDomain({
          action,
          ...payload,
        })) as BillingDomainBindingMutationResult;
        await mutateDomainBindings(current => {
          if (!current) {
            return current;
          }
          const nextItems =
            action === 'bind'
              ? [
                  response.binding,
                  ...current.items.filter(
                    item =>
                      item.domain_binding_bid !==
                      response.binding.domain_binding_bid,
                  ),
                ]
              : current.items.map(item =>
                  item.domain_binding_bid ===
                  response.binding.domain_binding_bid
                    ? response.binding
                    : item,
                );
          return {
            ...current,
            items: nextItems,
          };
        }, false);

        toast({
          title: t(`module.billing.domains.feedback.${action}`),
        });
        if (action === 'bind') {
          setHost('');
        }
      } catch (error: any) {
        toast({
          title:
            error?.message || t('module.billing.domains.actions.loadError'),
          variant: 'destructive',
        });
      } finally {
        setSubmittingAction('');
      }
    },
    [mutateDomainBindings, t],
  );

  const handleBind = useCallback(async () => {
    const normalizedHost = host.trim();
    if (!normalizedHost) {
      toast({
        title: t('module.billing.domains.form.errors.hostRequired'),
        variant: 'destructive',
      });
      return;
    }
    await submitAction('bind', { host: normalizedHost });
  }, [host, submitAction, t]);

  const handleVerify = useCallback(
    async (binding: BillingDomainBinding) => {
      await submitAction('verify', {
        domain_binding_bid: binding.domain_binding_bid,
        host: binding.host,
        verification_token: binding.verification_token,
      });
    },
    [submitAction],
  );

  const handleDisable = useCallback(
    async (binding: BillingDomainBinding) => {
      await submitAction('disable', {
        domain_binding_bid: binding.domain_binding_bid,
        host: binding.host,
      });
    },
    [submitAction],
  );

  return (
    <div className='space-y-4'>
      <div className='grid gap-4 xl:grid-cols-[1.1fr_0.9fr]'>
        <Card className='border-slate-200 bg-[linear-gradient(145deg,#ffffff_0%,#f8fafc_58%,#eef6ff_100%)] shadow-[0_18px_50px_rgba(15,23,42,0.08)]'>
          <CardHeader className='space-y-3'>
            <div className='flex flex-wrap items-center justify-between gap-3'>
              <div className='space-y-2'>
                <CardTitle className='text-lg text-slate-900'>
                  {t('module.billing.domains.branding.title')}
                </CardTitle>
                <CardDescription className='leading-6 text-slate-600'>
                  {t('module.billing.domains.branding.description')}
                </CardDescription>
              </div>
              <Badge
                variant='outline'
                className={
                  brandingEnabled
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-slate-200 bg-slate-100 text-slate-600'
                }
              >
                {brandingEnabled
                  ? t('module.billing.domains.branding.enabled')
                  : t('module.billing.domains.branding.disabled')}
              </Badge>
            </div>
            <div className='rounded-2xl border border-sky-100 bg-white/85 px-4 py-3 text-sm text-slate-600'>
              {t('module.billing.domains.branding.runtimeNote')}
            </div>
          </CardHeader>
          <CardContent className='grid gap-3 md:grid-cols-2'>
            <BrandingField
              label={t('module.billing.domains.branding.fields.logoWide')}
              value={branding.logo_wide_url}
            />
            <BrandingField
              label={t('module.billing.domains.branding.fields.logoSquare')}
              value={branding.logo_square_url}
            />
            <BrandingField
              label={t('module.billing.domains.branding.fields.favicon')}
              value={branding.favicon_url}
            />
            <BrandingField
              label={t('module.billing.domains.branding.fields.homeUrl')}
              value={branding.home_url}
            />
          </CardContent>
        </Card>

        <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
          <CardHeader className='space-y-3'>
            <div className='flex flex-wrap items-center justify-between gap-3'>
              <div className='space-y-2'>
                <CardTitle className='text-lg text-slate-900'>
                  {t('module.billing.domains.settings.title')}
                </CardTitle>
                <CardDescription className='leading-6 text-slate-600'>
                  {t('module.billing.domains.settings.description')}
                </CardDescription>
              </div>
              <Badge
                variant='outline'
                className={
                  customDomainEnabled
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-slate-200 bg-slate-100 text-slate-600'
                }
              >
                {customDomainEnabled
                  ? t('module.billing.domains.settings.enabled')
                  : t('module.billing.domains.settings.disabled')}
              </Badge>
            </div>

            {effectiveBinding ? (
              <div className='rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700'>
                {t('module.billing.domains.settings.effectiveDomain', {
                  host: effectiveBinding.host,
                })}
              </div>
            ) : (
              <div className='rounded-2xl border border-dashed border-slate-200 bg-slate-50/90 px-4 py-3 text-sm text-slate-500'>
                {t('module.billing.domains.settings.noEffectiveDomain')}
              </div>
            )}
          </CardHeader>

          <CardContent className='space-y-3'>
            <div className='space-y-2'>
              <label
                htmlFor='billing-domain-host'
                className='text-sm font-medium text-slate-700'
              >
                {t('module.billing.domains.form.hostLabel')}
              </label>
              <Input
                id='billing-domain-host'
                value={host}
                placeholder={t('module.billing.domains.form.hostPlaceholder')}
                disabled={!customDomainEnabled}
                onChange={event => setHost(event.target.value)}
              />
              <p className='text-xs leading-5 text-slate-500'>
                {t('module.billing.domains.form.hostHelp')}
              </p>
            </div>

            {!customDomainEnabled ? (
              <div className='rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'>
                {t('module.billing.domains.form.capabilityBlocked')}
              </div>
            ) : null}

            <Button
              className='w-full rounded-full'
              disabled={!customDomainEnabled || !host.trim()}
              onClick={handleBind}
            >
              {submittingAction === `bind:${host.trim() || 'creator'}`
                ? t('module.billing.domains.actions.binding')
                : t('module.billing.domains.actions.bind')}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
        <CardHeader className='space-y-2'>
          <CardTitle className='text-lg text-slate-900'>
            {t('module.billing.domains.records.title')}
          </CardTitle>
          <CardDescription className='leading-6 text-slate-600'>
            {t('module.billing.domains.records.description')}
          </CardDescription>
        </CardHeader>

        <CardContent className='space-y-4'>
          {hasError ? (
            <div className='rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
              {t('module.billing.domains.actions.loadError')}
            </div>
          ) : null}

          {isLoading ? (
            <div className='space-y-3'>
              <Skeleton className='h-24 rounded-2xl' />
              <Skeleton className='h-24 rounded-2xl' />
            </div>
          ) : null}

          {!isLoading && !items.length ? (
            <div className='rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center text-sm text-slate-500'>
              {t('module.billing.domains.records.empty')}
            </div>
          ) : null}

          {!isLoading
            ? items.map(item => {
                const verifyActionKey = `verify:${item.domain_binding_bid}`;
                const disableActionKey = `disable:${item.domain_binding_bid}`;
                const verificationError =
                  typeof item.metadata?.verification_error === 'string'
                    ? item.metadata.verification_error
                    : '';

                return (
                  <div
                    key={item.domain_binding_bid}
                    className='rounded-[24px] border border-slate-200 bg-[linear-gradient(135deg,#ffffff_0%,#f8fafc_58%,#f1f5f9_100%)] p-5 shadow-[0_8px_24px_rgba(15,23,42,0.05)]'
                  >
                    <div className='flex flex-wrap items-start justify-between gap-3'>
                      <div className='space-y-2'>
                        <div className='flex flex-wrap items-center gap-2'>
                          <p className='text-base font-semibold text-slate-900'>
                            {item.host}
                          </p>
                          <Badge
                            variant='outline'
                            className={resolveDomainStatusClass(item.status)}
                          >
                            {t(`module.billing.domains.status.${item.status}`)}
                          </Badge>
                          <Badge
                            variant='outline'
                            className={resolveDomainSslClass(item.ssl_status)}
                          >
                            {t(`module.billing.domains.ssl.${item.ssl_status}`)}
                          </Badge>
                          {item.is_effective ? (
                            <Badge
                              variant='outline'
                              className='border-emerald-200 bg-emerald-50 text-emerald-700'
                            >
                              {t('module.billing.domains.records.effective')}
                            </Badge>
                          ) : null}
                        </div>
                        <p className='text-xs text-slate-500'>
                          {item.domain_binding_bid}
                        </p>
                      </div>

                      <div className='flex flex-wrap gap-2'>
                        <Button
                          variant='outline'
                          className='rounded-full'
                          disabled={
                            !customDomainEnabled ||
                            item.status === 'verified' ||
                            submittingAction === disableActionKey
                          }
                          onClick={() => handleVerify(item)}
                        >
                          {submittingAction === verifyActionKey
                            ? t('module.billing.domains.actions.verifying')
                            : t('module.billing.domains.actions.verify')}
                        </Button>
                        <Button
                          variant='outline'
                          className='rounded-full'
                          disabled={submittingAction === verifyActionKey}
                          onClick={() => handleDisable(item)}
                        >
                          {submittingAction === disableActionKey
                            ? t('module.billing.domains.actions.disabling')
                            : t('module.billing.domains.actions.disable')}
                        </Button>
                      </div>
                    </div>

                    <div className='mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4'>
                      <div className='rounded-2xl border border-slate-200 bg-white/90 p-4'>
                        <p className='text-xs font-medium uppercase tracking-[0.2em] text-slate-400'>
                          {t('module.billing.domains.records.fields.method')}
                        </p>
                        <p className='mt-2 text-sm text-slate-700'>
                          {t(
                            `module.billing.domains.verificationMethod.${item.verification_method}`,
                          )}
                        </p>
                      </div>
                      <div className='rounded-2xl border border-slate-200 bg-white/90 p-4'>
                        <p className='text-xs font-medium uppercase tracking-[0.2em] text-slate-400'>
                          {t(
                            'module.billing.domains.records.fields.lastVerified',
                          )}
                        </p>
                        <p className='mt-2 text-sm text-slate-700'>
                          {formatBillingDateTime(
                            item.last_verified_at,
                            i18n.language,
                          ) ||
                            t('module.billing.domains.records.neverVerified')}
                        </p>
                      </div>
                      <div className='rounded-2xl border border-slate-200 bg-white/90 p-4'>
                        <p className='text-xs font-medium uppercase tracking-[0.2em] text-slate-400'>
                          {t(
                            'module.billing.domains.records.fields.recordName',
                          )}
                        </p>
                        <p className='mt-2 break-all text-sm text-slate-700'>
                          {item.verification_record_name}
                        </p>
                      </div>
                      <div className='rounded-2xl border border-slate-200 bg-white/90 p-4'>
                        <p className='text-xs font-medium uppercase tracking-[0.2em] text-slate-400'>
                          {t(
                            'module.billing.domains.records.fields.recordValue',
                          )}
                        </p>
                        <p className='mt-2 break-all text-sm text-slate-700'>
                          {item.verification_record_value}
                        </p>
                      </div>
                    </div>

                    {verificationError ? (
                      <div className='mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700'>
                        {t('module.billing.domains.records.verificationError', {
                          code: verificationError,
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })
            : null}
        </CardContent>
      </Card>
    </div>
  );
}
