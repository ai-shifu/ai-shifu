export const PAGE_SIZE = 20;
export const USAGE_PROGRESS_SEPARATOR = '/';
export const ALL_OPTION_VALUE = '__all__';
export const SINGLE_SELECT_ITEM_CLASS =
  'pl-3 pr-8 data-[state=checked]:bg-muted data-[state=checked]:text-foreground';
export const SINGLE_SELECT_INDICATOR_CLASS = 'left-auto right-2';
export const FILTER_LABEL_CLASS =
  'shrink-0 whitespace-nowrap text-[length:var(--text-sm-font-size,14px)] not-italic font-[var(--font-weight-medium,500)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-foreground,#0A0A0A)]';

export type RedemptionCodeFilters = {
  keyword: string;
  name: string;
  course_query: string;
  usage_type: string;
  ops_state: string;
  discount_type: string;
  status: string;
  start_time: string;
  end_time: string;
};

export const createDefaultFilters = (): RedemptionCodeFilters => ({
  keyword: '',
  name: '',
  course_query: '',
  usage_type: '',
  ops_state: '',
  discount_type: '',
  status: '',
  start_time: '',
  end_time: '',
});

export const toSelectValue = (value: string) => value || ALL_OPTION_VALUE;

export const fromSelectValue = (value: string) =>
  value === ALL_OPTION_VALUE ? '' : value;
