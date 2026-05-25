import type { ReactNode } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
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
  showToggle?: boolean;
};

const ADMIN_FILTER_LABEL_CLASS =
  'shrink-0 whitespace-nowrap text-[length:var(--text-sm-font-size,14px)] not-italic font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]';

const AdminFilterField = ({
  item,
  contentClassName,
  labelClassName,
}: {
  item: AdminFilterItem;
  contentClassName?: string;
  labelClassName?: string;
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
  showToggle,
}: AdminFilterProps) {
  const canToggle = showToggle ?? items.length > collapsedCount;
  const collapsedItems = items.slice(0, collapsedCount);
  const resolvedCollapsedLabelClassName =
    collapsedLabelClassName ?? labelClassName;
  const resolvedExpandedLabelClassName =
    expandedLabelClassName ?? labelClassName;

  return (
    <div className={cn('w-full bg-white', className)}>
      {!expanded ? (
        <div className='flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between'>
          <div className='grid min-w-0 flex-1 grid-cols-1 gap-x-7 gap-y-4 xl:grid-cols-[repeat(3,minmax(0,245px))]'>
            {collapsedItems.map(item => (
              <AdminFilterField
                key={item.key}
                item={item}
                contentClassName={contentClassName}
                labelClassName={resolvedCollapsedLabelClassName}
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
          <div className='grid min-w-0 grid-cols-1 gap-x-7 gap-y-4 xl:grid-cols-3'>
            {items.map(item => (
              <AdminFilterField
                key={item.key}
                item={item}
                contentClassName={contentClassName}
                labelClassName={resolvedExpandedLabelClassName}
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
