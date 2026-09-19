import {
  forwardRef,
  type ComponentPropsWithoutRef,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import type { ModelIndex } from '@/types/shifu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';

export type ModelIndexOption = {
  index: ModelIndex;
  display_name: string;
  available: boolean;
  is_default?: boolean;
  credit_multiplier?: number | null;
  credit_multiplier_label?: string | null;
};

type CourseModelSelectProps = Omit<
  ComponentPropsWithoutRef<typeof SelectTrigger>,
  'value' | 'onChange'
> & {
  value: ModelIndex | null;
  onChange: (index: ModelIndex) => void;
  displayName?: string;
  fallback?: boolean;
};

const CourseModelSelect = forwardRef<HTMLButtonElement, CourseModelSelectProps>(
  function CourseModelSelect(
    { value, onChange, displayName, fallback, disabled, ...triggerProps },
    ref,
  ) {
    const { t } = useTranslation();
    const [options, setOptions] = useState<ModelIndexOption[]>([]);
    const requestVersion = useRef(0);
    const selectedThisOpen = useRef(false);
    const pointerType = useRef('touch');
    const loadOptions = useCallback(async () => {
      const version = ++requestVersion.current;
      try {
        const result = await api.getCourseModelOptions({});
        if (version === requestVersion.current)
          setOptions(
            Array.isArray(result)
              ? result
                  .filter(item => /^[1-9]$/.test(item.index))
                  .sort((a, b) => Number(a.index) - Number(b.index))
              : [],
          );
      } catch {
        // Retain the last known labels when a catalog refresh fails.
      }
    }, []);
    useEffect(() => {
      void loadOptions();
      return () => {
        requestVersion.current++;
      };
    }, [loadOptions]);
    const select = (index: ModelIndex) => {
      if (disabled || selectedThisOpen.current) return;
      selectedThisOpen.current = true;
      onChange(index);
    };
    const optionLabel = (option: ModelIndexOption) => {
      const multiplier =
        option.credit_multiplier_label ||
        (option.credit_multiplier ? `${option.credit_multiplier}x` : '');
      return (
        <span className='flex w-full items-center gap-2'>
          <span>{option.display_name}</span>
          {multiplier ? (
            <span className='text-xs text-muted-foreground'>{multiplier}</span>
          ) : null}
        </span>
      );
    };
    const selected = options.find(item => item.index === value);
    return (
      <div className='space-y-2'>
        <Select
          value={value || ''}
          onValueChange={index => select(index as ModelIndex)}
          onOpenChange={open => {
            if (open) {
              selectedThisOpen.current = false;
              void loadOptions();
            }
          }}
          disabled={disabled}
        >
          <SelectTrigger
            className='h-9'
            {...triggerProps}
            ref={ref}
          >
            <SelectValue asChild>
              <span>
                {selected
                  ? optionLabel(selected)
                  : displayName ||
                    t('module.shifuSetting.modelOptions.unavailable')}
              </span>
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {options.map(option => (
              <SelectItem
                key={option.index}
                value={option.index}
                textValue={option.display_name}
                disabled={!option.available}
                // Radix does not emit onValueChange for the selected item.
                // An explicit re-selection must still persist a fallback to 1.
                onPointerDown={event => {
                  pointerType.current = event.pointerType;
                }}
                onPointerMove={event => {
                  pointerType.current = event.pointerType;
                }}
                onPointerUp={event => {
                  if (
                    !event.defaultPrevented &&
                    pointerType.current === 'mouse' &&
                    option.available &&
                    option.index === value
                  )
                    select(option.index);
                }}
                onClick={event => {
                  if (
                    !event.defaultPrevented &&
                    pointerType.current !== 'mouse' &&
                    option.available &&
                    option.index === value
                  )
                    select(option.index);
                }}
                onKeyDown={event => {
                  if (
                    option.available &&
                    option.index === value &&
                    (event.key === 'Enter' || event.key === ' ')
                  )
                    select(option.index);
                }}
              >
                {optionLabel(option)}
                {!option.available ? (
                  <span className='ml-2 text-xs text-muted-foreground'>
                    {t('module.shifuSetting.modelOptions.unavailable')}
                  </span>
                ) : null}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {fallback ? (
          <p
            className='text-xs text-muted-foreground'
            role='status'
          >
            {t('module.shifuSetting.modelOptions.fallback')}
          </p>
        ) : null}
      </div>
    );
  },
);

export default CourseModelSelect;
