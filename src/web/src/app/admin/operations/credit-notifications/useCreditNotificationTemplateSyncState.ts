import React from 'react';
import type { TFunction } from 'i18next';
import api from '@/api';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminOperationCreditNotificationTemplateOption,
  AdminOperationCreditNotificationTemplateSyncResponse,
} from '../operation-credit-notification-types';
import type { KnownNotificationType } from './creditNotificationUtils';

export function useCreditNotificationTemplateSyncState({
  policyTypes,
  setTemplateOptions,
  t,
}: {
  policyTypes: Record<KnownNotificationType, { template_code: string }>;
  setTemplateOptions: React.Dispatch<
    React.SetStateAction<AdminOperationCreditNotificationTemplateOption[]>
  >;
  t: TFunction;
}) {
  const [templateSyncResults, setTemplateSyncResults] = React.useState<
    Partial<
      Record<
        KnownNotificationType,
        AdminOperationCreditNotificationTemplateSyncResponse
      >
    >
  >({});
  const [templateSyncLoading, setTemplateSyncLoading] = React.useState<
    Partial<Record<KnownNotificationType, boolean>>
  >({});
  const [templateSyncError, setTemplateSyncError] = React.useState('');

  const syncTemplate = React.useCallback(
    async (
      notificationType: KnownNotificationType,
      templateCodeOverride?: string,
    ) => {
      const templateCode = (
        templateCodeOverride ?? policyTypes[notificationType].template_code
      ).trim();
      if (!templateCode) {
        setTemplateSyncError(
          t(
            'module.operationsCreditNotifications.config.templateSync.templateCodeRequired',
          ),
        );
        return false;
      }
      setTemplateSyncLoading(current => ({
        ...current,
        [notificationType]: true,
      }));
      try {
        const response =
          (await api.syncAdminOperationCreditNotificationTemplate({
            notification_type: notificationType,
            template_code: templateCode,
          })) as AdminOperationCreditNotificationTemplateSyncResponse;
        setTemplateSyncResults(current => ({
          ...current,
          [notificationType]: response,
        }));
        setTemplateOptions(current => {
          const nextOption: AdminOperationCreditNotificationTemplateOption = {
            notification_template_bid: response.notification_template_bid,
            channel: response.channel,
            provider: response.provider,
            template_code: response.template_code,
            template_name: response.template_name,
            template_content: response.template_content,
            template_status: response.template_status,
            template_type: response.template_type,
            sync_status: response.sync_status,
            error_code: response.error_code,
            error_message: response.error_message,
            placeholders: response.placeholders,
            compatible_notification_types: response.compatible
              ? [notificationType]
              : [],
            last_synced_at: response.last_synced_at,
            source: 'local',
          };
          return [
            nextOption,
            ...current.filter(
              option =>
                option.template_code !== response.template_code ||
                !option.compatible_notification_types?.includes(
                  notificationType,
                ),
            ),
          ];
        });
        setTemplateSyncError('');
        return Boolean(response.compatible);
      } catch (requestError) {
        const resolvedError = requestError as ErrorWithCode;
        setTemplateSyncError(
          resolvedError.message ||
            t(
              'module.operationsCreditNotifications.config.templateSync.syncFailed',
            ),
        );
        return false;
      } finally {
        setTemplateSyncLoading(current => ({
          ...current,
          [notificationType]: false,
        }));
      }
    },
    [policyTypes, setTemplateOptions, t],
  );

  const clearTemplateSyncResult = React.useCallback(
    (notificationType: KnownNotificationType) => {
      setTemplateSyncResults(current => {
        if (current[notificationType] === undefined) {
          return current;
        }
        return {
          ...current,
          [notificationType]: undefined,
        };
      });
    },
    [],
  );

  return {
    clearTemplateSyncResult,
    syncTemplate,
    templateSyncError,
    templateSyncLoading,
    templateSyncResults,
  };
}
