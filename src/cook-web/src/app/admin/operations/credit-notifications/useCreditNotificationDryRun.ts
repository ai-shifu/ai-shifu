import React from 'react';
import type { TFunction } from 'i18next';
import api from '@/api';
import { ErrorWithCode } from '@/lib/request';
import type { AdminOperationCreditNotificationDryRunResponse } from '../operation-credit-notification-types';

export function useCreditNotificationDryRun(t: TFunction) {
  const [dryRunResult, setDryRunResult] =
    React.useState<AdminOperationCreditNotificationDryRunResponse | null>(null);
  const [dryRunError, setDryRunError] = React.useState('');

  const runDryRun = React.useCallback(
    async (notificationType: string) => {
      try {
        const response = (await api.dryRunAdminOperationCreditNotifications({
          notification_type: notificationType.trim(),
          creator_bid: '',
        })) as AdminOperationCreditNotificationDryRunResponse;
        setDryRunResult(response);
        setDryRunError('');
        return true;
      } catch (requestError) {
        const resolvedError = requestError as ErrorWithCode;
        setDryRunResult(null);
        setDryRunError(resolvedError.message || t('common.core.submitFailed'));
        return false;
      }
    },
    [t],
  );

  return {
    dryRunError,
    dryRunResult,
    runDryRun,
  };
}
