'use client';

import React from 'react';
import { Plus } from 'lucide-react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
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
import { toast } from '@/hooks/useToast';
import {
  formatBillingDateTime,
  formatBillingPrice,
  resolveBillingEmptyLabel,
} from '@/lib/billing';
import type {
  AdminBillingProviderPriceMapping,
  AdminBillingProviderPriceProduct,
  AdminBillingProviderPricesPage,
  AdminBillingProviderPriceValidationResult,
} from '@/types/billing';
import { resolveAdminBillingProductName } from '@/components/billing/AdminBillingShared';

const PASSIVE_REQUEST_CONFIG = { skipErrorToast: true } as const;
const ALL_PRODUCTS = '__all__';
const ALL_STATUSES = '__all__';

type DraftMappingForm = {
  product_bid: string;
  provider_product_id: string;
  provider_price_id: string;
};

const DEFAULT_FORM: DraftMappingForm = {
  product_bid: '',
  provider_product_id: '',
  provider_price_id: '',
};

function statusClass(status: string): string {
  if (status === 'active' || status === 'healthy') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (status === 'invalid' || status === 'missing') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }
  if (status === 'retired') {
    return 'border-slate-200 bg-slate-100 text-slate-600';
  }
  return 'border-amber-200 bg-amber-50 text-amber-700';
}

function resolveProductStatus(
  mapping?: AdminBillingProviderPriceMapping | null,
): string {
  if (!mapping) {
    return 'missing';
  }
  if (mapping.status_label === 'active' && !mapping.validation_error) {
    return 'active';
  }
  return String(mapping.status_label || 'missing');
}

function formatIssues(issues: Array<Record<string, string>> = []): string {
  return issues
    .map(issue => issue.code || issue.message || '')
    .filter(Boolean)
    .join(', ');
}

function resolveProductGroupLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  product: AdminBillingProviderPriceProduct,
): string {
  if (product.product_type === 'topup') {
    return t('module.billing.admin.providerPrices.groups.topups');
  }
  const tier = String(product.plan_tier || '').trim();
  return tier
    ? t('module.billing.admin.providerPrices.groups.planTier', { tier })
    : t('module.billing.admin.providerPrices.groups.plans');
}

function resolveProductBillingMeta(
  t: (key: string, options?: Record<string, unknown>) => string,
  product: AdminBillingProviderPriceProduct,
): string {
  if (product.product_type === 'topup') {
    return t('module.billing.admin.providerPrices.productType.topup');
  }
  if (product.billing_interval === 'year') {
    return t('module.billing.admin.providerPrices.interval.year', {
      count: product.billing_interval_count || 1,
    });
  }
  return t('module.billing.admin.providerPrices.interval.month', {
    count: product.billing_interval_count || 1,
  });
}

function resolveProductDescription(
  t: (key: string, options?: Record<string, unknown>) => string,
  product: AdminBillingProviderPriceProduct,
): string {
  const normalizedKey = String(product.description || '').trim();
  if (!normalizedKey) {
    return '';
  }
  const translated = t(normalizedKey);
  return translated && translated !== normalizedKey ? translated : '';
}

function buildProductOptionLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  product: AdminBillingProviderPriceProduct,
): string {
  return `${resolveAdminBillingProductName(
    t,
    product.display_name,
    product.product_code,
  )} · ${resolveProductBillingMeta(t, product)}`;
}

