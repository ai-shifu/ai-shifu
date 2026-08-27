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
    collectionRunInFlight,
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
  const headerRef = React.useRef<HTMLElement | null>(null);
  const footerRef = React.useRef<HTMLElement | null>(null);
  const collectionContinueButtonRef = React.useRef<HTMLButtonElement | null>(
    null,
  );
  const [chromeHeights, setChromeHeights] = React.useState<{
    header: number | null;
    footer: number | null;
  }>({ header: null, footer: null });
  const collectionOwnsScroll = loaded && !confirmation && phase === 'collect';

  const keepFocusedControlVisible = React.useCallback(
    (event: React.FocusEvent<HTMLDivElement>) => {
      const target = event.target;
      if (
        !(target instanceof HTMLElement) ||
        !target.matches('input, textarea, select, [contenteditable="true"]')
      ) {
        return;
      }

      const scrollTargetIntoView = () => {
        if (!target.isConnected) return;
        target.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
      };
      if (typeof window.requestAnimationFrame === 'function') {
        window.requestAnimationFrame(scrollTargetIntoView);
      } else {
        scrollTargetIntoView();
      }
    },
    [],
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

  React.useLayoutEffect(() => {
    const updateChromeHeights = () => {
      const header = headerRef.current?.getBoundingClientRect().height ?? 0;
      const footer = footerRef.current?.getBoundingClientRect().height ?? 0;
      if (header > 0 || footer > 0) {
        setChromeHeights(current => {
          const next = { header: header || null, footer: footer || null };
          return current.header === next.header &&
            current.footer === next.footer
            ? current
            : next;
        });
      }
    };

    updateChromeHeights();
    if (typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver(updateChromeHeights);
    if (headerRef.current) observer.observe(headerRef.current);
    if (footerRef.current) observer.observe(footerRef.current);
    return () => observer.disconnect();
  }, [confirmation, loaded, phase]);

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
        data-testid='learner-profile-dialog-content'
        data-phase={phase}
        showClose={false}
        overlayClassName='!bg-slate-950/45 backdrop-blur-[1px]'
        onFocusCapture={keepFocusedControlVisible}
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
        className='inset-0 flex h-dvh max-h-none w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-none border-0 p-0 shadow-none outline-none focus:outline-none focus-visible:outline-none focus-within:outline-none focus-within:ring-0 focus-within:ring-offset-0 motion-reduce:animate-none motion-reduce:duration-0 max-sm:[&_button]:min-h-11 max-sm:[&_button]:min-w-11 max-sm:[&_input]:min-h-11 max-sm:[&_input]:text-base max-sm:[&_select]:min-h-11 max-sm:[&_select]:text-base max-sm:[&_textarea]:text-base sm:inset-auto sm:left-1/2 sm:top-1/2 sm:h-[min(88dvh,760px)] sm:w-[calc(100vw-48px)] sm:max-w-[900px] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border sm:shadow-lg sm:any-pointer-coarse:[&_button]:min-h-11 sm:any-pointer-coarse:[&_button]:min-w-11 sm:any-pointer-coarse:[&_input]:min-h-11 sm:any-pointer-coarse:[&_input]:text-base sm:any-pointer-coarse:[&_select]:min-h-11 sm:any-pointer-coarse:[&_select]:text-base sm:any-pointer-coarse:[&_textarea]:text-base'
      >
        <header
          ref={headerRef}
          className='absolute inset-x-0 top-0 z-10 border-b bg-background/55 pb-3 pl-[max(1rem,env(safe-area-inset-left,0px))] pr-[max(1rem,env(safe-area-inset-right,0px))] pt-[max(0.75rem,env(safe-area-inset-top,0px))] shadow-[0_10px_30px_-22px_rgba(15,23,42,0.4)] backdrop-blur-sm sm:px-8 sm:pb-5 sm:pt-6 [@media(max-height:620px)]:pb-2 [@media(max-height:620px)]:pt-[max(0.75rem,env(safe-area-inset-top,0px))]'
        >
          <DialogHeader className='w-full space-y-1 pr-12 text-start sm:space-y-2 [@media(max-height:620px)]:space-y-1'>
            <DialogTitle className='text-xl font-bold leading-7 tracking-tight sm:text-[28px] sm:leading-9 [@media(max-height:620px)]:text-xl [@media(max-height:620px)]:leading-7'>
              {t('module.profileOnboarding.dialog.unifiedTitle')}
            </DialogTitle>
            <DialogDescription className='max-w-2xl text-start text-sm leading-5 sm:text-base sm:leading-6 [@media(max-height:620px)]:text-sm [@media(max-height:620px)]:leading-5'>
              {t('module.profileOnboarding.dialog.unifiedDescription')}
            </DialogDescription>
          </DialogHeader>
          {exitPolicy === 'dismissible' ? (
            <Button
              type='button'
              size='icon'
              variant='ghost'
              className='absolute right-[max(0.75rem,env(safe-area-inset-right,0px))] top-[max(0.75rem,env(safe-area-inset-top,0px))] size-11 rounded-full sm:right-4 sm:top-4'
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
          className={cn(
            'relative z-0 flex min-h-0 flex-1 flex-col overscroll-contain bg-muted/25 pb-[calc(var(--learner-profile-footer-height,80px)+1rem)] pl-[max(1rem,env(safe-area-inset-left,0px))] pr-[max(1rem,env(safe-area-inset-right,0px))] pt-[calc(var(--learner-profile-header-height,96px)+1rem)] [scrollbar-gutter:stable] sm:px-8 sm:pb-[calc(var(--learner-profile-footer-height,76px)+1.5rem)] sm:pt-[calc(var(--learner-profile-header-height,116px)+1.5rem)] [@media(max-height:620px)]:pb-[calc(var(--learner-profile-footer-height,80px)+0.5rem)] [@media(max-height:620px)]:pt-[calc(var(--learner-profile-header-height,80px)+0.5rem)]',
            collectionOwnsScroll ? 'overflow-hidden' : 'overflow-y-auto',
          )}
          style={
            {
              '--learner-profile-header-height': chromeHeights.header
                ? `${chromeHeights.header}px`
                : undefined,
              '--learner-profile-footer-height': chromeHeights.footer
                ? `${chromeHeights.footer}px`
                : undefined,
            } as React.CSSProperties
          }
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
              guidedAvailable={guidedAvailable}
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
              onRequestCollection={requestCollection}
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
          ref={footerRef}
          className='absolute inset-x-0 bottom-0 z-10 flex flex-nowrap items-center gap-2 border-t bg-background/55 pb-[max(0.75rem,env(safe-area-inset-bottom,0px))] pl-[max(1rem,env(safe-area-inset-left,0px))] pr-[max(1rem,env(safe-area-inset-right,0px))] pt-3 shadow-[0_-10px_30px_-22px_rgba(15,23,42,0.4)] backdrop-blur-sm sm:flex-wrap sm:justify-end sm:gap-3 sm:px-8 sm:py-4 [@media(max-height:620px)]:flex-nowrap [@media(max-height:620px)]:pb-[max(0.75rem,env(safe-area-inset-bottom,0px))] [@media(max-height:620px)]:pt-3'
        >
          {confirmation ? (
            <>
              <div className='hidden min-w-0 items-center justify-start sm:me-auto sm:flex sm:w-auto [@media(max-height:620px)]:hidden'>
                <ProfileInformationUsageControl variant='popover' />
              </div>
              <div
                data-testid='learner-profile-dialog-confirmation-actions'
                className='ms-auto flex w-full min-w-0 items-center justify-end gap-2 sm:w-auto sm:gap-3'
              >
                <Button
                  type='button'
                  variant='outline'
                  className='h-auto min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                  onClick={() => setConfirmation(null)}
                >
                  {t('module.profileOnboarding.dialog.keepEditing')}
                </Button>
                <Button
                  type='button'
                  className={cn(
                    'h-auto min-h-11 min-w-0 flex-[1.4] !whitespace-normal sm:flex-none',
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
                className='me-auto flex min-w-0 flex-wrap items-center justify-start gap-2 sm:w-auto sm:gap-3'
              >
                <ProfileInformationUsageControl
                  variant='popover'
                  className='hidden sm:block [@media(max-height:620px)]:hidden'
                />
                {guidedAvailable ? (
                  <Button
                    data-testid='learner-profile-interactive-collection-desktop'
                    type='button'
                    variant='outline'
                    className='hidden min-h-11 min-w-0 !whitespace-normal sm:inline-flex [@media(max-height:620px)]:hidden'
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
                    className='h-auto min-h-11 px-3 text-muted-foreground !whitespace-normal'
                    disabled={
                      !onDefer ||
                      saving ||
                      deferring ||
                      collectionRunInFlight ||
                      externalSubmitting
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
                className='ms-auto flex min-w-0 flex-1 items-center justify-end gap-2 sm:w-auto sm:flex-none sm:gap-3'
              >
                {exitPolicy === 'dismissible' ? (
                  <Button
                    type='button'
                    variant='outline'
                    className='h-auto min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                    disabled={busy}
                    onClick={requestClose}
                  >
                    {t('module.profileOnboarding.dialog.cancel')}
                  </Button>
                ) : null}
                <Button
                  type='button'
                  className='h-auto min-h-11 min-w-0 flex-[1.4] !whitespace-normal sm:flex-none'
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
                className='me-auto flex min-w-0 flex-wrap items-center justify-start gap-2 sm:w-auto sm:gap-3'
              >
                <ProfileInformationUsageControl
                  variant='popover'
                  className='hidden sm:block [@media(max-height:620px)]:hidden'
                />
                {exitPolicy === 'blocking' ? (
                  <Button
                    type='button'
                    variant='ghost'
                    className='h-auto min-h-11 px-3 text-muted-foreground !whitespace-normal'
                    disabled={
                      !onDefer ||
                      saving ||
                      deferring ||
                      collectionRunInFlight ||
                      externalSubmitting
                    }
                    onClick={() => void deferOnboarding()}
                  >
                    {deferring || externalSubmitting
                      ? t('module.profileOnboarding.skipping')
                      : t('module.profileOnboarding.skip')}
                  </Button>
                ) : null}
                {exitPolicy === 'dismissible' && collectionReady ? (
                  <Button
                    type='button'
                    variant='outline'
                    className='h-auto min-h-11 min-w-0 flex-1 !whitespace-normal sm:hidden [@media(max-height:620px)]:inline-flex'
                    disabled={busy}
                    onClick={cancelCollection}
                  >
                    {t('module.profileOnboarding.dialog.cancelResearch')}
                  </Button>
                ) : null}
              </div>
              {collectionReady ? (
                <Button
                  ref={collectionContinueButtonRef}
                  type='button'
                  className='ms-auto h-auto min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                  disabled={busy}
                  onClick={continueToSave}
                >
                  {t('module.profileOnboarding.guided.reviewCollection')}
                </Button>
              ) : exitPolicy === 'dismissible' ? (
                <Button
                  type='button'
                  variant='outline'
                  className='ms-auto h-auto min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
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
