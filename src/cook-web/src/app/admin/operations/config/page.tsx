'use client';

import React from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTableShell from '@/components/admin/AdminTableShell';
import AdminTitle from '@/app/admin/components/AdminTitle';
import {
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/components/admin/adminTableStyles';
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
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import Loading from '@/components/loading';
import {
  ADMIN_BILLING_TABS_LIST_CLASSNAME,
  ADMIN_BILLING_TABS_TRIGGER_CLASSNAME,
} from '@/components/billing/AdminBillingShared';
import { useToast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import { useTranslation } from 'react-i18next';
import useOperatorGuard from '../useOperatorGuard';

const RATE_TABS = ['llm', 'tts'] as const;
const RATE_TABLE_PAGE_SIZE = 10;
type RateTab = (typeof RATE_TABS)[number];

type RateRow = {
  rate_bid?: string;
  usage_type: 'llm' | 'tts' | string;
  usage_type_code: number;
  provider: string;
  model: string;
  rate_model?: string;
  display_name: string;
  usage_scene: string;
  usage_scene_code: number;
  billing_metric: string;
  billing_metric_code: number;
  unit_size: number;
  credits_per_unit: number;
  unit_cost: number;
  multiplier: number | null;
  rounding_mode: number;
  status_code: number;
  updated_at?: string | null;
  source: string;
};

type RateConfigResponse = {
  baseline?: {
    default_llm_model?: string;
    unit_cost?: number;
    tts_chars_per_llm_token?: number;
  };
  llm_rates?: RateRow[];
  tts_rates?: RateRow[];
};

type EditState = {
  row: RateRow;
  unitSize: string;
  creditsPerUnit: string | null;
  multiplier: string;
};

const getRateRowKey = (row: RateRow) =>
  `${row.usage_type}-${row.provider}-${row.rate_model || row.model}-${row.billing_metric}`;

const formatNumber = (value: unknown, fallback = '-') => {
  if (value === null || value === undefined) {
    return fallback;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 6 });
};

const normalizeMultiplierInput = (value: string) => {
  const normalized = value.replace(/[。．｡]/g, '.');
  const cleaned = normalized.replace(/[^\d.]/g, '');
  const [integerPart = '', ...decimalParts] = cleaned.split('.');
  const decimalPart = decimalParts.join('').slice(0, 2);
  if (cleaned.includes('.')) {
    return `${integerPart || '0'}.${decimalPart}`;
  }
  return integerPart;
};

const isValidMultiplier = (value: string) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0;
};

const formatMultiplier = (value: unknown) => {
  const formatted = formatNumber(value);
  return formatted === '-' ? formatted : `${formatted}x`;
};

function ConfigReferenceTooltip({
  baseline,
}: {
  baseline?: RateConfigResponse['baseline'];
}) {
  const { t } = useTranslation(['module.operationsConfig']);
  const items = [
    {
      label: t('rules.baselineModel'),
      value: baseline?.default_llm_model || '-',
    },
    {
      label: t('rules.baselineUnitCost'),
      value: formatNumber(baseline?.unit_cost),
    },
    {
      label: t('rules.ttsFactor'),
      value: formatNumber(baseline?.tts_chars_per_llm_token),
    },
    {
      label: t('rules.effectScope'),
      value: t('rules.futureOnly'),
    },
  ];

  return (
    <span className='group relative ml-1 inline-flex'>
      <button
        type='button'
        aria-label={t('rules.tooltipAriaLabel')}
        className='inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30'
      >
        <QuestionMarkCircleIcon className='h-4 w-4' />
      </button>
      <span className='pointer-events-none absolute left-full top-1/2 z-50 ml-3 hidden w-[min(390px,calc(100vw-48px))] -translate-y-1/2 rounded-lg bg-[#171717] p-3 text-left text-xs font-normal leading-5 text-white shadow-lg group-hover:block group-focus-within:block'>
        <span className='absolute -left-1 top-1/2 h-2 w-2 -translate-y-1/2 rotate-45 bg-[#171717]' />
        <span className='block max-h-[220px] overflow-auto'>
          <span className='block font-medium leading-5'>
            {t('rules.intro')}
          </span>
          <span className='mt-2 grid gap-x-3 gap-y-1.5'>
            {items.map(item => (
              <span
                key={item.label}
                className='grid grid-cols-[128px_1fr] gap-2'
              >
                <span className='text-white/60'>{item.label}</span>
                <span className='min-w-0 break-words text-white'>
                  {item.value}
                </span>
              </span>
            ))}
          </span>
        </span>
      </span>
    </span>
  );
}

