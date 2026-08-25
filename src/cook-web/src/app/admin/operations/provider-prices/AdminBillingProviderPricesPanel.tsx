'use client';

import React from 'react';
import { ChevronDown, Plus } from 'lucide-react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminFilter from '@/app/admin/components/AdminFilter';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
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
  formatBillingCreditAmount,
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

type CreateMappingResult = {
  mapping?: AdminBillingProviderPriceMapping | null;
};

type ConfirmMappingAction = {
  action: 'activate' | 'retire' | 'restore';
  mapping: AdminBillingProviderPriceMapping;
  productName: string;
};

type ProductMappingRow = {
  key: string;
  product: AdminBillingProviderPriceProduct;
  mapping: AdminBillingProviderPriceMapping | null;
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

function resolveIssueLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  code: string,
): string {
  const normalizedCode = String(code || '').trim();
  if (!normalizedCode) {
    return t('module.billing.admin.providerPrices.issueMessages.unknown');
  }
  const key = `module.billing.admin.providerPrices.issueMessages.${normalizedCode}`;
  const translated = t(key);
  return translated && translated !== key ? translated : normalizedCode;
}

function formatIssues(
  t: (key: string, options?: Record<string, unknown>) => string,
  issues: Array<Record<string, string>> = [],
): string {
  return issues
    .map(issue => resolveIssueLabel(t, issue.code || issue.message || ''))
    .filter(Boolean)
    .join(', ');
}

function parseValidationIssueCodes(value?: string | null): string[] {
  const normalizedValue = String(value || '').trim();
  if (!normalizedValue) {
    return [];
  }
  try {
    const parsed = JSON.parse(normalizedValue) as unknown;
    if (Array.isArray(parsed)) {
      return parsed
        .map(item => {
          if (item && typeof item === 'object' && 'code' in item) {
            return String((item as { code?: unknown }).code || '').trim();
          }
          return '';
        })
        .filter(Boolean);
    }
  } catch {
    return [normalizedValue];
  }
  return [normalizedValue];
}

function resolveProductShortBenefit(
  t: (key: string, options?: Record<string, unknown>) => string,
  product: AdminBillingProviderPriceProduct,
): string {
  if (product.product_type === 'topup') {
    return '';
  }
  if (
    product.billing_interval === 'month' &&
    Number(product.billing_interval_count || 1) === 1
  ) {
    return t('module.billing.admin.providerPrices.billingLabel.monthly');
  }
  if (
    product.billing_interval === 'year' &&
    Number(product.billing_interval_count || 1) === 1
  ) {
    return t('module.billing.admin.providerPrices.billingLabel.yearly');
  }
  return resolveProductBillingMeta(t, product);
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
  const productName = resolveAdminBillingProductName(
    t,
    product.display_name,
    product.product_code,
    { credits: formatBillingCreditAmount(product.credit_amount) },
  );
  const shortBenefit = resolveProductShortBenefit(t, product);
  return shortBenefit ? `${productName} ${shortBenefit}` : productName;
}

function getMappingStatus(
  mapping: AdminBillingProviderPriceMapping | null,
): string {
  return mapping?.status_label || 'missing';
}

function getActiveProductMapping(
  mappings: AdminBillingProviderPriceMapping[],
): AdminBillingProviderPriceMapping | null {
  return mappings.find(mapping => mapping.status_label === 'active') || null;
}

