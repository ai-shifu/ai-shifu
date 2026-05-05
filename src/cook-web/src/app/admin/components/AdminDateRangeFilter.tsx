import React from 'react';
import { CalendarIcon, X } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Calendar } from '@/components/ui/Calendar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/Popover';
import { cn } from '@/lib/utils';

type AdminDateRangeFilterProps = {
  startValue: string;
  endValue: string;
  placeholder: string;
  resetLabel: string;
  clearLabel: string;
  numberOfMonths?: number;
  triggerAriaLabel?: string;
  popoverContainer?: HTMLElement | null;
  popoverModal?: boolean;
  onChange: (range: { start: string; end: string }) => void;
};

const formatDateValue = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const parseDateValue = (value: string) => {
  if (!value) {
    return undefined;
  }
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return undefined;
  }
  return parsed;
};

const AdminDateRangeFilter = ({
  startValue,
  endValue,
  placeholder,
  resetLabel,
  clearLabel,
  numberOfMonths = 2,
  triggerAriaLabel,
  popoverContainer,
  popoverModal,
  onChange,
}: AdminDateRangeFilterProps) => {
  const selectedRange = React.useMemo(
    () => ({
      from: parseDateValue(startValue),
      to: parseDateValue(endValue),
    }),
    [endValue, startValue],
  );

  const label = React.useMemo(() => {
    if (selectedRange.from && selectedRange.to) {
      return `${formatDateValue(selectedRange.from)} ~ ${formatDateValue(
        selectedRange.to,
      )}`;
    }
    if (selectedRange.from) {
      return formatDateValue(selectedRange.from);
    }
    return placeholder;
  }, [placeholder, selectedRange]);
  const hasValue = Boolean(startValue || endValue);
  const triggerLabel = React.useMemo(() => {
    const baseTriggerLabel = triggerAriaLabel || placeholder;
    if (!hasValue || label === baseTriggerLabel) {
      return baseTriggerLabel;
    }
    return [baseTriggerLabel, label].filter(Boolean).join(' ');
  }, [hasValue, label, placeholder, triggerAriaLabel]);

  return (
    <Popover modal={popoverModal}>
      <div className='relative'>
        <PopoverTrigger asChild>
          <Button
            size='sm'
            variant='outline'
            type='button'
            aria-label={triggerLabel}
            className={cn(
              'h-9 w-full justify-start font-normal',
              hasValue ? 'pr-16' : 'pr-10',
            )}
          >
            <span
              className={cn(
                'flex-1 truncate text-left',
                startValue ? 'text-foreground' : 'text-muted-foreground',
              )}
            >
              {label}
            </span>
          </Button>
        </PopoverTrigger>
        {hasValue ? (
          <button
            type='button'
            aria-label={clearLabel}
            className='absolute right-9 top-1/2 z-10 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground'
            onMouseDown={event => {
              event.preventDefault();
              event.stopPropagation();
            }}
            onClick={event => {
              event.preventDefault();
              event.stopPropagation();
              onChange({ start: '', end: '' });
            }}
          >
            <X className='h-3.5 w-3.5' />
          </button>
        ) : null}
        <CalendarIcon className='pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
      </div>
      <PopoverContent
        align='start'
        container={popoverContainer}
        className='w-auto max-w-[calc(100vw-2rem)] max-h-[min(80vh,42rem)] overflow-auto p-0'
      >
        <Calendar
          mode='range'
          numberOfMonths={numberOfMonths}
          selected={selectedRange}
          onSelect={range =>
            onChange({
              start: range?.from ? formatDateValue(range.from) : '',
              end: range?.to ? formatDateValue(range.to) : '',
            })
          }
          classNames={{
            months: 'relative flex flex-row gap-2',
            month: 'flex w-full flex-col gap-2',
            week: 'mt-1 flex w-full',
          }}
          className='p-1.5 md:p-2 [--cell-size:1.9rem] lg:[--cell-size:2rem] xl:[--cell-size:2.1rem]'
        />
        <div className='flex items-center justify-end gap-2 border-t border-border px-3 py-1.5'>
          <Button
            size='sm'
            variant='ghost'
            type='button'
            onClick={() => onChange({ start: '', end: '' })}
          >
            {resetLabel}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default AdminDateRangeFilter;
