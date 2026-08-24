'use client';

import React from 'react';
import { Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { cn } from '@/lib/utils';
import {
  LearnerProfileSaveView,
  ProfileCollectionView,
  ProfileDialogConfirmationView,
  ProfileInformationUsageControl,
} from './LearnerProfileDialogViews';
import type { LearnerProfileDialogProps } from './learnerProfileDialogModel';
import { useLearnerProfileDialogController } from './useLearnerProfileDialogController';

export type {
  LearnerProfileDialogProps,
  ProfileCollectionResult,
} from './learnerProfileDialogModel';

export default function LearnerProfileDialog(props: LearnerProfileDialogProps) {
  const { open, exitPolicy, externalSubmitting = false, onDefer } = props;
  const { t } = useTranslation();
  const {
    state,
    derived,
    textareaRef,
    collectionReady,
    confirmation,
    optimizeDisabled,
    optimizationDescription,
    combinedDialogError,
    primaryLabel,
    conversationProps,
    setProfile,
    setNickname,
    setError,
    setConfirmation,
    resetOptimization,
    retryLoad,
    saveProfile,
    requestClose,
    optimizeProfile,
    undoOptimization,
    requestCollection,
    continueToSave,
    cancelCollection,
    deferOnboarding,
    confirmPendingAction,
  } = useLearnerProfileDialogController(props);
  const {
    phase,
    collectionKey,
    guidedAvailable,
    manualFallback,
    optimizationStatus,
    optimizationOriginal,
    form: { profile, nickname, maxLength, nicknameMaxLength },
  } = state;
  const {
    loaded,
    loading,
    optimizing,
    saving,
    dismissing,
    deferring,
    busy,
    nicknameLength,
    nicknameOverLimit,
    canSave,
  } = derived;
  const viewHeadingRef = React.useRef<HTMLHeadingElement | null>(null);
  const confirmationHeadingRef = React.useRef<HTMLHeadingElement | null>(null);
  const contentScrollRef = React.useRef<HTMLDivElement | null>(null);
  const collectionContinueButtonRef = React.useRef<HTMLButtonElement | null>(
    null,
  );

  React.useEffect(() => {
    contentScrollRef.current?.scrollTo?.({ top: 0, behavior: 'auto' });
    if (contentScrollRef.current) {
      contentScrollRef.current.scrollTop = 0;
    }
    if (confirmation) {
      confirmationHeadingRef.current?.focus();
    } else {
      viewHeadingRef.current?.focus();
    }
  }, [confirmation, loaded, phase]);

  React.useEffect(() => {
    if (phase === 'collect' && collectionReady) {
      collectionContinueButtonRef.current?.focus();
    }
  }, [collectionReady, phase]);

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        if (!nextOpen) {
          requestClose();
        }
      }}
    >
      <DialogContent
        data-phase={phase}
        showClose={false}
        overlayClassName='!bg-slate-950/45 backdrop-blur-[1px]'
        onEscapeKeyDown={event => {
          if (exitPolicy === 'blocking') {
            event.preventDefault();
          }
        }}
        onPointerDownOutside={event => {
          if (exitPolicy === 'blocking') {
            event.preventDefault();
          }
        }}
        className='bottom-3 left-3 top-3 flex h-auto max-h-none w-[calc(100vw-24px)] max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-2xl p-0 outline-none focus:outline-none focus-visible:outline-none focus-within:outline-none focus-within:ring-0 focus-within:ring-offset-0 motion-reduce:animate-none motion-reduce:duration-0 sm:bottom-auto sm:left-1/2 sm:top-1/2 sm:h-[min(88dvh,760px)] sm:w-[calc(100vw-48px)] sm:max-w-[900px] sm:-translate-x-1/2 sm:-translate-y-1/2'
      >
        <div
          data-testid='learner-profile-mobile-handle'
          className='mx-auto mt-3 h-1 w-10 shrink-0 rounded-full bg-muted-foreground/35 [@media(max-height:620px)]:hidden sm:hidden'
          aria-hidden='true'
        />

        <header className='relative shrink-0 border-b bg-background px-5 pb-4 pt-5 [@media(max-height:620px)]:py-3 sm:px-8 sm:pb-5 sm:pt-6'>
          <DialogHeader className='w-full space-y-2 pr-12 text-left [@media(max-height:620px)]:space-y-1'>
            <DialogTitle className='text-2xl font-bold leading-8 tracking-tight [@media(max-height:620px)]:text-xl [@media(max-height:620px)]:leading-7 sm:text-[28px] sm:leading-9'>
              {t('module.profileOnboarding.dialog.unifiedTitle')}
            </DialogTitle>
            <DialogDescription className='max-w-2xl text-left text-sm leading-6 [@media(max-height:620px)]:text-xs [@media(max-height:620px)]:leading-5 sm:text-base'>
              {t('module.profileOnboarding.dialog.unifiedDescription')}
            </DialogDescription>
          </DialogHeader>
          {exitPolicy === 'dismissible' ? (
            <Button
              type='button'
              size='icon'
              variant='ghost'
              className='absolute right-3 top-3 size-11 rounded-full sm:right-4 sm:top-4'
              disabled={saving || dismissing || deferring}
              aria-label={t('module.profileOnboarding.dialog.close')}
              onClick={requestClose}
            >
              <X aria-hidden='true' />
            </Button>
          ) : null}
        </header>

        <div
          ref={contentScrollRef}
          data-testid='learner-profile-dialog-body'
          className='flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain px-5 py-5 [scrollbar-gutter:stable] [@media(max-height:620px)]:py-3 sm:px-8 sm:py-6'
        >
          {loading ? (
            <div
              role='status'
              className='flex h-full min-h-40 items-center justify-center gap-2 text-sm text-muted-foreground'
            >
              <Loader2
                className='size-4 animate-spin motion-reduce:animate-none'
                aria-hidden='true'
              />
              {t('module.profileOnboarding.dialog.loading')}
            </div>
          ) : !loaded ? (
            <div className='mx-auto max-w-lg space-y-3'>
              {state.error ? (
                <div
                  role='alert'
                  className='rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'
                >
                  <p>{state.error}</p>
                  <Button
                    type='button'
                    variant='outline'
                    className='mt-3 min-h-11 border-destructive/30 bg-background text-foreground'
                    disabled={loading || busy}
                    onClick={retryLoad}
                  >
                    {t('module.profileOnboarding.dialog.retry')}
                  </Button>
                </div>
              ) : null}
            </div>
          ) : confirmation ? (
            <ProfileDialogConfirmationView
              confirmation={confirmation}
              headingRef={confirmationHeadingRef}
            />
          ) : phase === 'collect' ? (
            <ProfileCollectionView
              conversationKey={collectionKey}
              collectionReady={collectionReady}
              {...conversationProps}
            />
          ) : (
            <LearnerProfileSaveView
              headingRef={viewHeadingRef}
              textareaRef={textareaRef}
              manualFallback={manualFallback}
              nickname={nickname}
              profile={profile}
              loaded={loaded}
              busy={busy}
              optimizing={optimizing}
              nicknameOverLimit={nicknameOverLimit}
              nicknameLength={nicknameLength}
              nicknameMaxLength={nicknameMaxLength}
              maxLength={maxLength}
              optimizationStatus={optimizationStatus}
              optimizationDescription={optimizationDescription}
              optimizationOriginal={optimizationOriginal}
              optimizeDisabled={optimizeDisabled}
              onNicknameChange={value => {
                setNickname(value);
                setError('');
              }}
              onProfileChange={value => {
                setProfile(value);
                resetOptimization();
                setError('');
              }}
              onUndoOptimization={undoOptimization}
              onOptimize={optimizeProfile}
            />
          )}

          {loaded && combinedDialogError ? (
            <div
              role='alert'
              className='mt-5 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'
            >
              {combinedDialogError}
            </div>
          ) : null}
        </div>

        <footer
          data-testid='learner-profile-dialog-footer'
          className='flex shrink-0 flex-wrap items-center gap-2.5 border-t bg-background px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 sm:justify-end sm:gap-3 sm:px-8 sm:py-4'
        >
          {confirmation ? (
            <>
              <div className='mr-auto flex w-full min-w-0 items-center justify-start sm:w-auto'>
                <ProfileInformationUsageControl />
              </div>
              <div className='ml-auto flex w-full min-w-0 items-center justify-end gap-2.5 sm:w-auto sm:gap-3'>
                <Button
                  type='button'
                  variant='outline'
                  className='min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                  onClick={() => setConfirmation(null)}
                >
                  {t('module.profileOnboarding.dialog.keepEditing')}
                </Button>
                <Button
                  type='button'
                  className={cn(
                    'min-h-11 min-w-0 flex-[1.4] !whitespace-normal sm:flex-none',
                    confirmation === 'discard' &&
                      'bg-destructive text-destructive-foreground hover:bg-destructive/90',
                  )}
                  onClick={confirmPendingAction}
                >
                  {t(
                    confirmation === 'discard'
                      ? 'module.profileOnboarding.dialog.discard'
                      : 'module.profileOnboarding.dialog.replaceResearchConfirm',
                  )}
                </Button>
              </div>
            </>
          ) : phase === 'save' ? (
            <>
              <div
                data-testid='learner-profile-dialog-left-actions'
                className='mr-auto flex w-full min-w-0 flex-wrap items-center justify-start gap-2.5 sm:w-auto sm:gap-3'
              >
                <ProfileInformationUsageControl />
                {guidedAvailable ? (
                  <Button
                    type='button'
                    variant='outline'
                    className='min-h-11 min-w-0 !whitespace-normal'
                    disabled={busy || optimizing}
                    onClick={requestCollection}
                  >
                    {t('module.profileOnboarding.dialog.interactiveCollection')}
                  </Button>
                ) : null}
                {exitPolicy === 'blocking' ? (
                  <Button
                    type='button'
                    variant='ghost'
                    className='min-h-11 px-3 text-muted-foreground !whitespace-normal'
                    disabled={
                      !onDefer || saving || deferring || externalSubmitting
                    }
                    onClick={() => void deferOnboarding()}
                  >
                    {deferring || externalSubmitting
                      ? t('module.profileOnboarding.skipping')
                      : t('module.profileOnboarding.skip')}
                  </Button>
                ) : null}
              </div>
              <div
                data-testid='learner-profile-dialog-save-actions'
                className='ml-auto flex w-full min-w-0 items-center justify-end gap-2.5 sm:w-auto sm:gap-3'
              >
                {exitPolicy === 'dismissible' ? (
                  <Button
                    type='button'
                    variant='outline'
                    className='min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                    disabled={busy}
                    onClick={requestClose}
                  >
                    {t('module.profileOnboarding.dialog.cancel')}
                  </Button>
                ) : null}
                <Button
                  type='button'
                  className='min-h-11 min-w-0 flex-[1.4] !whitespace-normal sm:flex-none'
                  disabled={!canSave}
                  onClick={() => void saveProfile()}
                >
                  {saving
                    ? t('module.profileOnboarding.dialog.saving')
                    : primaryLabel}
                </Button>
              </div>
            </>
          ) : (
            <>
              <div
                data-testid='learner-profile-dialog-left-actions'
                className='mr-auto flex w-full min-w-0 flex-wrap items-center justify-start gap-2.5 sm:w-auto sm:gap-3'
              >
                <ProfileInformationUsageControl />
                {exitPolicy === 'blocking' ? (
                  <Button
                    type='button'
                    variant='ghost'
                    className='min-h-11 px-3 text-muted-foreground !whitespace-normal'
                    disabled={
                      !onDefer || saving || deferring || externalSubmitting
                    }
                    onClick={() => void deferOnboarding()}
                  >
                    {deferring || externalSubmitting
                      ? t('module.profileOnboarding.skipping')
                      : t('module.profileOnboarding.skip')}
                  </Button>
                ) : null}
              </div>
              {collectionReady ? (
                <Button
                  ref={collectionContinueButtonRef}
                  type='button'
                  className='ml-auto min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                  disabled={busy}
                  onClick={continueToSave}
                >
                  {t('module.profileOnboarding.guided.reviewCollection')}
                </Button>
              ) : exitPolicy === 'dismissible' ? (
                <Button
                  type='button'
                  variant='outline'
                  className='ml-auto min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                  disabled={busy}
                  onClick={cancelCollection}
                >
                  {t('module.profileOnboarding.dialog.cancelResearch')}
                </Button>
              ) : null}
            </>
          )}
        </footer>
      </DialogContent>
    </Dialog>
  );
}
