'use client';

import React from 'react';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Label } from '@/components/ui/Label';
import { Switch } from '@/components/ui/Switch';
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import { useTranslation } from 'react-i18next';
import useOperatorGuard from '../useOperatorGuard';
import {
  PROFILE_ONBOARDING_ALLOWED_VARIABLE_KEYS,
  getInvalidProfileOnboardingVariableKeys,
  parseProfileOnboardingFlow,
} from '@/components/profile-onboarding/profileOnboardingFlow';

type ProfileOnboardingConfig = {
  enabled?: boolean;
  markdownflow?: string;
  allowed_variable_keys?: string[];
  version?: number;
  updated_by?: string;
  updated_at?: string;
};

export default function ProfileOnboardingAdminPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { isReady } = useOperatorGuard();
  const [enabled, setEnabled] = React.useState(false);
  const [markdownflow, setMarkdownflow] = React.useState('');
  const [allowedKeys, setAllowedKeys] = React.useState<string[]>(
    Array.from(PROFILE_ONBOARDING_ALLOWED_VARIABLE_KEYS),
  );
  const [version, setVersion] = React.useState(0);
  const [updatedBy, setUpdatedBy] = React.useState('');
  const [updatedAt, setUpdatedAt] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState('');
  const [previewOpen, setPreviewOpen] = React.useState(false);
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
        setEnabled(Boolean(response.enabled));
        setMarkdownflow(response.markdownflow || defaultMarkdownflow);
        setAllowedKeys(
          response.allowed_variable_keys?.length
            ? response.allowed_variable_keys
            : Array.from(PROFILE_ONBOARDING_ALLOWED_VARIABLE_KEYS),
        );
        setVersion(Number(response.version || 0));
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

  const previewSteps = React.useMemo(
    () => parseProfileOnboardingFlow(markdownflow),
    [markdownflow],
  );

  const validateBeforeSave = React.useCallback(() => {
    const invalidKeys = getInvalidProfileOnboardingVariableKeys(
      markdownflow,
      allowedKeys,
    );
    if (invalidKeys.length > 0) {
      return t('module.profileOnboarding.admin.invalidVariables', {
        keys: invalidKeys.join(', '),
      });
    }
    return '';
  }, [allowedKeys, markdownflow, t]);

  const handleSave = React.useCallback(async () => {
    const validationError = validateBeforeSave();
    if (validationError) {
      setError(validationError);
      return;
    }

    setSaving(true);
    setError('');
    try {
      const response = (await api.updateAdminOperationProfileOnboardingConfig({
        enabled,
        markdownflow,
      })) as ProfileOnboardingConfig;
      setEnabled(Boolean(response.enabled));
      setMarkdownflow(response.markdownflow || markdownflow);
      setAllowedKeys(
        response.allowed_variable_keys?.length
          ? response.allowed_variable_keys
          : allowedKeys,
      );
      setVersion(Number(response.version || version));
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
    allowedKeys,
    enabled,
    markdownflow,
    t,
    toast,
    updatedAt,
    updatedBy,
    validateBeforeSave,
    version,
  ]);

  if (!isReady || loading) {
    return <Loading />;
  }

  return (
    <div className='flex min-h-0 flex-1 flex-col px-8 py-6'>
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
              onClick={() => setPreviewOpen(open => !open)}
            >
              {previewOpen
                ? t('module.profileOnboarding.admin.hidePreview')
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

      <div className='grid min-h-0 flex-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]'>
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
            <Label htmlFor='profile-onboarding-markdownflow'>
              {t('module.profileOnboarding.admin.markdownflow')}
            </Label>
            <Textarea
              id='profile-onboarding-markdownflow'
              value={markdownflow}
              className='min-h-[360px] font-mono text-sm'
              maxRows={24}
              onChange={event => setMarkdownflow(event.target.value)}
            />
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
              {t('module.profileOnboarding.admin.allowedVariables')}
            </h2>
            <p className='mt-1 text-sm text-muted-foreground'>
              {t('module.profileOnboarding.admin.allowedVariablesHint')}
            </p>
            <div className='mt-3 flex flex-wrap gap-2'>
              {allowedKeys.map(key => (
                <Badge
                  key={key}
                  variant='outline'
                >
                  {key}
                </Badge>
              ))}
            </div>
          </section>

          <section className='rounded-md border bg-background p-4'>
            <h2 className='text-sm font-semibold'>
              {t('module.profileOnboarding.admin.publishState')}
            </h2>
            <dl className='mt-3 space-y-2 text-sm'>
              <div className='flex justify-between gap-3'>
                <dt className='text-muted-foreground'>
                  {t('module.profileOnboarding.admin.version')}
                </dt>
                <dd>{version || '-'}</dd>
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
              <h2 className='text-sm font-semibold'>
                {t('module.profileOnboarding.admin.preview')}
              </h2>
              <div className='mt-3 space-y-3'>
                {previewSteps.length > 0 ? (
                  previewSteps.map(step => (
                    <div
                      key={step.id}
                      className='rounded-md border px-3 py-2 text-sm'
                    >
                      {step.intro ? (
                        <p className='mb-2 whitespace-pre-wrap text-muted-foreground'>
                          {step.intro}
                        </p>
                      ) : null}
                      <div className='font-medium'>
                        {step.prompt || step.variableKey}
                      </div>
                      {step.options.length > 0 ? (
                        <div className='mt-2 flex flex-wrap gap-2'>
                          {step.options.map(option => (
                            <Badge
                              key={option.value}
                              variant='secondary'
                            >
                              {option.label}
                            </Badge>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <div className='text-sm text-muted-foreground'>
                    {t('module.profileOnboarding.admin.emptyPreview')}
                  </div>
                )}
              </div>
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
