import React, { useEffect, useState } from 'react';
import { CalendarIcon, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import AdminTimeSelect from '@/app/admin/components/AdminTimeSelect';
import { Button } from '@/components/ui/Button';
import { Calendar } from '@/components/ui/Calendar';
import { cn } from '@/lib/utils';
import {
  combineDateAndTime,
  DEFAULT_END_TIME,
  DEFAULT_START_TIME,
  FormField,
  formatDateValue,
  parseDateValue,
  resolveDateTimeParts,
} from './promotionPageShared';

const PromotionDateTimePicker = ({
  value,
  placeholder,
  resetLabel,
  clearLabel,
  timeLabel,
  defaultTime,
  minDateTime,
  maxDateTime,
  onChange,
}: {
  value: string;
  placeholder: string;
  resetLabel: string;
  clearLabel: string;
  timeLabel: string;
  defaultTime: string;
  minDateTime?: string;
  maxDateTime?: string;
  onChange: (value: string) => void;
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [draftDate, setDraftDate] = useState<Date | undefined>(undefined);
  const [draftTime, setDraftTime] = useState(defaultTime);
  const selectedDate = React.useMemo(() => parseDateValue(value), [value]);
  const minDate = React.useMemo(
    () => parseDateValue(minDateTime || ''),
    [minDateTime],
  );
  const maxDate = React.useMemo(
    () => parseDateValue(maxDateTime || ''),
    [maxDateTime],
  );
  const timeParts = React.useMemo(
    () => resolveDateTimeParts(value, defaultTime),
    [defaultTime, value],
  );
  const minParts = React.useMemo(
    () => resolveDateTimeParts(minDateTime || '', DEFAULT_START_TIME),
    [minDateTime],
  );
  const maxParts = React.useMemo(
    () => resolveDateTimeParts(maxDateTime || '', DEFAULT_END_TIME),
    [maxDateTime],
  );
  const minDateKey = minDate ? formatDateValue(minDate) : '';
  const maxDateKey = maxDate ? formatDateValue(maxDate) : '';
  const resolveInitialCalendarMonth = React.useCallback(
    () => selectedDate || minDate || maxDate || new Date(),
    [maxDate, minDate, selectedDate],
  );
  const [calendarMonth, setCalendarMonth] = useState<Date>(
    resolveInitialCalendarMonth,
  );
  const hasValue = Boolean(value);
  const label = selectedDate
    ? `${formatDateValue(selectedDate)} ${timeParts.time}`
    : placeholder;
  const draftDateKey = draftDate ? formatDateValue(draftDate) : '';
  const minTime =
    draftDateKey && draftDateKey === minDateKey ? minParts.time : undefined;
  const maxTime =
    draftDateKey && draftDateKey === maxDateKey ? maxParts.time : undefined;
  const isDraftTimeOutOfRange =
    (Boolean(minTime) && draftTime < String(minTime)) ||
    (Boolean(maxTime) && draftTime > String(maxTime));
  const isDayDisabled = React.useCallback(
    (date: Date) => {
      const dateKey = formatDateValue(date);
      if (minDateKey && dateKey < minDateKey) {
        return true;
      }
      if (maxDateKey && dateKey > maxDateKey) {
        return true;
      }
      return false;
    },
    [maxDateKey, minDateKey],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setDraftDate(selectedDate);
    setDraftTime(timeParts.time);
    setCalendarMonth(resolveInitialCalendarMonth());
  }, [open, resolveInitialCalendarMonth, selectedDate, timeParts.time]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  const handleApply = () => {
    if (!draftDate) {
      return;
    }
    onChange(
      combineDateAndTime(formatDateValue(draftDate), draftTime || defaultTime),
    );
    setOpen(false);
  };

  return (
    <div className='relative'>
      <Button
        size='sm'
        variant='outline'
        type='button'
        aria-label={placeholder}
        onClick={() => setOpen(current => !current)}
        className={cn(
          'h-9 w-full justify-start font-normal',
          hasValue ? 'pr-16' : 'pr-10',
        )}
      >
        <span
          className={cn(
            'flex-1 truncate text-left',
            value ? 'text-foreground' : 'text-muted-foreground',
          )}
        >
          {label}
        </span>
      </Button>
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
            onChange('');
          }}
        >
          <X className='h-3.5 w-3.5' />
        </button>
      ) : null}
      <CalendarIcon className='pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
      {open ? (
        <div className='fixed inset-0 z-[70] flex items-center justify-center p-4'>
          <button
            type='button'
            aria-label={clearLabel}
            className='absolute inset-0 bg-black/20'
            onClick={() => setOpen(false)}
          />
          <div
            className='relative w-auto max-w-[calc(100vw-2rem)] overflow-auto rounded-md border bg-popover p-0 shadow-md'
            onClick={event => event.stopPropagation()}
          >
            <Calendar
              mode='single'
              month={calendarMonth}
              numberOfMonths={1}
              selected={draftDate}
              disabled={isDayDisabled}
              onMonthChange={setCalendarMonth}
              onSelect={date => {
                setDraftDate(date || undefined);
                if (date) {
                  setCalendarMonth(date);
                }
              }}
              className='p-3 md:p-4 [--cell-size:2.3rem]'
            />
            <div className='border-t border-border px-4 py-3'>
              <FormField label={timeLabel}>
                <AdminTimeSelect
                  value={draftTime}
                  onChange={setDraftTime}
                  minTime={minTime}
                  maxTime={maxTime}
                  dropdownClassName='bottom-full top-auto mb-1 mt-0'
                />
              </FormField>
            </div>
            <div className='flex items-center justify-end gap-2 border-t border-border px-3 py-2'>
              <Button
                size='sm'
                variant='ghost'
                type='button'
                onClick={() => {
                  onChange('');
                  setOpen(false);
                }}
              >
                {resetLabel}
              </Button>
              <Button
                size='sm'
                type='button'
                disabled={!draftDate || isDraftTimeOutOfRange}
                onClick={handleApply}
              >
                {t('common.core.confirm')}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default PromotionDateTimePicker;
