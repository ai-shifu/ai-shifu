import { useShifu } from '../../store/useShifu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/Select';
import { cn } from '../../lib/utils';
import { useTranslation } from 'react-i18next';
import { ModelOption } from '@/types/shifu';

export default function ModelList({
  value,
  className,
  onChange,
  disabled,
  options,
  showDefaultOption = true,
}: {
  value: string;
  className?: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  options?: ModelOption[];
  showDefaultOption?: boolean;
}) {
  const { models } = useShifu();
  const { t } = useTranslation();

  const resolvedOptions: ModelOption[] = options || models || [];

  // Empty string is used to represent using the default model. However, the Select component uses empty string as unselected.
  // So we need to use a special value to represent the empty state in the Select component.
  const DEFAULT_MODEL_OPTION_VALUE = '__empty__';
  const displayValue =
    showDefaultOption && value === '' ? DEFAULT_MODEL_OPTION_VALUE : value;

  const handleChange = (selectedValue: string) => {
    // If the selected value is the empty value, we need to pass an empty string
    const outputValue =
      selectedValue === DEFAULT_MODEL_OPTION_VALUE ? '' : selectedValue;
    onChange(outputValue);
  };

  return (
    <Select
      onValueChange={handleChange}
      value={displayValue}
      disabled={disabled}
    >
      <SelectTrigger className={cn('w-full', className)}>
        <SelectValue placeholder={t('common.core.selectModel')} />
      </SelectTrigger>
      <SelectContent>
        {showDefaultOption && (
          <SelectItem
            key='default'
            value={DEFAULT_MODEL_OPTION_VALUE}
          >
            {t('common.core.default')}
          </SelectItem>
        )}
        {resolvedOptions.map(item => {
          return (
            <SelectItem
              key={item.value}
              value={item.value}
            >
              <span className='flex w-full items-center justify-between gap-2'>
                <span>{item.label}</span>
                {item.credit_multiplier_label ? (
                  <span className='rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground'>
                    {item.credit_multiplier_label}
                  </span>
                ) : null}
              </span>
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}
