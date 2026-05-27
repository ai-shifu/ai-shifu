import { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

const TIME_HOURS = Array.from({ length: 24 }, (_, index) =>
  String(index).padStart(2, '0'),
);
const TIME_MINUTES = Array.from({ length: 60 }, (_, index) =>
  String(index).padStart(2, '0'),
);
const DEFAULT_TIME = '00:00';

export const parseAdminTimeValue = (value: string) => {
  const matched = /^(\d{2}):(\d{2})$/.exec(String(value || '').trim());
  if (!matched) {
    return { hour: '00', minute: '00' };
  }
  const [, hour, minute] = matched;
  return {
    hour: TIME_HOURS.includes(hour) ? hour : '00',
    minute: TIME_MINUTES.includes(minute) ? minute : '00',
  };
};

type AdminTimeSelectProps = {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  triggerClassName?: string;
  dropdownClassName?: string;
};

const renderTimeOptionClassName = (selected: boolean) =>
  cn(
    'flex h-8 w-full items-center justify-center rounded-sm text-sm transition-colors',
    selected
      ? 'bg-primary text-primary-foreground'
      : 'text-foreground hover:bg-accent hover:text-accent-foreground',
  );

const scrollTimeOptionIntoView = (
  container: HTMLDivElement | null,
  value: string,
) => {
  const option = container?.querySelector(`[data-time-value="${value}"]`);
  if (option instanceof HTMLElement && option.scrollIntoView) {
    option.scrollIntoView({ block: 'center' });
  }
};

export default function AdminTimeSelect({
  id,
  value,
  onChange,
  className,
  triggerClassName,
  dropdownClassName,
}: AdminTimeSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const hourListRef = useRef<HTMLDivElement>(null);
  const minuteListRef = useRef<HTMLDivElement>(null);
  const { hour, minute } = parseAdminTimeValue(value || DEFAULT_TIME);
  const displayTime = [hour, minute].join(':');
  const updateTime = (next: { hour?: string; minute?: string }) => {
    onChange(`${next.hour ?? hour}:${next.minute ?? minute}`);
  };

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    scrollTimeOptionIntoView(hourListRef.current, hour);
    scrollTimeOptionIntoView(minuteListRef.current, minute);
  }, [hour, minute, open]);

  return (
    <div
      ref={rootRef}
      className={cn('relative', className)}
    >
      <button
        id={id}
        type='button'
        className={cn(
          'flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 text-left text-sm ring-offset-background transition-colors hover:border-muted-foreground/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-2',
          triggerClassName,
        )}
        onClick={() => setOpen(current => !current)}
      >
        <span className='text-base text-foreground'>{displayTime}</span>
        <ChevronDown className='h-4 w-4 text-muted-foreground' />
      </button>
      {open ? (
        <div
          className={cn(
            'absolute left-0 top-full z-[112] mt-1 grid w-full min-w-44 grid-cols-2 overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-md',
            dropdownClassName,
          )}
        >
          <div
            ref={hourListRef}
            className='max-h-56 overflow-y-auto border-r border-border p-1'
          >
            {TIME_HOURS.map(item => (
              <button
                key={item}
                type='button'
                data-time-value={item}
                className={renderTimeOptionClassName(item === hour)}
                onClick={() => updateTime({ hour: item })}
              >
                {item}
              </button>
            ))}
          </div>
          <div
            ref={minuteListRef}
            className='max-h-56 overflow-y-auto p-1'
          >
            {TIME_MINUTES.map(item => (
              <button
                key={item}
                type='button'
                data-time-value={item}
                className={renderTimeOptionClassName(item === minute)}
                onClick={() => updateTime({ minute: item })}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
