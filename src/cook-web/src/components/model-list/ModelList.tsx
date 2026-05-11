import { useShifu } from '@/store';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/Select';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import { ModelOption } from '@/types/shifu';

function ModelOptionLabel({
  label,
  creditMultiplier,
}: {
  label: string;
  creditMultiplier?: number | null;
}) {
  return (
    <span className='flex w-full min-w-0 items-center'>
      <span
        aria-hidden='true'
        className='w-8 shrink-0'
      />
      <span className='min-w-0 flex-1 truncate text-left'>{label}</span>
      {creditMultiplier ? (
        <span className='ml-2 shrink-0 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-medium leading-none text-primary'>
          {creditMultiplier}x
        </span>
      ) : null}
      <span
        aria-hidden='true'
        className='w-6 shrink-0'
      />
    </span>
  );
}

export default function ModelList({
  value,
  className,
  onChange,
  disabled,
}: {
  value: string;
  className?: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const { models } = useShifu();
  const { t } = useTranslation();

  const options: ModelOption[] = models || [];

  // Empty string is used to represent using the default model. However, the Select component uses empty string as unselected.
  // So we need to use a special value to represent the empty state in the Select component.
  const DEFAULT_MODEL_OPTION_VALUE = '__empty__';
  const displayValue = value === '' ? DEFAULT_MODEL_OPTION_VALUE : value;
  const defaultOption = {
    label: t('common.core.default'),
    creditMultiplier: 1,
  };
  const selectedOption =
    displayValue === DEFAULT_MODEL_OPTION_VALUE
      ? defaultOption
      : options.find(item => item.value === displayValue);

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
      <SelectTrigger
        className={cn(
          'relative w-full px-1 [&>svg]:absolute [&>svg]:right-3',
          className,
        )}
      >
        <SelectValue
          asChild
          placeholder={t('common.core.selectModel')}
        >
          <span className='flex min-w-0 w-full'>
            {selectedOption ? (
              <ModelOptionLabel
                label={selectedOption.label}
                creditMultiplier={selectedOption.creditMultiplier}
              />
            ) : (
              t('common.core.selectModel')
            )}
          </span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem
          key='default'
          value={DEFAULT_MODEL_OPTION_VALUE}
          textValue={defaultOption.label}
          className='pl-0 pr-0'
        >
          <ModelOptionLabel
            label={defaultOption.label}
            creditMultiplier={defaultOption.creditMultiplier}
          />
        </SelectItem>
        {options.map(item => {
          return (
            <SelectItem
              key={item.value}
              value={item.value}
              textValue={item.label}
              className='pl-0 pr-0'
            >
              <ModelOptionLabel
                label={item.label}
                creditMultiplier={item.creditMultiplier}
              />
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}