export function AdminBillingProviderPricesPanel() {
  const { t, i18n } = useTranslation();
  const [productFilter, setProductFilter] = React.useState(ALL_PRODUCTS);
  const [statusFilter, setStatusFilter] = React.useState(ALL_STATUSES);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [form, setForm] = React.useState<DraftMappingForm>(DEFAULT_FORM);
  const [actionLoading, setActionLoading] = React.useState('');
  const clearLabel = t('common.core.close');

  const { data, error, isLoading, mutate } =
    useSWR<AdminBillingProviderPricesPage>(
      ['admin-package-management'],
      async () =>
        (await api.getAdminBillingProviderPrices(
          {},
          PASSIVE_REQUEST_CONFIG,
        )) as AdminBillingProviderPricesPage,
      { revalidateOnFocus: false },
    );

  const products = React.useMemo(() => data?.products || [], [data?.products]);
  const productOptions = React.useMemo(
    () =>
      products.filter(
        product =>
          product.product_type === 'plan' || product.product_type === 'topup',
      ),
    [products],
  );
  const visibleProducts = React.useMemo(() => {
    return products.filter(product => {
      if (
        productFilter !== ALL_PRODUCTS &&
        product.product_bid !== productFilter
      ) {
        return false;
      }
      if (statusFilter === ALL_STATUSES) {
        return true;
      }
      const activeMapping = data?.active_by_product?.[product.product_bid];
      const latestMapping =
        activeMapping || data?.history_by_product?.[product.product_bid]?.[0];
      return latestMapping?.status_label === statusFilter;
    });
  }, [
    data?.active_by_product,
    data?.history_by_product,
    productFilter,
    products,
    statusFilter,
  ]);

  const groupedProducts = React.useMemo(() => {
    const groups: Array<{
      label: string;
      items: AdminBillingProviderPriceProduct[];
    }> = [];
    for (const product of visibleProducts) {
      const label = resolveProductGroupLabel(t, product);
      const lastGroup = groups.at(-1);
      if (lastGroup?.label === label) {
        lastGroup.items.push(product);
      } else {
        groups.push({ label, items: [product] });
      }
    }
    return groups;
  }, [visibleProducts, t]);

  const summaryItems = React.useMemo(() => {
    const activeCount = products.filter(
      product => data?.active_by_product?.[product.product_bid],
    ).length;
    const needsActionCount = products.length - activeCount;
    const invalidCount = products.filter(product => {
      const mapping = data?.active_by_product?.[product.product_bid];
      return Boolean(
        mapping?.validation_error || mapping?.status_label === 'invalid',
      );
    }).length;
    return [
      {
        key: 'total',
        label: t('module.billing.admin.providerPrices.summary.total'),
        value: products.length,
      },
      {
        key: 'active',
        label: t('module.billing.admin.providerPrices.summary.active'),
        value: activeCount,
      },
      {
        key: 'needsAction',
        label: t('module.billing.admin.providerPrices.summary.needsAction'),
        value: needsActionCount,
      },
      {
        key: 'invalid',
        label: t('module.billing.admin.providerPrices.summary.invalid'),
        value: invalidCount,
      },
    ];
  }, [data?.active_by_product, products, t]);

  const resetFilters = React.useCallback(() => {
    setProductFilter(ALL_PRODUCTS);
    setStatusFilter(ALL_STATUSES);
  }, []);

  const openConfigDialog = React.useCallback(
    (product?: AdminBillingProviderPriceProduct) => {
      const activeMapping = product
        ? data?.active_by_product?.[product.product_bid]
        : null;
      setForm({
        product_bid: product?.product_bid || '',
        provider_product_id: activeMapping?.provider_product_id || '',
        provider_price_id: activeMapping?.provider_price_id || '',
      });
      setDialogOpen(true);
    },
    [data?.active_by_product],
  );

  const runAction = React.useCallback(
    async (
      action: 'validate' | 'activate' | 'retire',
      mapping: AdminBillingProviderPriceMapping,
    ) => {
      if (
        (action === 'activate' || action === 'retire') &&
        !window.confirm(
          t(`module.billing.admin.providerPrices.confirm.${action}`),
        )
      ) {
        return;
      }
      const loadingKey = `${action}:${mapping.provider_price_bid}`;
      setActionLoading(loadingKey);
      try {
        const params = { provider_price_bid: mapping.provider_price_bid };
        const result =
          action === 'validate'
            ? ((await api.validateAdminBillingProviderPrice(
                params,
              )) as AdminBillingProviderPriceValidationResult)
            : action === 'activate'
              ? ((await api.activateAdminBillingProviderPrice(
                  params,
                )) as AdminBillingProviderPriceValidationResult)
              : await api.retireAdminBillingProviderPrice(params);
        const validationResult =
          result as AdminBillingProviderPriceValidationResult;
        const issueText =
          validationResult?.valid === false
            ? formatIssues(validationResult.errors)
            : formatIssues(validationResult.warnings);
        const actionFailedValidation =
          action === 'activate' && validationResult?.valid === false;
        toast({
          title: t(
            `module.billing.admin.providerPrices.toast.${action}${
              actionFailedValidation ? 'Failed' : 'Success'
            }`,
          ),
          description: issueText || undefined,
          variant: actionFailedValidation ? 'destructive' : undefined,
        });
        await mutate();
      } catch (err) {
        toast({
          title: t(`module.billing.admin.providerPrices.toast.${action}Failed`),
          description: err instanceof Error ? err.message : undefined,
          variant: 'destructive',
        });
      } finally {
        setActionLoading('');
      }
    },
    [mutate, t],
  );

  const submitDraft = React.useCallback(async () => {
    setActionLoading('create');
    try {
      await api.createAdminBillingProviderPrice({
        product_bid: form.product_bid,
        provider_product_id: form.provider_product_id.trim(),
        provider_price_id: form.provider_price_id.trim(),
      });
      toast({
        title: t('module.billing.admin.providerPrices.toast.createSuccess'),
      });
      setDialogOpen(false);
      await mutate();
    } catch (err) {
      toast({
        title: t('module.billing.admin.providerPrices.toast.createFailed'),
        description: err instanceof Error ? err.message : undefined,
        variant: 'destructive',
      });
    } finally {
      setActionLoading('');
    }
  }, [form, mutate, t]);

  const renderEnvironment = (
    mapping?: AdminBillingProviderPriceMapping | null,
  ) => {
    if (!mapping) {
      return resolveBillingEmptyLabel(t);
    }
    return mapping.livemode
      ? t('module.billing.admin.providerPrices.mode.live')
      : t('module.billing.admin.providerPrices.mode.test');
  };

  const filterItems = React.useMemo(
    () => [
      {
        key: 'product',
        label: t('module.billing.admin.providerPrices.filters.product'),
        component: (
          <Select
            value={productFilter}
            onValueChange={setProductFilter}
          >
            <SelectTrigger className='h-9'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_PRODUCTS}>
                {t('module.billing.admin.providerPrices.filters.allProducts')}
              </SelectItem>
              {productOptions.map(product => (
                <SelectItem
                  key={product.product_bid}
                  value={product.product_bid}
                >
                  {buildProductOptionLabel(t, product)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ),
        contentClassName: 'min-w-[260px]',
      },
      {
        key: 'status',
        label: t('module.billing.admin.providerPrices.filters.status'),
        component: (
          <Select
            value={statusFilter}
            onValueChange={setStatusFilter}
          >
            <SelectTrigger className='h-9'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_STATUSES}>
                {t('module.billing.admin.providerPrices.status.all')}
              </SelectItem>
              {['draft', 'active', 'invalid', 'retired'].map(status => (
                <SelectItem
                  key={status}
                  value={status}
                >
                  {t(`module.billing.admin.providerPrices.status.${status}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ),
        contentClassName: 'min-w-[160px]',
      },
    ],
    [productFilter, productOptions, statusFilter, t],
  );

  return (
    <>
      <div className='mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4'>
        {summaryItems.map(item => (
          <div
            key={item.key}
            className='rounded-xl border border-border bg-white px-4 py-3 shadow-sm'
          >
            <div className='text-xs text-muted-foreground'>{item.label}</div>
            <div className='mt-1 text-2xl font-semibold text-foreground'>
              {item.value}
            </div>
          </div>
        ))}
      </div>

      <div className='mb-4 rounded-xl border border-border bg-white p-5 shadow-sm'>
        <div className='flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between'>
          <AdminFilter
            items={filterItems}
            expanded={false}
            onExpandedChange={() => undefined}
            onReset={resetFilters}
            onSearch={() => undefined}
            showActions={false}
            showToggle={false}
            resetLabel={t('module.order.filters.reset')}
            searchLabel={t('module.order.filters.search')}
            expandLabel={t('common.core.expand')}
            collapseLabel={t('common.core.collapse')}
            collapsedCount={2}
            className='min-w-0 bg-transparent'
            contentClassName='min-w-0'
            labelClassName='w-20 text-right'
            collapsedGridClassName='gap-x-5 xl:grid-cols-[minmax(0,360px)_minmax(0,260px)]'
            labelColon
          />
          <div className='flex shrink-0 justify-end gap-2'>
            <Button
              type='button'
              size='sm'
              variant='outline'
              className='h-9 px-4'
              onClick={resetFilters}
            >
              {t('module.order.filters.reset')}
            </Button>
            <Button
              type='button'
              size='sm'
              className='h-9 px-4'
              onClick={() => openConfigDialog()}
            >
              <Plus className='mr-1 h-4 w-4' />
              {t('module.billing.admin.providerPrices.actions.create')}
            </Button>
          </div>
        </div>
      </div>

      {error ? (
        <div className='mb-4 rounded-md border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive'>
          {t('module.billing.admin.providerPrices.loadError')}
        </div>
      ) : null}

      <AdminTableShell
        loading={isLoading && !data}
        isEmpty={!visibleProducts.length}
        emptyContent={t('module.billing.admin.providerPrices.empty')}
        emptyColSpan={7}
        containerClassName='min-h-0 flex-1'
        tableWrapperClassName='max-h-[calc(100vh-22rem)] overflow-auto'
        table={emptyRow => (
          <Table className='min-w-[1120px] table-fixed'>
            <TableHeader>
              <TableRow>
                <TableHead className='w-[280px]'>
                  {t('module.billing.admin.providerPrices.table.product')}
                </TableHead>
                <TableHead className='w-[140px]'>
                  {t('module.billing.admin.providerPrices.table.localPrice')}
                </TableHead>
                <TableHead className='w-[180px]'>
                  {t('module.billing.admin.providerPrices.table.stripePrice')}
                </TableHead>
                <TableHead className='w-[120px]'>
                  {t('module.billing.admin.providerPrices.table.status')}
                </TableHead>
                <TableHead className='w-[100px]'>
                  {t('module.billing.admin.providerPrices.table.environment')}
                </TableHead>
                <TableHead className='w-[170px]'>
                  {t('module.billing.admin.providerPrices.table.validatedAt')}
                </TableHead>
                <TableHead className='w-[230px] text-right'>
                  {t('module.billing.admin.providerPrices.table.actions')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {groupedProducts.map(group => (
                <React.Fragment key={group.label}>
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className='bg-muted/40 py-2 text-xs font-medium text-muted-foreground'
                    >
                      {group.label}
                    </TableCell>
                  </TableRow>
                  {group.items.map(product => {
                    const activeMapping =
                      data?.active_by_product?.[product.product_bid];
                    const history =
                      data?.history_by_product?.[product.product_bid] || [];
                    const latestMapping = activeMapping || history[0] || null;
                    const status = resolveProductStatus(activeMapping);
                    const productDescription = resolveProductDescription(
                      t,
                      product,
                    );
                    return (
                      <TableRow key={product.product_bid}>
                        <TableCell className='align-top'>
                          <div className='space-y-2'>
                            <div className='font-medium text-foreground'>
                              {resolveAdminBillingProductName(
                                t,
                                product.display_name,
                                product.product_code,
                              )}
                            </div>
                            <div className='flex flex-wrap gap-1.5'>
                              <Badge
                                variant='outline'
                                className='border-slate-200 bg-slate-50 text-slate-600'
                              >
                                {product.product_type === 'topup'
                                  ? t(
                                      'module.billing.admin.providerPrices.productType.topup',
                                    )
                                  : t(
                                      'module.billing.admin.providerPrices.productType.plan',
                                    )}
                              </Badge>
                              <Badge
                                variant='outline'
                                className='border-slate-200 bg-slate-50 text-slate-600'
                              >
                                {resolveProductBillingMeta(t, product)}
                              </Badge>
                            </div>
                            {productDescription ? (
                              <div className='line-clamp-2 text-xs text-muted-foreground'>
                                {productDescription}
                              </div>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell className='align-top text-sm'>
                          {formatBillingPrice(
                            product.price_amount,
                            product.currency,
                            i18n.language,
                          )}
                        </TableCell>
                        <TableCell className='align-top text-sm'>
                          {latestMapping ? (
                            <div className='space-y-1'>
                              <div className='font-medium text-foreground'>
                                {formatBillingPrice(
                                  latestMapping.unit_amount,
                                  latestMapping.currency,
                                  i18n.language,
                                )}
                              </div>
                              <div className='truncate text-xs text-muted-foreground'>
                                {latestMapping.provider_price_id}
                              </div>
                            </div>
                          ) : (
                            <span className='text-muted-foreground'>
                              {resolveBillingEmptyLabel(t)}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className='align-top'>
                          <Badge
                            variant='outline'
                            className={statusClass(status)}
                          >
                            {t(
                              `module.billing.admin.providerPrices.health.${status}`,
                            )}
                          </Badge>
                          {activeMapping?.validation_error ? (
                            <div className='mt-2 line-clamp-2 text-xs text-amber-700'>
                              {activeMapping.validation_error}
                            </div>
                          ) : null}
                        </TableCell>
                        <TableCell className='align-top text-sm text-muted-foreground'>
                          {renderEnvironment(latestMapping)}
                        </TableCell>
                        <TableCell className='align-top text-sm text-muted-foreground'>
                          {latestMapping?.validated_at
                            ? formatBillingDateTime(
                                latestMapping.validated_at,
                                i18n.language,
                              )
                            : resolveBillingEmptyLabel(t)}
                        </TableCell>
                        <TableCell className='align-top'>
                          <div className='flex justify-end gap-2'>
                            <Button
                              type='button'
                              variant='outline'
                              size='sm'
                              onClick={() => openConfigDialog(product)}
                            >
                              {t(
                                'module.billing.admin.providerPrices.actions.configure',
                              )}
                            </Button>
                            {latestMapping ? (
                              <Button
                                type='button'
                                variant='outline'
                                size='sm'
                                disabled={
                                  actionLoading ===
                                  `validate:${latestMapping.provider_price_bid}`
                                }
                                onClick={() =>
                                  runAction('validate', latestMapping)
                                }
                              >
                                {t(
                                  'module.billing.admin.providerPrices.actions.validate',
                                )}
                              </Button>
                            ) : null}
                            {latestMapping &&
                            latestMapping.status_label !== 'active' ? (
                              <Button
                                type='button'
                                variant='outline'
                                size='sm'
                                onClick={() =>
                                  runAction('activate', latestMapping)
                                }
                              >
                                {t(
                                  'module.billing.admin.providerPrices.actions.activate',
                                )}
                              </Button>
                            ) : null}
                            {activeMapping ? (
                              <Button
                                type='button'
                                variant='outline'
                                size='sm'
                                onClick={() =>
                                  runAction('retire', activeMapping)
                                }
                              >
                                {t(
                                  'module.billing.admin.providerPrices.actions.retire',
                                )}
                              </Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        )}
      />

      <Dialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      >
        <DialogContent className='max-w-xl'>
          <DialogHeader>
            <DialogTitle>
              {t('module.billing.admin.providerPrices.dialog.title')}
            </DialogTitle>
            <DialogDescription>
              {t('module.billing.admin.providerPrices.dialog.description')}
            </DialogDescription>
          </DialogHeader>
          <div className='grid gap-4 py-2'>
            <div className='space-y-2'>
              <Label>
                {t('module.billing.admin.providerPrices.fields.product')}
              </Label>
              <Select
                value={form.product_bid}
                onValueChange={value =>
                  setForm(current => ({ ...current, product_bid: value }))
                }
              >
                <SelectTrigger>
                  <SelectValue
                    placeholder={t(
                      'module.billing.admin.providerPrices.fields.productPlaceholder',
                    )}
                  />
                </SelectTrigger>
                <SelectContent>
                  {productOptions.map(product => (
                    <SelectItem
                      key={product.product_bid}
                      value={product.product_bid}
                    >
                      {buildProductOptionLabel(t, product)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <FieldInput
              label={t('module.billing.admin.providerPrices.fields.productId')}
              value={form.provider_product_id}
              clearLabel={clearLabel}
              onChange={value =>
                setForm(current => ({ ...current, provider_product_id: value }))
              }
            />
            <FieldInput
              label={t('module.billing.admin.providerPrices.fields.priceId')}
              value={form.provider_price_id}
              clearLabel={clearLabel}
              onChange={value =>
                setForm(current => ({ ...current, provider_price_id: value }))
              }
            />
            <div className='rounded-lg bg-muted/50 px-3 py-2 text-xs leading-5 text-muted-foreground'>
              {t('module.billing.admin.providerPrices.dialog.autoDetectHint')}
            </div>
          </div>
          <DialogFooter>
            <Button
              type='button'
              variant='outline'
              onClick={() => setDialogOpen(false)}
            >
              {t('module.billing.admin.providerPrices.actions.cancel')}
            </Button>
            <Button
              type='button'
              disabled={actionLoading === 'create'}
              onClick={submitDraft}
            >
              {t('module.billing.admin.providerPrices.actions.saveDraft')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function FieldInput({
  label,
  value,
  clearLabel,
  onChange,
}: {
  label: string;
  value: string;
  clearLabel: string;
  onChange: (value: string) => void;
}) {
  const id = React.useId();
  return (
    <div className='space-y-2'>
      <Label htmlFor={id}>{label}</Label>
      <AdminClearableInput
        id={id}
        value={value}
        placeholder={label}
        clearLabel={clearLabel}
        onChange={onChange}
      />
    </div>
  );
}