export function AdminBillingProviderPricesPanel() {
  const { t, i18n } = useTranslation();
  const [productFilter, setProductFilter] = React.useState(ALL_PRODUCTS);
  const [statusFilter, setStatusFilter] = React.useState(ALL_STATUSES);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [form, setForm] = React.useState<DraftMappingForm>(DEFAULT_FORM);
  const [issueMapping, setIssueMapping] =
    React.useState<AdminBillingProviderPriceMapping | null>(null);
  const [confirmAction, setConfirmAction] =
    React.useState<ConfirmMappingAction | null>(null);
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
  const visibleRows = React.useMemo<ProductMappingRow[]>(() => {
    return products.flatMap<ProductMappingRow>(product => {
      if (
        productFilter !== ALL_PRODUCTS &&
        product.product_bid !== productFilter
      ) {
        return [];
      }
      const mappings = data?.history_by_product?.[product.product_bid] || [];
      if (!mappings.length) {
        return statusFilter === ALL_STATUSES || statusFilter === 'missing'
          ? [
              {
                key: `${product.product_bid}:missing`,
                product,
                mapping: null,
              },
            ]
          : [];
      }
      return mappings
        .filter(
          mapping =>
            statusFilter === ALL_STATUSES ||
            mapping.status_label === statusFilter,
        )
        .map(mapping => ({
          key: mapping.provider_price_bid,
          product,
          mapping,
        }));
    });
  }, [data?.history_by_product, productFilter, products, statusFilter]);

  const resetFilters = React.useCallback(() => {
    setProductFilter(ALL_PRODUCTS);
    setStatusFilter(ALL_STATUSES);
  }, []);

  const openConfigDialog = React.useCallback(
    (
      product?: AdminBillingProviderPriceProduct,
      mapping?: AdminBillingProviderPriceMapping | null,
    ) => {
      const productMappings = product
        ? data?.history_by_product?.[product.product_bid] || []
        : [];
      const sourceMapping = mapping || getActiveProductMapping(productMappings);
      setForm({
        product_bid: product?.product_bid || '',
        provider_product_id: sourceMapping?.provider_product_id || '',
        provider_price_id: sourceMapping?.provider_price_id || '',
      });
      setDialogOpen(true);
    },
    [data?.history_by_product],
  );

  const runAction = React.useCallback(
    async (
      action: 'validate' | 'activate' | 'retire' | 'restore',
      mapping: AdminBillingProviderPriceMapping,
    ) => {
      const loadingKey = `${action}:${mapping.provider_price_bid}`;
      setActionLoading(loadingKey);
      try {
        const params = { provider_price_bid: mapping.provider_price_bid };
        const result =
          action === 'validate'
            ? ((await api.validateAdminBillingProviderPrice(
                params,
                PASSIVE_REQUEST_CONFIG,
              )) as AdminBillingProviderPriceValidationResult)
            : action === 'activate'
              ? ((await api.activateAdminBillingProviderPrice(
                  params,
                  PASSIVE_REQUEST_CONFIG,
                )) as AdminBillingProviderPriceValidationResult)
              : action === 'restore'
                ? await api.restoreAdminBillingProviderPrice(
                    params,
                    PASSIVE_REQUEST_CONFIG,
                  )
                : await api.retireAdminBillingProviderPrice(
                    params,
                    PASSIVE_REQUEST_CONFIG,
                  );
        const validationResult =
          result as AdminBillingProviderPriceValidationResult;
        const issueText =
          validationResult?.valid === false
            ? formatIssues(t, validationResult.errors)
            : formatIssues(t, validationResult.warnings);
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

  const requestAction = React.useCallback(
    (
      action: 'validate' | 'activate' | 'retire' | 'restore',
      mapping: AdminBillingProviderPriceMapping,
      productName = '',
    ) => {
      if (action === 'validate') {
        void runAction(action, mapping);
        return;
      }
      setConfirmAction({ action, mapping, productName });
    },
    [runAction],
  );

  const canSubmitDraft = Boolean(
    form.product_bid.trim() &&
    form.provider_product_id.trim() &&
    form.provider_price_id.trim(),
  );

  const submitDraft = React.useCallback(async () => {
    if (!canSubmitDraft) {
      return;
    }
    setActionLoading('create');
    try {
      const createResult = (await api.createAdminBillingProviderPrice(
        {
          product_bid: form.product_bid,
          provider_product_id: form.provider_product_id.trim(),
          provider_price_id: form.provider_price_id.trim(),
        },
        PASSIVE_REQUEST_CONFIG,
      )) as CreateMappingResult;
      const providerPriceBid = createResult.mapping?.provider_price_bid || '';
      if (providerPriceBid) {
        try {
          const validationResult = (await api.validateAdminBillingProviderPrice(
            {
              provider_price_bid: providerPriceBid,
            },
            PASSIVE_REQUEST_CONFIG,
          )) as AdminBillingProviderPriceValidationResult;
          const issueText =
            validationResult?.valid === false
              ? formatIssues(t, validationResult.errors)
              : formatIssues(t, validationResult.warnings);
          toast({
            title: t(
              `module.billing.admin.providerPrices.toast.${
                validationResult?.valid === false
                  ? 'validateFailed'
                  : 'validateSuccess'
              }`,
            ),
            description: issueText || undefined,
            variant:
              validationResult?.valid === false ? 'destructive' : undefined,
          });
        } catch (err) {
          toast({
            title: t(
              'module.billing.admin.providerPrices.toast.validateFailed',
            ),
            description: err instanceof Error ? err.message : undefined,
            variant: 'destructive',
          });
        }
      } else {
        toast({
          title: t('module.billing.admin.providerPrices.toast.createSuccess'),
        });
      }
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
  }, [canSubmitDraft, form, mutate, t]);

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
              {['missing', 'draft', 'active', 'invalid', 'retired'].map(
                status => (
                  <SelectItem
                    key={status}
                    value={status}
                  >
                    {t(`module.billing.admin.providerPrices.status.${status}`)}
                  </SelectItem>
                ),
              )}
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
        isEmpty={!visibleRows.length}
        emptyContent={t('module.billing.admin.providerPrices.empty')}
        emptyColSpan={7}
        containerClassName='min-h-0 flex-1'
        tableWrapperClassName='max-h-[calc(100vh-22rem)] overflow-auto'
        table={emptyRow => (
          <Table className='min-w-[980px] table-fixed'>
            <TableHeader>
              <TableRow>
                <TableHead className='w-[330px]'>
                  {t('module.billing.admin.providerPrices.table.product')}
                </TableHead>
                <TableHead className='w-[86px]'>
                  {t('module.billing.admin.providerPrices.table.productType')}
                </TableHead>
                <TableHead className='w-[118px]'>
                  {t('module.billing.admin.providerPrices.table.localPrice')}
                </TableHead>
                <TableHead className='w-[126px]'>
                  {t('module.billing.admin.providerPrices.table.stripePrice')}
                </TableHead>
                <TableHead className='w-[108px]'>
                  {t('module.billing.admin.providerPrices.table.status')}
                </TableHead>
                <TableHead className='w-[142px]'>
                  {t('module.billing.admin.providerPrices.table.validatedAt')}
                </TableHead>
                <TableHead className='w-[88px] text-left'>
                  {t('module.billing.admin.providerPrices.table.actions')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {emptyRow}
              {visibleRows.map(({ key, product, mapping }) => {
                const status = getMappingStatus(mapping);
                const productDescription = resolveProductDescription(
                  t,
                  product,
                );
                const productName = resolveAdminBillingProductName(
                  t,
                  product.display_name,
                  product.product_code,
                  {
                    credits: formatBillingCreditAmount(product.credit_amount),
                  },
                );
                const productShortBenefit = resolveProductShortBenefit(
                  t,
                  product,
                );
                const productDisplayName = productShortBenefit
                  ? `${productName} ${productShortBenefit}`
                  : productName;
                const canActivateMapping =
                  mapping &&
                  (mapping.status_label === 'draft' ||
                    mapping.status_label === 'invalid');
                return (
                  <TableRow key={key}>
                    <TableCell className='align-top'>
                      <div className='space-y-2'>
                        <div className='font-medium text-foreground'>
                          {productDisplayName}
                        </div>
                        {productDescription ? (
                          <div className='line-clamp-2 text-xs text-muted-foreground'>
                            {productDescription}
                          </div>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className='align-top'>
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
                    </TableCell>
                    <TableCell className='align-top text-sm'>
                      {formatBillingPrice(
                        product.price_amount,
                        product.currency,
                        i18n.language,
                      )}
                    </TableCell>
                    <TableCell className='align-top text-sm'>
                      {mapping ? (
                        <div className='space-y-1'>
                          <div className='font-medium text-foreground'>
                            {formatBillingPrice(
                              mapping.unit_amount,
                              mapping.currency,
                              i18n.language,
                            )}
                          </div>
                        </div>
                      ) : (
                        <span className='text-muted-foreground'>
                          {resolveBillingEmptyLabel(t)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className='align-top'>
                      <div className='space-y-1.5'>
                        <Badge
                          variant='outline'
                          className={statusClass(status)}
                        >
                          {t(
                            `module.billing.admin.providerPrices.health.${status}`,
                          )}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell className='align-top text-sm text-muted-foreground'>
                      {mapping?.validated_at
                        ? formatBillingDateTime(
                            mapping.validated_at,
                            i18n.language,
                          )
                        : resolveBillingEmptyLabel(t)}
                    </TableCell>
                    <TableCell className='align-top'>
                      <div className='flex justify-start'>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              type='button'
                              variant='ghost'
                              size='sm'
                              className='h-8 gap-1 px-2 text-muted-foreground'
                            >
                              {t('common.core.more')}
                              <ChevronDown className='h-3.5 w-3.5' />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            align='start'
                            className='min-w-[132px]'
                          >
                            <DropdownMenuItem
                              onSelect={() =>
                                openConfigDialog(product, mapping)
                              }
                            >
                              {t(
                                'module.billing.admin.providerPrices.actions.configure',
                              )}
                            </DropdownMenuItem>
                            {mapping && mapping.status_label !== 'retired' ? (
                              <DropdownMenuItem
                                disabled={
                                  actionLoading ===
                                  `validate:${mapping.provider_price_bid}`
                                }
                                onSelect={() =>
                                  requestAction('validate', mapping)
                                }
                              >
                                {t(
                                  'module.billing.admin.providerPrices.actions.validate',
                                )}
                              </DropdownMenuItem>
                            ) : null}
                            {canActivateMapping ? (
                              <DropdownMenuItem
                                disabled={
                                  actionLoading ===
                                  `activate:${mapping.provider_price_bid}`
                                }
                                onSelect={() =>
                                  requestAction(
                                    'activate',
                                    mapping,
                                    productDisplayName,
                                  )
                                }
                              >
                                {t(
                                  'module.billing.admin.providerPrices.actions.activate',
                                )}
                              </DropdownMenuItem>
                            ) : null}
                            {mapping?.status_label === 'retired' ? (
                              <DropdownMenuItem
                                disabled={
                                  actionLoading ===
                                  `restore:${mapping.provider_price_bid}`
                                }
                                onSelect={() =>
                                  requestAction(
                                    'restore',
                                    mapping,
                                    productDisplayName,
                                  )
                                }
                              >
                                {t(
                                  'module.billing.admin.providerPrices.actions.restore',
                                )}
                              </DropdownMenuItem>
                            ) : null}
                            {mapping?.status_label === 'active' ? (
                              <DropdownMenuItem
                                className='text-destructive focus:text-destructive'
                                disabled={
                                  actionLoading ===
                                  `retire:${mapping.provider_price_bid}`
                                }
                                onSelect={() =>
                                  requestAction(
                                    'retire',
                                    mapping,
                                    productDisplayName,
                                  )
                                }
                              >
                                {t(
                                  'module.billing.admin.providerPrices.actions.retire',
                                )}
                              </DropdownMenuItem>
                            ) : null}
                            {mapping?.validation_error ? (
                              <DropdownMenuItem
                                onSelect={() => setIssueMapping(mapping)}
                              >
                                {t(
                                  'module.billing.admin.providerPrices.actions.viewIssues',
                                )}
                              </DropdownMenuItem>
                            ) : null}
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
      />

      <Sheet
        open={Boolean(issueMapping)}
        onOpenChange={open => {
          if (!open) {
            setIssueMapping(null);
          }
        }}
      >
        <SheetContent className='flex w-full flex-col overflow-y-auto border-l border-border bg-white p-0 sm:w-[360px] md:w-[420px] lg:w-[480px]'>
          <SheetHeader className='border-b border-border px-5 py-5 pr-12 text-left'>
            <SheetTitle>
              {t('module.billing.admin.providerPrices.issueDrawer.title')}
            </SheetTitle>
            <SheetDescription>
              {t('module.billing.admin.providerPrices.issueDrawer.description')}
            </SheetDescription>
          </SheetHeader>
          {issueMapping ? (
            <div className='space-y-5 px-5 py-5'>
              <div className='space-y-3'>
                <div className='text-sm font-medium text-foreground'>
                  {t('module.billing.admin.providerPrices.issueDrawer.issues')}
                </div>
                {parseValidationIssueCodes(issueMapping.validation_error)
                  .length ? (
                  <div className='space-y-2'>
                    {parseValidationIssueCodes(
                      issueMapping.validation_error,
                    ).map(code => (
                      <div
                        key={code}
                        className='rounded-lg border border-amber-200 bg-amber-50 px-3 py-2'
                      >
                        <div className='text-sm font-medium text-amber-900'>
                          {resolveIssueLabel(t, code)}
                        </div>
                        <div className='mt-1 break-all font-mono text-xs text-amber-700'>
                          {code}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className='rounded-lg border bg-muted/30 px-3 py-2 text-sm text-muted-foreground'>
                    {t(
                      'module.billing.admin.providerPrices.issueDrawer.noIssues',
                    )}
                  </div>
                )}
              </div>
              <details className='rounded-lg border border-border bg-muted/20 p-3'>
                <summary className='cursor-pointer text-sm font-medium text-muted-foreground'>
                  {t('module.billing.admin.providerPrices.issueDrawer.raw')}
                </summary>
                <pre className='mt-3 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-md bg-slate-950 p-3 text-xs text-slate-100'>
                  {issueMapping.validation_error || resolveBillingEmptyLabel(t)}
                </pre>
              </details>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>

      <Dialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      >
        <DialogContent className='sm:max-w-[560px]'>
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
          <DialogFooter className='mt-4 gap-2'>
            <Button
              type='button'
              variant='outline'
              onClick={() => setDialogOpen(false)}
            >
              {t('module.billing.admin.providerPrices.actions.cancel')}
            </Button>
            <Button
              type='button'
              disabled={actionLoading === 'create' || !canSubmitDraft}
              onClick={submitDraft}
            >
              {t('module.billing.admin.providerPrices.actions.saveDraft')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={Boolean(confirmAction)}
        onOpenChange={open => {
          if (!open) {
            setConfirmAction(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmAction
                ? t(
                    `module.billing.admin.providerPrices.actions.${confirmAction.action}`,
                  )
                : ''}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction
                ? t(
                    `module.billing.admin.providerPrices.confirm.${confirmAction.action}`,
                    {
                      productName:
                        confirmAction.productName ||
                        confirmAction.mapping.provider_price_id,
                    },
                  )
                : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t('module.billing.admin.providerPrices.actions.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={event => {
                event.preventDefault();
                if (!confirmAction) {
                  return;
                }
                const pendingAction = confirmAction;
                setConfirmAction(null);
                void runAction(pendingAction.action, pendingAction.mapping);
              }}
            >
              {t('common.core.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
