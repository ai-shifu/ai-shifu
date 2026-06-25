import type { ReactNode } from 'react';
import AdminClearableInput from '@/app/admin/components/AdminClearableInput';
import AdminDateRangeFilter from '@/app/admin/components/AdminDateRangeFilter';
import type { AdminFilterItem } from '@/app/admin/components/AdminFilter';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { cn } from '@/lib/utils';

export type AdminFilterSelectOption = {
  value: string;
  label: ReactNode;
};

type CreateTextFilterItemParams = {
  key: string;
  label: ReactNode;
  value?: string | null;
  placeholder: string;
  clearLabel: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  contentClassName?: string;
  itemClassName?: string;
  labelClassName?: string;
  inputClassName?: string;
};

type CreateSelectFilterItemParams = {
  key: string;
  label: ReactNode;
  value: string;
  placeholder: string;
  options: AdminFilterSelectOption[];
  onChange: (value: string) => void;
  contentClassName?: string;
  itemClassName?: string;
  labelClassName?: string;
  triggerClassName?: string;
  selectItemClassName?: string;
  indicatorClassName?: string;
};

type CreateDateRangeFilterItemParams = {
  key: string;
  label: ReactNode;
  startValue: string;
  endValue: string;
  placeholder: string;
  resetLabel: string;
  clearLabel: string;
  onChange: (range: { start: string; end: string }) => void;
  contentClassName?: string;
  itemClassName?: string;
  labelClassName?: string;
};

export const createTextFilterItem = ({
  key,
  label,
  value,
  placeholder,
  clearLabel,
  onChange,
  onSubmit,
  contentClassName,
  itemClassName,
  labelClassName,
  inputClassName,
}: CreateTextFilterItemParams): AdminFilterItem => ({
  key,
  label,
  contentClassName,
  itemClassName,
  labelClassName,
  component: (
    <AdminClearableInput
      value={value}
      onChange={onChange}
      onSubmit={onSubmit}
      placeholder={placeholder}
      clearLabel={clearLabel}
      className={inputClassName}
    />
  ),
});

export const createSelectFilterItem = ({
  key,
  label,
  value,
  placeholder,
  options,
  onChange,
  contentClassName,
  itemClassName,
  labelClassName,
  triggerClassName,
  selectItemClassName,
  indicatorClassName,
}: CreateSelectFilterItemParams): AdminFilterItem => ({
  key,
  label,
  contentClassName,
  itemClassName,
  labelClassName,
  component: (
    <Select
      value={value}
      onValueChange={onChange}
    >
      <SelectTrigger className={cn('h-9', triggerClassName)}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map(option => (
          <SelectItem
            key={option.value}
            value={option.value}
            className={selectItemClassName}
            indicatorClassName={indicatorClassName}
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  ),
});

export const createDateRangeFilterItem = ({
  key,
  label,
  startValue,
  endValue,
  placeholder,
  resetLabel,
  clearLabel,
  onChange,
  contentClassName,
  itemClassName,
  labelClassName,
}: CreateDateRangeFilterItemParams): AdminFilterItem => ({
  key,
  label,
  contentClassName,
  itemClassName,
  labelClassName,
  component: (
    <AdminDateRangeFilter
      startValue={startValue}
      endValue={endValue}
      onChange={onChange}
      placeholder={placeholder}
      resetLabel={resetLabel}
      clearLabel={clearLabel}
    />
  ),
});
