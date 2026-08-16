export const PAGE_SIZE = 20;
export const USAGE_PROGRESS_SEPARATOR = '/';
export const ALL_OPTION_VALUE = '__all__';

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
