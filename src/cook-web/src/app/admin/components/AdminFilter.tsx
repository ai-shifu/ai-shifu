import type { ReactNode } from 'react';
import { ChevronDown, ChevronUp, X } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

export type AdminFilterItem = {
  key: string;
  label: ReactNode;
  component: ReactNode;
  contentClassName?: string;
  itemClassName?: string;
  labelClassName?: string;
};

export type AdminFilterActiveFilter = {
  label: ReactNode;
  value: ReactNode;
  clearAriaLabel: string;
  onClear: () => void;
};

type AdminFilterProps = {
  items: AdminFilterItem[];
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  onReset: () => void;
  onSearch: () => void;
  resetLabel: string;
  searchLabel: string;
  expandLabel: string;
  collapseLabel: string;
  collapsedCount?: number;
  className?: string;
  contentClassName?: string;
  labelClassName?: string;
  collapsedLabelClassName?: string;
  expandedLabelClassName?: string;
  collapsedGridClassName?: string;
  expandedGridClassName?: string;
  labelColon?: boolean;
  showToggle?: boolean;
  surface?: 'plain' | 'card';
  layoutPreset?: 'default' | 'operations';
  activeFilter?: AdminFilterActiveFilter | null;
  testId?: string;
};

const ADMIN_FILTER_LABEL_CLASS =
  'shrink-0 whitespace-nowrap text-[length:var(--text-sm-font-size,14px)] not-italic font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]';
const ADMIN_FILTER_CARD_CLASS =
  'rounded-xl border border-border bg-white p-4 shadow-sm transition-all';
const ADMIN_FILTER_ACTIVE_CHIP_CLASS =
  'inline-flex items-center gap-1 rounded-full border border-border bg-muted/30 px-3 py-1 text-sm text-foreground transition-colors hover:bg-muted';

const AdminFilterField = ({
  item,
  contentClassName,
  labelClassName,
  labelColon,
}: {
  item: AdminFilterItem;
  contentClassName?: string;
  labelClassName?: string;
  labelColon?: boolean;
}) => (
  <div
    className={cn(
      'flex min-w-0 items-center gap-3 md:[&>span]:text-right',
      item.itemClassName,
    )}
  >
    <span
      className={cn(
        ADMIN_FILTER_LABEL_CLASS,
        labelColon && "after:ml-0.5 after:content-[':']",
        labelClassName,
        item.labelClassName,
      )}
    >
      {item.label}
    </span>
    <div
      className={cn('min-w-0 flex-1', contentClassName, item.contentClassName)}
    >
      {item.component}
    </div>
  </div>
);

const AdminFilterActions = ({
  expanded,
  onExpandedChange,
  onReset,
  onSearch,
  resetLabel,
  searchLabel,
  expandLabel,
  collapseLabel,
  showToggle,
}: Omit<
  AdminFilterProps,
  | 'items'
  | 'collapsedCount'
  | 'className'
  | 'contentClassName'
  | 'labelClassName'
  | 'collapsedLabelClassName'
  | 'expandedLabelClassName'
  | 'collapsedGridClassName'
  | 'expandedGridClassName'
  | 'labelColon'
  | 'surface'
  | 'layoutPreset'
  | 'activeFilter'
  | 'testId'
>) => (
  <div className='flex shrink-0 items-center justify-end'>
    <Button
      size='sm'
      type='button'
      variant='outline'
      className='px-4'
      onClick={onReset}
    >
      {resetLabel}
    </Button>
    <Button
      size='sm'
      type='button'
      className='ml-2 px-4'
      onClick={onSearch}
    >
      {searchLabel}
    </Button>
    {showToggle ? (
      <Button
        size='sm'
        type='button'
        variant='ghost'
        className='ml-4 gap-1 px-2 text-[var(--base-foreground,#0A0A0A)] hover:text-[var(--base-foreground,#0A0A0A)]'
        onClick={() => onExpandedChange(!expanded)}
      >
        {expanded ? collapseLabel : expandLabel}
        {expanded ? (
          <ChevronUp className='h-4 w-4' />
        ) : (
          <ChevronDown className='h-4 w-4' />
        )}
      </Button>
    ) : null}
  </div>
);

