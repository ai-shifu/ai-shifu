import type { ReactNode } from 'react';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export type AdminMetricCardHoverMode = 'card' | 'control';

export type AdminMetricCardItem = {
  key: string;
  label: string;
  value: ReactNode;
  tooltip: string;
  onClick?: () => void;
};

type AdminMetricCardProps = Omit<AdminMetricCardItem, 'key'> & {
  hoverMode?: AdminMetricCardHoverMode;
  className?: string;
  valueClassName?: string;
};

type AdminMetricCardGroupProps = {
  items: AdminMetricCardItem[];
  title?: ReactNode;
  className?: string;
  gridClassName?: string;
  cardHoverMode?: AdminMetricCardHoverMode;
  tooltipDelayDuration?: number;
  valueClassName?: string;
};

const CARD_CLASS = 'rounded-lg border border-border/70 bg-muted/20 p-4';
const CONTROL_TARGET_CLASS = 'metric-control';
const CLICKABLE_CARD_HOVER_CLASS =
  'transition-colors has-[.metric-control:hover]:border-primary/30 has-[.metric-control:hover]:bg-primary/[0.04]';
const STATIC_CARD_HOVER_CLASS =
  'transition-colors hover:border-primary/30 hover:bg-primary/[0.04]';
const CONTROL_CLASS =
  'group min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2';
const INSET_CONTROL_CLASS =
  '-m-2 rounded-md border border-transparent p-2 transition-colors hover:border-primary/30 hover:bg-primary/[0.04]';
const TOOLTIP_TRIGGER_CLASS =
  'inline-flex h-4 w-4 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2';

export function AdminMetricCard({
  label,
  value,
  tooltip,
  onClick,
  hoverMode = 'card',
  className,
  valueClassName,
}: AdminMetricCardProps) {
  const content = (
    <>
      <div className='text-sm text-muted-foreground'>{label}</div>
      <div
        className={cn(
          'mt-3 text-2xl font-semibold text-foreground transition-colors group-hover:text-primary',
          valueClassName,
        )}
      >
        {value}
      </div>
    </>
  );

  return (
    <div
      className={cn(
        CARD_CLASS,
        hoverMode === 'card' &&
          (onClick ? CLICKABLE_CARD_HOVER_CLASS : STATIC_CARD_HOVER_CLASS),
        className,
      )}
    >
      <div className='flex items-start justify-between gap-2'>
        {onClick ? (
          <button
            type='button'
            aria-label={label}
            className={cn(
              CONTROL_CLASS,
              hoverMode === 'card' && CONTROL_TARGET_CLASS,
              hoverMode === 'control' && INSET_CONTROL_CLASS,
            )}
            onClick={onClick}
          >
            {content}
          </button>
        ) : (
          <div className='min-w-0 flex-1'>{content}</div>
        )}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type='button'
              aria-label={tooltip}
              className={TOOLTIP_TRIGGER_CLASS}
            >
              <QuestionMarkCircleIcon className='h-4 w-4' />
            </button>
          </TooltipTrigger>
          <TooltipContent className='max-w-56 text-left leading-5'>
            {tooltip}
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}

export function AdminMetricCardGroup({
  items,
  title,
  className,
  gridClassName,
  cardHoverMode = 'card',
  tooltipDelayDuration = 150,
  valueClassName,
}: AdminMetricCardGroupProps) {
  const grid = (
    <TooltipProvider delayDuration={tooltipDelayDuration}>
      <div className={cn('grid gap-3', gridClassName)}>
        {items.map(item => (
          <AdminMetricCard
            key={item.key}
            label={item.label}
            value={item.value}
            tooltip={item.tooltip}
            onClick={item.onClick}
            hoverMode={cardHoverMode}
            valueClassName={valueClassName}
          />
        ))}
      </div>
    </TooltipProvider>
  );

  if (!title) {
    return className ? <div className={className}>{grid}</div> : grid;
  }

  return (
    <div
      className={cn(
        'mb-5 rounded-xl border border-border bg-white p-4 shadow-sm',
        className,
      )}
    >
      <div className='mb-3'>
        <h2 className='text-base font-semibold text-foreground'>{title}</h2>
      </div>
      {grid}
    </div>
  );
}