function RateTable({
  rows,
  loading,
  onEdit,
  onCancelEdit,
  onMultiplierChange,
  onMultiplierBlur,
  onSaveEdit,
  editState,
  saving,
  modelHeader,
  showProvider,
  multiplierHeader,
}: {
  rows: RateRow[];
  loading: boolean;
  onEdit: (row: RateRow) => void;
  onCancelEdit: () => void;
  onMultiplierChange: (value: string) => void;
  onMultiplierBlur: () => void;
  onSaveEdit: () => void;
  editState: EditState | null;
  saving: boolean;
  modelHeader: string;
  showProvider: boolean;
  multiplierHeader: string;
}) {
  const { t } = useTranslation(['module.operationsConfig', 'common.core']);
  const [pageIndex, setPageIndex] = React.useState(1);
  const pageCount = Math.max(Math.ceil(rows.length / RATE_TABLE_PAGE_SIZE), 1);
  const safePageIndex = Math.min(pageIndex, pageCount);
  const visibleRows = React.useMemo(() => {
    const start = (safePageIndex - 1) * RATE_TABLE_PAGE_SIZE;
    return rows.slice(start, start + RATE_TABLE_PAGE_SIZE);
  }, [rows, safePageIndex]);
  const dataColSpan = showProvider ? 6 : 5;
  const emptyColSpan = dataColSpan + 1;

  React.useEffect(() => {
    setPageIndex(1);
  }, [rows]);

  return (
    <AdminTableShell
      loading={loading}
      isEmpty={!rows.length}
      emptyContent={t('empty')}
      emptyColSpan={emptyColSpan}
      stickyActionEmpty={{
        contentColSpan: dataColSpan,
        actionClassName: getAdminStickyRightCellClass(
          'w-[132px] min-w-[132px] whitespace-nowrap text-left',
        ),
      }}
      pagination={{
        pageIndex: safePageIndex,
        pageCount,
        onPageChange: setPageIndex,
        prevLabel: t('pagination.prev'),
        nextLabel: t('pagination.next'),
        prevAriaLabel: t('pagination.prev'),
        nextAriaLabel: t('pagination.next'),
        hideWhenSinglePage: true,
        jumpInputThreshold: Number.MAX_SAFE_INTEGER,
      }}
      footerClassName='justify-end'
      table={emptyRow => (
        <Table className={showProvider ? 'min-w-[860px]' : 'min-w-[760px]'}>
          <TableHeader>
            <TableRow>
              {showProvider ? (
                <TableHead className='min-w-[120px]'>
                  {t('fields.provider')}
                </TableHead>
              ) : null}
              <TableHead className='min-w-[180px]'>{modelHeader}</TableHead>
              <TableHead className='min-w-[160px]'>
                {t('fields.displayName')}
              </TableHead>
              <TableHead className='min-w-[148px]'>
                {multiplierHeader}
              </TableHead>
              <TableHead className='min-w-[104px]'>
                {t('fields.source')}
              </TableHead>
              <TableHead className='min-w-[150px]'>
                {t('fields.updatedAt')}
              </TableHead>
              <TableHead
                className={getAdminStickyRightHeaderClass(
                  'w-[132px] min-w-[132px] whitespace-nowrap text-left',
                )}
              >
                {t('fields.actions')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {emptyRow}
            {visibleRows.map(row => {
              const isEditing =
                editState?.row &&
                getRateRowKey(editState.row) === getRateRowKey(row);

              return (
                <TableRow key={getRateRowKey(row)}>
                  {showProvider ? (
                    <TableCell className='font-medium'>
                      {row.provider || '-'}
                    </TableCell>
                  ) : null}
                  <TableCell>
                    <span className='block max-w-[220px] truncate font-mono text-xs'>
                      {row.model || '-'}
                    </span>
                    {!showProvider && row.provider ? (
                      <span className='mt-1 block max-w-[220px] truncate text-xs text-muted-foreground'>
                        {row.provider}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <span className='block max-w-[220px] truncate'>
                      {row.display_name || '-'}
                    </span>
                  </TableCell>
                  <TableCell>
                    {isEditing ? (
                      <div className='flex items-center gap-2'>
                        <Input
                          type='text'
                          inputMode='decimal'
                          value={editState.multiplier}
                          className='h-8 w-[84px] px-2 text-sm font-medium'
                          disabled={saving}
                          onChange={event =>
                            onMultiplierChange(event.target.value)
                          }
                          onBlur={onMultiplierBlur}
                        />
                        <span className='select-none text-sm font-medium text-foreground'>
                          {t('fields.multiplierSuffix')}
                        </span>
                      </div>
                    ) : row.multiplier == null ? (
                      '-'
                    ) : (
                      `${formatNumber(row.multiplier)}x`
                    )}
                  </TableCell>
                  <TableCell>
                    {row.source === 'exact'
                      ? t('source.exact')
                      : row.source === 'default'
                        ? t('source.default')
                        : row.source === 'unconfigured'
                          ? t('source.unconfigured')
                          : row.source || '-'}
                  </TableCell>
                  <TableCell>
                    {row.updated_at
                      ? formatAdminUtcDateTime(row.updated_at)
                      : '-'}
                  </TableCell>
                  <TableCell
                    className={getAdminStickyRightCellClass(
                      'w-[132px] min-w-[132px] whitespace-nowrap text-left',
                    )}
                  >
                    {isEditing ? (
                      <div className='flex items-center justify-start gap-3'>
                        <Button
                          type='button'
                          variant='ghost'
                          size='sm'
                          className='h-auto justify-center rounded-none p-0 text-primary hover:bg-transparent hover:text-primary/80'
                          disabled={saving}
                          onClick={onSaveEdit}
                        >
                          {t('actions.save')}
                        </Button>
                        <Button
                          type='button'
                          variant='ghost'
                          size='sm'
                          className='h-auto justify-center rounded-none p-0 text-muted-foreground hover:bg-transparent hover:text-foreground'
                          disabled={saving}
                          onClick={onCancelEdit}
                        >
                          {t('common.core:cancel')}
                        </Button>
                      </div>
                    ) : (
                      <Button
                        type='button'
                        variant='ghost'
                        size='sm'
                        className='h-auto justify-center rounded-none p-0 text-primary hover:bg-transparent hover:text-primary/80'
                        disabled={saving}
                        onClick={() => onEdit(row)}
                      >
                        {t('actions.edit')}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    />
  );
}

export default function AdminOperationsConfigPage() {
  const { t } = useTranslation(['module.operationsConfig', 'common.core']);
  const { toast } = useToast();
  const { isReady } = useOperatorGuard();
  const [activeTab, setActiveTab] = React.useState<RateTab>('llm');
  const [config, setConfig] = React.useState<RateConfigResponse>({});
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [editState, setEditState] = React.useState<EditState | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const loadConfig = React.useCallback(async () => {
    setLoading(true);
    try {
      const response = (await api.getAdminOperationConfigRates(
        {},
      )) as RateConfigResponse;
      setConfig(response || {});
    } catch (caughtError) {
      const typedError = caughtError as Partial<ErrorWithCode>;
      toast({
        title: typedError.message || t('loadFailed'),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [t, toast]);

  React.useEffect(() => {
    if (!isReady) {
      return;
    }
    void loadConfig();
  }, [isReady, loadConfig]);

  const openEditor = React.useCallback((row: RateRow) => {
    setEditState({
      row,
      unitSize: String(row.unit_size || 1),
      creditsPerUnit: String(row.credits_per_unit ?? 0),
      multiplier: row.multiplier == null ? '' : String(row.multiplier),
    });
  }, []);

  const updateCreditsFromMultiplier = React.useCallback(
    (multiplierText: string, current: EditState): string | null => {
      const multiplier = Number(multiplierText);
      const unitSize = Number(current.unitSize || 1);
      const baseline = Number(config.baseline?.unit_cost || 0);
      if (
        !Number.isFinite(multiplier) ||
        !Number.isFinite(unitSize) ||
        baseline <= 0
      ) {
        return null;
      }
      let value = baseline * multiplier * unitSize;
      if (current.row.usage_type === 'tts') {
        const factor = Number(config.baseline?.tts_chars_per_llm_token || 0);
        if (factor <= 0) {
          return null;
        }
        value = (baseline * multiplier * unitSize) / factor;
      }
      return String(Number(value.toFixed(10)));
    },
    [config.baseline?.tts_chars_per_llm_token, config.baseline?.unit_cost],
  );

  const saveEdit = React.useCallback(async () => {
    if (!editState) {
      return;
    }
    if (!isValidMultiplier(editState.multiplier)) {
      toast({ title: t('invalidMultiplier'), variant: 'destructive' });
      return;
    }
    const nextCreditsPerUnit = updateCreditsFromMultiplier(
      editState.multiplier,
      editState,
    );
    if (nextCreditsPerUnit == null || Number(nextCreditsPerUnit) <= 0) {
      toast({ title: t('invalidMultiplier'), variant: 'destructive' });
      return;
    }
    setSaving(true);
    try {
      await api.updateAdminOperationConfigRate({
        usage_type: editState.row.usage_type,
        provider: editState.row.provider,
        model: editState.row.model,
        rate_model: editState.row.rate_model || editState.row.model,
        display_name: editState.row.display_name,
        billing_metric: editState.row.billing_metric,
        unit_size: Number(editState.unitSize || 1),
        credits_per_unit: Number(nextCreditsPerUnit),
        status: 'active',
      });
      toast({ title: t('saveSuccess') });
      setEditState(null);
      setConfirmOpen(false);
      await loadConfig();
    } catch (caughtError) {
      const typedError = caughtError as Partial<ErrorWithCode>;
      toast({
        title: typedError.message || t('saveFailed'),
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  }, [editState, loadConfig, t, toast, updateCreditsFromMultiplier]);

  const requestSaveEdit = React.useCallback(() => {
    if (!editState) {
      return;
    }
    if (!isValidMultiplier(editState.multiplier)) {
      toast({ title: t('invalidMultiplier'), variant: 'destructive' });
      return;
    }
    setConfirmOpen(true);
  }, [editState, t, toast]);

  const updateEditMultiplier = React.useCallback(
    (rawValue: string) => {
      const nextMultiplier = normalizeMultiplierInput(rawValue);
      setEditState(current =>
        current
          ? {
              ...current,
              multiplier: nextMultiplier,
              creditsPerUnit: updateCreditsFromMultiplier(
                nextMultiplier,
                current,
              ),
            }
          : current,
      );
    },
    [updateCreditsFromMultiplier],
  );

  const clearInvalidEditMultiplier = React.useCallback(() => {
    setEditState(current =>
      current && !isValidMultiplier(current.multiplier)
        ? {
            ...current,
            multiplier: '',
            creditsPerUnit: null,
          }
        : current,
    );
  }, []);

  if (!isReady) {
    return <Loading />;
  }

  const llmRows = config.llm_rates || [];
  const ttsRows = config.tts_rates || [];
  const confirmModelName =
    editState?.row.display_name || editState?.row.model || '-';
  const confirmFromMultiplier = formatMultiplier(editState?.row.multiplier);
  const confirmToMultiplier = formatMultiplier(editState?.multiplier);

  return (
    <>
      <AdminBreadcrumb items={[{ label: t('title') }]} />

      <Tabs
        className='flex min-h-0 flex-1 flex-col'
        value={activeTab}
        onValueChange={value => setActiveTab(value as RateTab)}
      >
        <AdminTitle
          title={t('title')}
          description={
            <span className='inline-flex items-center'>
              <span>{t('description')}</span>
              <ConfigReferenceTooltip baseline={config.baseline} />
            </span>
          }
          tabs={
            <TabsList className={ADMIN_BILLING_TABS_LIST_CLASSNAME}>
              {RATE_TABS.map(tab => (
                <TabsTrigger
                  key={tab}
                  value={tab}
                  className={ADMIN_BILLING_TABS_TRIGGER_CLASSNAME}
                >
                  {tab === 'llm' ? t('tabs.llm') : t('tabs.tts')}
                </TabsTrigger>
              ))}
            </TabsList>
          }
        />

        <div className='flex min-h-0 flex-1 flex-col gap-4'>
          <TabsContent
            value='llm'
            className='mt-0'
          >
            <RateTable
              rows={llmRows}
              loading={loading}
              onEdit={openEditor}
              onCancelEdit={() => setEditState(null)}
              onMultiplierChange={updateEditMultiplier}
              onMultiplierBlur={clearInvalidEditMultiplier}
              onSaveEdit={requestSaveEdit}
              editState={editState}
              saving={saving}
              modelHeader={t('fields.model')}
              showProvider={false}
              multiplierHeader={t('fields.multiplier')}
            />
          </TabsContent>

          <TabsContent
            value='tts'
            className='mt-0'
          >
            <RateTable
              rows={ttsRows}
              loading={loading}
              onEdit={openEditor}
              onCancelEdit={() => setEditState(null)}
              onMultiplierChange={updateEditMultiplier}
              onMultiplierBlur={clearInvalidEditMultiplier}
              onSaveEdit={requestSaveEdit}
              editState={editState}
              saving={saving}
              modelHeader={t('fields.modelTier')}
              showProvider
              multiplierHeader={t('fields.ttsMultiplier')}
            />
          </TabsContent>
        </div>
      </Tabs>

      <AlertDialog
        open={confirmOpen}
        onOpenChange={open => {
          if (!saving) {
            setConfirmOpen(open);
          }
        }}
      >
        <AlertDialogContent className='max-w-[420px]'>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirm.title')}</AlertDialogTitle>
            <AlertDialogDescription className='leading-6 text-foreground'>
              {t('confirm.description', {
                model: confirmModelName,
                from: confirmFromMultiplier,
                to: confirmToMultiplier,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={saving}>
              {t('common.core:cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={saving}
              onClick={event => {
                event.preventDefault();
                void saveEdit();
              }}
            >
              {t('actions.save')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
