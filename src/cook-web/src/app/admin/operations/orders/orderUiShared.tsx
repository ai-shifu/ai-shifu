import { X } from 'lucide-react';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';

export const ALL_OPTION_VALUE = '__all__';
export const EMPTY_STATE_LABEL = '--';

export const ORDER_TABS_LIST_CLASSNAME =
  'h-11 w-fit justify-start self-start rounded-[12px] bg-[var(--base-muted,#F5F5F5)] p-[3px] shadow-sm';

export const ORDER_TABS_TRIGGER_CLASSNAME =
  'h-full rounded-[10px] border border-transparent px-5 py-2 text-sm font-medium text-[var(--base-foreground,#0A0A0A)] data-[state=active]:bg-white data-[state=active]:shadow-[0_1px_3px_rgba(0,0,0,0.1),0_1px_2px_rgba(0,0,0,0.06)]';

export const renderTooltipText = (text?: string, className?: string) => (
  <AdminTooltipText
    text={text}
    emptyValue={EMPTY_STATE_LABEL}
    className={className}
  />
);

export function ClearableTextInput({
  value,
  placeholder,
  clearLabel,
  onChange,
}: {
  value: string;
  placeholder: string;
  clearLabel: string;
  onChange: (value: string) => void;
}) {
  const hasValue = value.trim().length > 0;

  return (
    <div className='relative'>
      <Input
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className={cn('h-9', hasValue && 'pr-9')}
      />
      {hasValue ? (
        <button
          type='button'
          aria-label={clearLabel}
          className='absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground'
          onMouseDown={event => event.preventDefault()}
          onClick={() => onChange('')}
        >
          <X className='h-3.5 w-3.5' />
        </button>
      ) : null}
    </div>
  );
}