export default function AdminFilter({
  items,
  expanded,
  onExpandedChange,
  onReset,
  onSearch,
  resetLabel,
  searchLabel,
  expandLabel,
  collapseLabel,
  collapsedCount = 2,
  className,
  contentClassName,
  labelClassName,
  collapsedLabelClassName,
  expandedLabelClassName,
  collapsedGridClassName,
  expandedGridClassName,
  labelColon,
  showToggle,
  surface = 'plain',
  layoutPreset = 'default',
  activeFilter,
  testId,
}: AdminFilterProps) {
  const canToggle = showToggle ?? items.length > collapsedCount;
  const collapsedItems = items.slice(0, collapsedCount);
  const isOperationsPreset = layoutPreset === 'operations';
  const resolvedCollapsedLabelClassName =
    collapsedLabelClassName ??
    labelClassName ??
    (isOperationsPreset ? 'w-20 text-right' : undefined);
  const resolvedExpandedLabelClassName =
    expandedLabelClassName ??
    labelClassName ??
    (isOperationsPreset ? 'w-20 text-right' : undefined);
  const resolvedContentClassName =
    contentClassName ?? (isOperationsPreset ? 'min-w-0' : undefined);
  const resolvedCollapsedGridClassName =
    collapsedGridClassName ??
    (isOperationsPreset ? 'gap-x-5 xl:grid-cols-3' : undefined);
  const resolvedExpandedGridClassName =
    expandedGridClassName ??
    (isOperationsPreset ? 'gap-x-5 xl:grid-cols-3' : undefined);
  const resolvedLabelColon = labelColon ?? isOperationsPreset;

  return (
    <div
      data-testid={testId}
      className={cn(
        'w-full',
        surface === 'card' ? ADMIN_FILTER_CARD_CLASS : 'bg-white',
        activeFilter && 'space-y-4',
        className,
      )}
    >
      {activeFilter ? (
        <div className='flex flex-wrap items-center gap-2'>
          <span className='text-sm text-muted-foreground'>
            {activeFilter.label}
          </span>
          <button
            type='button'
            aria-label={activeFilter.clearAriaLabel}
            className={ADMIN_FILTER_ACTIVE_CHIP_CLASS}
            onClick={activeFilter.onClear}
          >
            <span>{activeFilter.value}</span>
            <X className='h-3.5 w-3.5' />
          </button>
        </div>
      ) : null}
      {!expanded ? (
        <div className='flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between'>
          <div
            className={cn(
              'grid min-w-0 flex-1 grid-cols-1 gap-x-7 gap-y-4 xl:grid-cols-[repeat(3,minmax(0,245px))]',
              resolvedCollapsedGridClassName,
            )}
          >
            {collapsedItems.map(item => (
              <AdminFilterField
                key={item.key}
                item={item}
                contentClassName={resolvedContentClassName}
                labelClassName={resolvedCollapsedLabelClassName}
                labelColon={resolvedLabelColon}
              />
            ))}
          </div>
          <AdminFilterActions
            expanded={expanded}
            onExpandedChange={onExpandedChange}
            onReset={onReset}
            onSearch={onSearch}
            resetLabel={resetLabel}
            searchLabel={searchLabel}
            expandLabel={expandLabel}
            collapseLabel={collapseLabel}
            showToggle={canToggle}
          />
        </div>
      ) : (
        <div className='space-y-4'>
          <div
            className={cn(
              'grid min-w-0 grid-cols-1 gap-x-7 gap-y-4 xl:grid-cols-3',
              resolvedExpandedGridClassName,
            )}
          >
            {items.map(item => (
              <AdminFilterField
                key={item.key}
                item={item}
                contentClassName={resolvedContentClassName}
                labelClassName={resolvedExpandedLabelClassName}
                labelColon={resolvedLabelColon}
              />
            ))}
          </div>
          <AdminFilterActions
            expanded={expanded}
            onExpandedChange={onExpandedChange}
            onReset={onReset}
            onSearch={onSearch}
            resetLabel={resetLabel}
            searchLabel={searchLabel}
            expandLabel={expandLabel}
            collapseLabel={collapseLabel}
            showToggle={canToggle}
          />
        </div>
      )}
    </div>
  );
}
