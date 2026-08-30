'use client';

import { useTranslation } from 'react-i18next';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import Loading from '@/components/loading';
import ProfileOnboardingConversation from '@/components/profile-onboarding/ProfileOnboardingConversation';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
import { Button } from '@/components/ui/Button';
import { Label } from '@/components/ui/Label';
import { Switch } from '@/components/ui/Switch';
import { Textarea } from '@/components/ui/Textarea';
import useOperatorGuard from '../useOperatorGuard';
import { useProfileOnboardingAdminController } from './useProfileOnboardingAdminController';

export default function ProfileOnboardingAdminPage() {
  const { t } = useTranslation();
  const { isReady } = useOperatorGuard();
  const {
    enabled,
    setEnabled,
    markdownflow,
    setMarkdownflow,
    assistantPrompt,
    setAssistantPrompt,
    configRevision,
    updatedBy,
    updatedAt,
    loading,
    configLoaded,
    loadFailed,
    reload,
    saving,
    navigating,
    generating,
    error,
    generationNotice,
    documentChanged,
    pendingNavigation,
    navigationRetryPending,
    navigationStatus,
    dismissPendingNavigation,
    discardPendingChanges,
    retryPendingNavigation,
    saveAndProceed,
    previewOpen,
    previewKey,
    previewDraft,
    generateAssistantPrompt,
    save,
    startPreview,
    hidePreview,
    previewConversationProps,
  } = useProfileOnboardingAdminController(isReady);

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
              disabled={!configLoaded || saving || navigating || generating}
              onClick={startPreview}
            >
              {previewOpen
                ? t('module.profileOnboarding.admin.restartPreview')
                : t('module.profileOnboarding.admin.preview')}
            </Button>
            <Button
              type='button'
              disabled={!configLoaded || saving || navigating || generating}
              onClick={() => void save()}
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
              disabled={!configLoaded}
              aria-label={t('module.profileOnboarding.admin.enabled')}
              onCheckedChange={setEnabled}
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
              className='min-h-[360px] font-mono text-sm focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2'
              maxRows={24}
              disabled={!configLoaded}
              onChange={event => setMarkdownflow(event.target.value)}
            />
            <div className='flex flex-wrap items-center justify-between gap-3 pt-1'>
              <Button
                type='button'
                variant='outline'
                disabled={!configLoaded || saving || generating}
                onClick={() => void generateAssistantPrompt()}
              >
                {generating
                  ? t(
                      'module.profileOnboarding.admin.generatingAssistantPrompt',
                    )
                  : assistantPrompt.trim()
                    ? t(
                        'module.profileOnboarding.admin.regenerateAssistantPrompt',
                      )
                    : t(
                        'module.profileOnboarding.admin.generateAssistantPrompt',
                      )}
              </Button>
              {generationNotice ? (
                <p
                  role='status'
                  aria-live='polite'
                  className='text-sm text-muted-foreground'
                >
                  {generationNotice}
                </p>
              ) : null}
            </div>
            {documentChanged ? (
              <p
                role='status'
                className='rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950'
              >
                {t('module.profileOnboarding.admin.documentChanged')}
              </p>
            ) : null}
          </div>

          <div className='space-y-2'>
            <Label htmlFor='profile-onboarding-assistant-prompt'>
              {t('module.profileOnboarding.admin.assistantPrompt')}
            </Label>
            <p className='text-sm text-muted-foreground'>
              {t('module.profileOnboarding.admin.assistantPromptHint')}
            </p>
            <Textarea
              id='profile-onboarding-assistant-prompt'
              value={assistantPrompt}
              placeholder={t(
                'module.profileOnboarding.admin.assistantPromptEmpty',
              )}
              className='focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2'
              minRows={4}
              maxRows={12}
              disabled={!configLoaded}
              onChange={event => setAssistantPrompt(event.target.value)}
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
              <div className='flex flex-wrap items-center justify-between gap-3'>
                <span>{error}</span>
                {loadFailed ? (
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    onClick={reload}
                  >
                    {t('module.profileOnboarding.admin.reload')}
                  </Button>
                ) : null}
              </div>
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
                  onClick={hidePreview}
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
                  {...previewConversationProps}
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

      <AlertDialog
        open={Boolean(pendingNavigation)}
        onOpenChange={open => {
          if (!open) {
            dismissPendingNavigation();
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t(
                navigationRetryPending
                  ? 'module.profileOnboarding.admin.unsavedDialog.retryTitle'
                  : 'module.profileOnboarding.admin.unsavedDialog.title',
              )}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t(
                navigationRetryPending
                  ? 'module.profileOnboarding.admin.unsavedDialog.retryDescription'
                  : 'module.profileOnboarding.admin.unsavedDialog.description',
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {error ? (
            <div
              role='alert'
              className='rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive'
            >
              {error}
            </div>
          ) : null}
          {navigationStatus ? (
            <div
              role='status'
              aria-live='polite'
              className='rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950'
            >
              {navigationStatus}
            </div>
          ) : null}
          <AlertDialogFooter className='gap-2 sm:space-x-0'>
            <AlertDialogCancel disabled={saving || navigating}>
              {t(
                navigationRetryPending
                  ? 'module.profileOnboarding.admin.unsavedDialog.stay'
                  : 'module.profileOnboarding.admin.unsavedDialog.cancel',
              )}
            </AlertDialogCancel>
            {navigationRetryPending ? (
              <AlertDialogAction
                type='button'
                disabled={navigating}
                onClick={event => {
                  event.preventDefault();
                  retryPendingNavigation();
                }}
              >
                {t('module.profileOnboarding.admin.unsavedDialog.retry')}
              </AlertDialogAction>
            ) : (
              <>
                <AlertDialogAction
                  type='button'
                  disabled={saving || navigating}
                  className='border border-input bg-white text-muted-foreground shadow-sm hover:bg-muted hover:text-foreground'
                  onClick={event => {
                    event.preventDefault();
                    discardPendingChanges();
                  }}
                >
                  {t('module.profileOnboarding.admin.unsavedDialog.discard')}
                </AlertDialogAction>
                <AlertDialogAction
                  type='button'
                  disabled={saving || navigating || generating}
                  onClick={event => {
                    event.preventDefault();
                    void saveAndProceed();
                  }}
                >
                  {t('module.profileOnboarding.admin.unsavedDialog.save')}
                </AlertDialogAction>
              </>
            )}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
