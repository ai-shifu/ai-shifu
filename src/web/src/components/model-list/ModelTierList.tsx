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
import type { ModelTier } from '@/types/shifu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';

export type ModelTierOption = {
  tier: ModelTier;
  available: boolean;
  credit_multiplier?: number | null;
  credit_multiplier_label?: string | null;
};

const TIERS: ModelTier[] = ['fast', 'balanced', 'ultimate'];

type ModelTierListProps = Omit<
  ComponentPropsWithoutRef<typeof SelectTrigger>,
  'value' | 'onChange'
> & {
  value: ModelTier | null;
  onChange: (tier: ModelTier) => void;
};

const ModelTierList = forwardRef<HTMLButtonElement, ModelTierListProps>(
  function ModelTierList({ value, onChange, disabled, ...triggerProps }, ref) {
    const { t } = useTranslation();
    const [options, setOptions] = useState<ModelTierOption[]>([]);
    const requestVersion = useRef(0);
    const loadOptions = useCallback(async () => {
      const version = ++requestVersion.current;
      try {
        const result = await api.getModelTierList({});
        if (version === requestVersion.current)
          setOptions(Array.isArray(result) ? result : []);
      } catch {
        if (version === requestVersion.current) setOptions([]);
      }
    }, []);
    useEffect(() => {
      void loadOptions();
      return () => {
        requestVersion.current++;
      };
    }, [loadOptions]);
    const label = (tier: ModelTier) =>
      t(`module.shifuSetting.modelTiers.${tier}`);
    const optionLabel = (tier: ModelTier) => {
      const option = options.find(item => item.tier === tier);
      const multiplier =
        option?.credit_multiplier_label ||
        (option?.credit_multiplier ? `${option.credit_multiplier}x` : '');
      return (
        <span className='flex w-full items-center gap-2'>
          <span>{label(tier)}</span>
          {multiplier ? (
            <span className='text-xs text-muted-foreground'>{multiplier}</span>
          ) : null}
        </span>
      );
    };
    return (
      <Select
        value={value || ''}
        onValueChange={tier => onChange(tier as ModelTier)}
        onOpenChange={open => {
          if (open) void loadOptions();
        }}
        disabled={disabled}
      >
        <SelectTrigger
          className='h-9'
          {...triggerProps}
          ref={ref}
        >
          <SelectValue
            asChild
            placeholder={t('module.shifuSetting.modelTiers.legacy')}
          >
            <span>
              {value
                ? optionLabel(value)
                : t('module.shifuSetting.modelTiers.legacy')}
            </span>
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {TIERS.map(tier => (
            <SelectItem
              key={tier}
              value={tier}
              textValue={label(tier)}
              disabled={!options.find(item => item.tier === tier)?.available}
            >
              {optionLabel(tier)}
              {!options.find(item => item.tier === tier)?.available ? (
                <span className='ml-2 text-xs text-muted-foreground'>
                  {t('module.shifuSetting.modelTiers.unavailable')}
                </span>
              ) : null}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  },
);

export default ModelTierList;
