'use client';

import React from 'react';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import Loading from '@/components/loading';
import ProfileOnboardingConversation, {
  type ProfileOnboardingRunSession,
  type ProfileOnboardingSessionInfo,
} from '@/components/profile-onboarding/ProfileOnboardingConversation';
import { Button } from '@/components/ui/Button';
import { Label } from '@/components/ui/Label';
import { Switch } from '@/components/ui/Switch';
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/hooks/useToast';
import { streamProfileOnboardingRuntime } from '@/lib/profileOnboardingSse';
import { ErrorWithCode } from '@/lib/request';
import { useTranslation } from 'react-i18next';
import useOperatorGuard from '../useOperatorGuard';

type ProfileOnboardingConfig = {
  enabled?: boolean;
  markdownflow?: string;
  document_prompt?: string;
  config_revision?: number;
  allowed_variable_keys?: string[];
  version?: number;
  updated_by?: string;
  updated_at?: string;
};

export default function ProfileOnboardingAdminPage() {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const { isReady } = useOperatorGuard();
  const [enabled, setEnabled] = React.useState(false);
  const [markdownflow, setMarkdownflow] = React.useState('');
  const [documentPrompt, setDocumentPrompt] = React.useState('');
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
  const defaultDocumentPrompt = t(
    'module.profileOnboarding.admin.defaultDocumentPrompt',
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
        setDocumentPrompt(
          hasStoredConfiguration
            ? (response.document_prompt ?? defaultDocumentPrompt)
            : response.document_prompt || defaultDocumentPrompt,
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
  }, [defaultDocumentPrompt, defaultMarkdownflow, isReady, t]);

  const handleSave = React.useCallback(async () => {
    if (enabled && !markdownflow.trim()) {
      setError(t('module.profileOnboarding.admin.documentRequired'));
      return;
    }
    setSaving(true);
    setError('');
    try {
      const response = (await api.updateAdminOperationProfileOnboardingConfig({
        enabled,
        markdownflow,
        document_prompt: documentPrompt,
      })) as ProfileOnboardingConfig;
      setEnabled(Boolean(response.enabled));
      setMarkdownflow(response.markdownflow ?? markdownflow);
      setDocumentPrompt(response.document_prompt ?? documentPrompt);
      setConfigRevision(
        Number(response.config_revision ?? response.version ?? configRevision),
      );
      setUpdatedBy(response.updated_by || updatedBy);
      setUpdatedAt(response.updated_at || updatedAt);
      toast({
        title: t('module.profileOnboarding.admin.saveSuccess'),
      });
    } catch (caughtError) {
      const typedError = caughtError as Partial<ErrorWithCode>;
      setError(
        typedError.message || t('module.profileOnboarding.admin.saveFailed'),
      );
    } finally {
      setSaving(false);
    }
  }, [
    configRevision,
    documentPrompt,
    enabled,
    markdownflow,
    t,
    toast,
    updatedAt,
    updatedBy,
  ]);

  const createPreviewSession = React.useCallback(async () => {
    setPreviewDraft('');
    setError('');
    return (await api.createAdminOperationProfileOnboardingPreview({
      markdownflow,
      document_prompt: documentPrompt,
      language: i18n.resolvedLanguage ?? i18n.language,
    })) as ProfileOnboardingSessionInfo;
  }, [documentPrompt, i18n.language, i18n.resolvedLanguage, markdownflow]);

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

  if (!isReady || loading) {
    return <Loading />;
  }

  return (
    <>
      <AdminBreadcrumb
        items={[
          {
            label: t('common.core.operations'),
            href: '/admin/operations',
          },
          {
            label: t('module.profileOnboarding.admin.title'),
          },
        ]}
      />
      <AdminTitle
        title={t('module.profileOnboarding.admin.title')}
        description={t('module.profileOnboarding.admin.description')}
        actions={
          <div className='flex gap-2'>
            <Button
              type='button'
              variant='outline'
              onClick={() => {
                setPreviewDraft('');
                setPreviewOpen(true);
                setPreviewKey(key => key + 1);
              }}
            >
              {previewOpen
                ? t('module.profileOnboarding.admin.restartPreview')
                : t('module.profileOnboarding.admin.preview')}
            </Button>
            <Button
              type='button'
              disabled={saving}
              onClick={handleSave}
            >
              {t('module.profileOnboarding.admin.save')}
            </Button>
          </div>
        }
      />

      <div className='grid min-h-0 flex-1 gap-6 xl:grid-cols-[minmax(0,1fr)_400px]'>
        <section className='min-h-0 space-y-5'>
          <div className='flex items-center justify-between rounded-md border bg-background px-4 py-3'>
            <div className='space-y-1'>
              <Label htmlFor='profile-onboarding-enabled'>
                {t('module.profileOnboarding.admin.enabled')}
              </Label>
              <p className='text-sm text-muted-foreground'>
                {t('module.profileOnboarding.admin.enabledHint')}
              </p>
            </div>
            <Switch
              id='profile-onboarding-enabled'
              checked={enabled}
              aria-label={t('module.profileOnboarding.admin.enabled')}
              onCheckedChange={setEnabled}
            />
          </div>

          <div className='space-y-2'>
            <Label htmlFor='profile-onboarding-document-prompt'>
              {t('module.profileOnboarding.admin.documentPrompt')}
            </Label>
            <p className='text-sm text-muted-foreground'>
              {t('module.profileOnboarding.admin.documentPromptHint')}
            </p>
            <Textarea
              id='profile-onboarding-document-prompt'
              value={documentPrompt}
              minRows={4}
              maxRows={8}
              onChange={event => setDocumentPrompt(event.target.value)}
            />
          </div>

          <div className='space-y-2'>
            <Label htmlFor='profile-onboarding-markdownflow'>
              {t('module.profileOnboarding.admin.markdownflow')}
            </Label>
            <p className='text-sm text-muted-foreground'>
              {t('module.profileOnboarding.admin.markdownflowHint')}
            </p>
            <Textarea
              id='profile-onboarding-markdownflow'
              value={markdownflow}
              className='min-h-[360px] font-mono text-sm'
              maxRows={24}
              onChange={event => setMarkdownflow(event.target.value)}
            />
          </div>

          <div className='rounded-md border bg-muted/30 p-4 text-sm leading-6'>
            <div className='font-medium'>
              {t('module.profileOnboarding.admin.lockedSummaryTitle')}
            </div>
            <p className='mt-1 text-muted-foreground'>
              {t('module.profileOnboarding.admin.lockedSummaryHint')}
            </p>
          </div>

          {error ? (
            <div
              role='alert'
              className='rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive'
            >
              {error}
            </div>
          ) : null}
        </section>

        <aside className='space-y-5'>
          <section className='rounded-md border bg-background p-4'>
            <h2 className='text-sm font-semibold'>
              {t('module.profileOnboarding.admin.publishState')}
            </h2>
            <dl className='mt-3 space-y-2 text-sm'>
              <div className='flex justify-between gap-3'>
                <dt className='text-muted-foreground'>
                  {t('module.profileOnboarding.admin.configRevision')}
                </dt>
                <dd>{configRevision || '-'}</dd>
              </div>
              <div className='flex justify-between gap-3'>
                <dt className='text-muted-foreground'>
                  {t('module.profileOnboarding.admin.updatedBy')}
                </dt>
                <dd className='truncate'>{updatedBy || '-'}</dd>
              </div>
              <div className='flex justify-between gap-3'>
                <dt className='text-muted-foreground'>
                  {t('module.profileOnboarding.admin.updatedAt')}
                </dt>
                <dd className='truncate'>{updatedAt || '-'}</dd>
              </div>
            </dl>
          </section>

          {previewOpen ? (
            <section className='rounded-md border bg-background p-4'>
              <div className='flex items-center justify-between gap-3'>
                <h2 className='text-sm font-semibold'>
                  {t('module.profileOnboarding.admin.preview')}
                </h2>
                <Button
                  type='button'
                  variant='ghost'
                  size='sm'
                  onClick={() => setPreviewOpen(false)}
                >
                  {t('module.profileOnboarding.admin.hidePreview')}
                </Button>
              </div>
              <p className='mt-2 text-xs leading-5 text-muted-foreground'>
                {t('module.profileOnboarding.admin.previewProfileNotice')}
              </p>
              <div className='mt-4'>
                <ProfileOnboardingConversation
                  key={previewKey}
                  createSession={createPreviewSession}
                  runSession={runPreviewSession}
                  onDraftReady={draft => setPreviewDraft(draft)}
                  onRetry={() => setError('')}
                  onError={caughtError => {
                    setError(
                      caughtError instanceof Error && caughtError.message
                        ? caughtError.message
                        : t('module.profileOnboarding.admin.previewFailed'),
                    );
                  }}
                />
              </div>
              {previewDraft ? (
                <div className='mt-4 space-y-2'>
                  <Label htmlFor='profile-onboarding-preview-draft'>
                    {t('module.profileOnboarding.admin.previewDraft')}
                  </Label>
                  <Textarea
                    id='profile-onboarding-preview-draft'
                    value={previewDraft}
                    minRows={6}
                    maxRows={10}
                    readOnly
                  />
                </div>
              ) : null}
            </section>
          ) : null}
        </aside>
      </div>
    </>
  );
}
