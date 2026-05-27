import { X } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';

type AdminClearableInputProps = {
  id?: string;
  value: string;
  placeholder: string;
  clearLabel: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  className?: string;
};

export default function AdminClearableInput({
  id,
  value,
  placeholder,
  clearLabel,
  onChange,
  onSubmit,
  className,
}: AdminClearableInputProps) {
  const hasValue = value.trim().length > 0;

  return (
    <div className='relative'>
      <Input
        id={id}
        value={value}
        onChange={event => onChange(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter' && onSubmit) {
            event.preventDefault();
            onSubmit();
          }
        }}
        placeholder={placeholder}
        className={cn('h-9', hasValue && 'pr-9', className)}
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
