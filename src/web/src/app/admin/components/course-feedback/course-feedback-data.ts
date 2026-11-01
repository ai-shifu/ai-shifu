/**
 * Request and environment helpers shared by the course follow-up and rating
 * pages on both the teacher dashboard and the operator admin surfaces.
 */
import { useMemo } from 'react';
import {
  resolveLoginIdentifierTypes,
  selectSingleLoginIdentifierType,
  type LoginIdentifierType,
} from '@/lib/login-identifiers';
import { ErrorWithCode } from '@/lib/request';
import { useEnvStore } from '@/store';
import type { CourseFeedbackErrorState } from './course-feedback-display';

export const resolveRequestErrorState = (
  error: unknown,
  fallbackMessage: string,
): CourseFeedbackErrorState => {
  if (error instanceof ErrorWithCode) {
    return { message: error.message, code: error.code };
  }
  if (error instanceof Error) {
    return { message: error.message };
  }
  return { message: fallbackMessage };
};

/**
 * Picks the single login identifier type (phone or email) used to label and
 * display learner accounts, based on the enabled login methods.
 */
export const useDisplayIdentifierType = (): LoginIdentifierType => {
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const defaultLoginMethod = useEnvStore(state => state.defaultLoginMethod);
  return useMemo<LoginIdentifierType>(
    () =>
      selectSingleLoginIdentifierType(
        resolveLoginIdentifierTypes(loginMethodsEnabled),
        defaultLoginMethod,
      ),
    [defaultLoginMethod, loginMethodsEnabled],
  );
};
