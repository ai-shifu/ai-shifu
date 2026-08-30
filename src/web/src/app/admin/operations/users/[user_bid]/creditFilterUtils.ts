import type { AdminOperationUserCreditFilters } from '../../operation-user-types';

export const FILTER_ALL_OPTION = 'all';

export const createUserCreditFilters = (): AdminOperationUserCreditFilters => ({
  creditType: FILTER_ALL_OPTION,
  grantSource: FILTER_ALL_OPTION,
  courseQuery: '',
  usageScene: FILTER_ALL_OPTION,
  usageMode: FILTER_ALL_OPTION,
  startTime: '',
  endTime: '',
});

export const sanitizeCreditFiltersByType = (
  filters: AdminOperationUserCreditFilters,
): AdminOperationUserCreditFilters => {
  if (filters.creditType === 'grant') {
    return {
      ...filters,
      courseQuery: '',
      usageScene: FILTER_ALL_OPTION,
      usageMode: FILTER_ALL_OPTION,
    };
  }
  if (filters.creditType === 'consume') {
    return {
      ...filters,
      grantSource: FILTER_ALL_OPTION,
    };
  }
  if (filters.creditType === 'other') {
    return {
      ...filters,
      grantSource: FILTER_ALL_OPTION,
      courseQuery: '',
      usageScene: FILTER_ALL_OPTION,
      usageMode: FILTER_ALL_OPTION,
    };
  }
  return createUserCreditFilters();
};
