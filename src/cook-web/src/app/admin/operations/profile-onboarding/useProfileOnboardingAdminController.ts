import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import type {
  ProfileOnboardingRunSession,
  ProfileOnboardingSessionInfo,
} from '@/components/profile-onboarding/ProfileOnboardingConversation';
import { useToast } from '@/hooks/useToast';
import { streamProfileOnboardingRuntime } from '@/lib/profileOnboardingSse';
import type { ErrorWithCode } from '@/lib/request';

type ProfileOnboardingConfig = {
  enabled?: boolean;
  markdownflow?: string;
  config_revision?: number;
  allowed_variable_keys?: string[];
  version?: number;
  updated_by?: string;
  updated_at?: string;
};

export const useProfileOnboardingAdminController = (isReady: boolean) => {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const [enabled, setEnabled] = React.useState(false);
  const [markdownflow, setMarkdownflow] = React.useState('');
  const [configRevision, setConfigRevision] = React.useState(0);
  const [updatedBy, setUpdatedBy] = React.useState('');
  const [updatedAt, setUpdatedAt] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState('');
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [previewKey, setPreviewKey] = React.useState(0);
  const [previewDraft, setPreviewDraft] = React.useState('');
  const loadStartedRef = React.useRef(false);
  const defaultMarkdownflow = t(
    'module.profileOnboarding.admin.defaultMarkdownflow',
  );

  React.useEffect(() => {
    if (!isReady || loadStartedRef.current) {
      return;
    }
    loadStartedRef.current = true;
    setLoading(true);
    void api
      .getAdminOperationProfileOnboardingConfig({})
      .then((response: ProfileOnboardingConfig) => {
        const loadedRevision = Number(
          response.config_revision ?? response.version ?? 0,
        );
        const hasStoredConfiguration = loadedRevision > 0;
        setEnabled(Boolean(response.enabled));
        setMarkdownflow(
          hasStoredConfiguration
            ? (response.markdownflow ?? defaultMarkdownflow)
            : response.markdownflow || defaultMarkdownflow,
        );
        setConfigRevision(loadedRevision);
        setUpdatedBy(response.updated_by || '');
        setUpdatedAt(response.updated_at || '');
        setError('');
      })
      .catch((caughtError: unknown) => {
        const typedError = caughtError as Partial<ErrorWithCode>;
        setError(
          typedError.message || t('module.profileOnboarding.admin.loadFailed'),
        );
      })
      .finally(() => {
        setLoading(false);
      });
  }, [defaultMarkdownflow, isReady, t]);

  const save = React.useCallback(async () => {
    if (enabled && !markdownflow.trim()) {
      setError(t('module.profileOnboarding.admin.documentRequired'));
      return;
    }
    const submittedConfig = { enabled, markdownflow };
    setSaving(true);
    setError('');
    try {
      const response = (await api.updateAdminOperationProfileOnboardingConfig({
        enabled: submittedConfig.enabled,
        markdownflow: submittedConfig.markdownflow,
      })) as ProfileOnboardingConfig;
      setEnabled(currentValue =>
        currentValue === submittedConfig.enabled
          ? Boolean(response.enabled)
          : currentValue,
      );
      setMarkdownflow(currentValue =>
        currentValue === submittedConfig.markdownflow
          ? (response.markdownflow ?? submittedConfig.markdownflow)
          : currentValue,
      );
      setConfigRevision(
        Number(response.config_revision ?? response.version ?? configRevision),
      );
      setUpdatedBy(response.updated_by || updatedBy);
      setUpdatedAt(response.updated_at || updatedAt);
      toast({ title: t('module.profileOnboarding.admin.saveSuccess') });
    } catch (caughtError) {
      const typedError = caughtError as Partial<ErrorWithCode>;
      setError(
        typedError.message || t('module.profileOnboarding.admin.saveFailed'),
      );
    } finally {
      setSaving(false);
    }
  }, [configRevision, enabled, markdownflow, t, toast, updatedAt, updatedBy]);

  const createPreviewSession = React.useCallback(async () => {
    setPreviewDraft('');
    setError('');
    return (await api.createAdminOperationProfileOnboardingPreview({
      markdownflow,
      language: i18n.resolvedLanguage ?? i18n.language,
    })) as ProfileOnboardingSessionInfo;
  }, [i18n.language, i18n.resolvedLanguage, markdownflow]);

  const runPreviewSession = React.useCallback<ProfileOnboardingRunSession>(
    ({
      sessionId,
      expectedBlockIndex,
      requestId,
      userInput,
      onMessage,
      onError,
    }) =>
      streamProfileOnboardingRuntime({
        path: `/api/shifu/admin/operations/profile-onboarding/preview/${encodeURIComponent(sessionId)}/run`,
        payload: {
          expected_block_index: expectedBlockIndex,
          request_id: requestId,
          ...(userInput ? { user_input: userInput } : {}),
        },
        language: i18n.resolvedLanguage ?? i18n.language,
        onMessage,
        onError,
      }),
    [i18n.language, i18n.resolvedLanguage],
  );

  const startPreview = React.useCallback(() => {
    setPreviewDraft('');
    setPreviewOpen(true);
    setPreviewKey(key => key + 1);
  }, []);

  const handlePreviewError = React.useCallback(
    (caughtError: unknown) => {
      setError(
        caughtError instanceof Error && caughtError.message
          ? caughtError.message
          : t('module.profileOnboarding.admin.previewFailed'),
      );
    },
    [t],
  );

  return {
    enabled,
    setEnabled,
    markdownflow,
    setMarkdownflow,
    configRevision,
    updatedBy,
    updatedAt,
    loading,
    saving,
    error,
    setError,
    previewOpen,
    previewKey,
    previewDraft,
    setPreviewDraft,
    save,
    startPreview,
    hidePreview: () => setPreviewOpen(false),
    previewConversationProps: {
      createSession: createPreviewSession,
      runSession: runPreviewSession,
      onDraftReady: setPreviewDraft,
      onRetry: () => setError(''),
      onError: handlePreviewError,
    },
  };
};
