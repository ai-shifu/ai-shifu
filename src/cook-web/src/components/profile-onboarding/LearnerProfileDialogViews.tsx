import React from 'react';
import {
  CircleHelp,
  Loader2,
  MessageCircleQuestion,
  Sparkles,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button, buttonVariants } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';
import { ProfileDraftEditor } from './ProfileDraftEditor';
import ProfileOnboardingConversation, {
  type ProfileOnboardingConversationProps,
} from './ProfileOnboardingConversation';

export type DialogConfirmation = 'discard' | 'replace-collection';
export type OptimizationStatus = 'idle' | 'running' | 'success' | 'error';

type LearnerProfileSaveViewProps = {
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  manualFallback: boolean;
  nickname: string;
  profile: string;
  loaded: boolean;
  busy: boolean;
  optimizing: boolean;
  nicknameOverLimit: boolean;
  nicknameLength: number;
  nicknameMaxLength: number;
  maxLength: number;
  optimizationStatus: OptimizationStatus;
  optimizationDescription: string;
  optimizationOriginal: string | null;
  optimizeDisabled: boolean;
  guidedAvailable: boolean;
  onNicknameChange: (value: string) => void;
  onProfileChange: (value: string) => void;
  onUndoOptimization: () => void;
  onOptimize: () => void;
  onRequestCollection: () => void;
};

export function LearnerProfileSaveView({
  headingRef,
  textareaRef,
  manualFallback,
  nickname,
  profile,
  loaded,
  busy,
  optimizing,
  nicknameOverLimit,
  nicknameLength,
  nicknameMaxLength,
  maxLength,
  optimizationStatus,
  optimizationDescription,
  optimizationOriginal,
  optimizeDisabled,
  guidedAvailable,
  onNicknameChange,
  onProfileChange,
  onUndoOptimization,
  onOptimize,
  onRequestCollection,
}: LearnerProfileSaveViewProps) {
  const { t } = useTranslation();

  return (
    <div
      data-testid='learner-profile-save-view'
      className='flex min-h-full flex-1 flex-col gap-5 sm:gap-4'
    >
      <div
        data-testid='learner-profile-save-heading-row'
        className='flex shrink-0 items-center justify-between gap-2 sm:block [@media(max-height:620px)]:flex'
      >
        <h2
          ref={headingRef}
          tabIndex={-1}
          className='min-w-0 text-xl font-semibold leading-7 outline-none'
        >
          {t('module.profileOnboarding.dialog.confirmTitle')}
        </h2>
        {guidedAvailable ? (
          <Button
            data-testid='learner-profile-interactive-collection-mobile'
            type='button'
            variant='ghost'
            className='ms-auto h-auto min-h-11 w-fit max-w-[48%] shrink-0 justify-start px-2 py-2 text-start text-sm leading-5 text-muted-foreground !whitespace-normal hover:bg-accent/60 hover:text-foreground sm:hidden [@media(max-height:620px)]:inline-flex'
            disabled={busy || optimizing}
            onClick={onRequestCollection}
          >
            <MessageCircleQuestion
              className='shrink-0 text-primary'
              aria-hidden='true'
            />
            <span className='min-w-0'>
              {t('module.profileOnboarding.dialog.interactiveCollection')}
            </span>
          </Button>
        ) : null}
      </div>

      {manualFallback ? (
        <div className='shrink-0 rounded-xl border border-primary/20 bg-primary/[0.05] px-4 py-3 text-sm leading-6 text-foreground/80'>
          {t('module.profileOnboarding.dialog.manualFallback')}
        </div>
      ) : null}

      <div className='shrink-0 space-y-1.5 sm:grid sm:grid-cols-[minmax(0,180px)_1fr] sm:items-center sm:gap-3 sm:space-y-0'>
        <label
          htmlFor='learner-profile-dialog-nickname'
          className='text-sm font-semibold text-foreground'
        >
          {t('module.profileOnboarding.dialog.nicknameLabel')}
        </label>
        <div className='space-y-1'>
          <Input
            id='learner-profile-dialog-nickname'
            className='h-11 rounded-lg text-base shadow-none sm:h-10 sm:text-sm'
            value={nickname}
            disabled={!loaded || busy}
            aria-invalid={nicknameOverLimit || undefined}
            aria-describedby={
              nicknameOverLimit
                ? 'learner-profile-dialog-nickname-error'
                : undefined
            }
            placeholder={t(
              'module.profileOnboarding.dialog.nicknamePlaceholder',
            )}
            onChange={event => onNicknameChange(event.target.value)}
          />
          {nicknameOverLimit ? (
            <p
              id='learner-profile-dialog-nickname-error'
              role='alert'
              className='text-xs leading-5 text-destructive'
            >
              {t('module.profileOnboarding.characterCountOverLimit', {
                count: nicknameLength,
                max: nicknameMaxLength,
              })}
            </p>
          ) : null}
        </div>
      </div>

      <section className='flex min-h-60 flex-1 flex-col gap-3 sm:min-h-52 [@media(max-height:620px)]:min-h-52 [@media(max-height:620px)]:flex-none'>
        <label
          htmlFor='learner-profile-dialog-draft'
          className='text-sm font-medium'
        >
          {t('module.profileOnboarding.dialog.profileLabel')}
        </label>

        <ProfileDraftEditor
          inputId='learner-profile-dialog-draft'
          textareaRef={textareaRef}
          className='min-h-48 flex-1 sm:min-h-40 [@media(max-height:620px)]:min-h-40'
          textareaClassName='min-h-40 flex-1 resize-none overflow-y-auto rounded-xl border-border px-4 py-3 text-base leading-6 shadow-none sm:min-h-32 sm:text-sm [@media(max-height:620px)]:min-h-32'
          minRows={4}
          autoResize={false}
          value={profile}
          maxLength={maxLength}
          disabled={!loaded || busy || optimizing}
          placeholder={t('module.profileOnboarding.profilePlaceholder')}
          descriptionId='learner-profile-optimization-status'
          onChange={onProfileChange}
        />

        <div
          data-testid='learner-profile-optimization-card'
          className='shrink-0 rounded-xl border border-primary/20 bg-primary/[0.05] px-4 py-3'
          aria-live='polite'
        >
          <div className='flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between'>
            <p
              id='learner-profile-optimization-status'
              className={cn(
                'min-w-0 flex-1 text-sm leading-5 text-foreground/80',
                optimizationStatus === 'error' && 'text-destructive',
              )}
            >
              {optimizationDescription}
            </p>
            <div className='flex flex-wrap gap-2'>
              {optimizationStatus === 'success' &&
              optimizationOriginal !== null ? (
                <Button
                  type='button'
                  size='sm'
                  variant='outline'
                  className='min-h-11 flex-1 sm:min-h-10 sm:flex-none'
                  onClick={onUndoOptimization}
                >
                  {t('module.profileOnboarding.dialog.undoOptimize')}
                </Button>
              ) : null}
              <Button
                type='button'
                size='sm'
                className='min-h-11 flex-1 px-4 shadow-sm sm:min-h-10 sm:flex-none'
                disabled={optimizeDisabled}
                aria-describedby='learner-profile-optimization-status'
                onClick={onOptimize}
              >
                {optimizing ? (
                  <Loader2
                    className='size-4 animate-spin motion-reduce:animate-none'
                    aria-hidden='true'
                  />
                ) : (
                  <Sparkles
                    className='size-4'
                    aria-hidden='true'
                  />
                )}
                {t(
                  optimizing
                    ? 'module.profileOnboarding.dialog.optimizing'
                    : 'module.profileOnboarding.dialog.optimize',
                )}
              </Button>
            </div>
          </div>
        </div>
      </section>

      <ProfileInformationUsageControl
        variant='inline'
        className='sm:hidden [@media(max-height:620px)]:block'
      />
    </div>
  );
}

type ProfileCollectionViewProps = ProfileOnboardingConversationProps & {
  conversationKey: number;
  collectionReady: boolean;
};

export function ProfileCollectionView({
  conversationKey,
  collectionReady,
  ...conversationProps
}: ProfileCollectionViewProps) {
  const { t } = useTranslation();

  return (
    <section className='flex min-h-0 flex-1 flex-col'>
      <div className='min-h-0 flex-1'>
        <ProfileOnboardingConversation
          key={conversationKey}
          {...conversationProps}
          questionScrollFooter={
            <ProfileInformationUsageControl
              variant='inline'
              className='mt-4 sm:hidden [@media(max-height:620px)]:block'
            />
          }
        />
      </div>
      {collectionReady ? (
        <div
          role='status'
          className='mt-3 shrink-0 rounded-xl border border-primary/20 bg-primary/[0.05] px-4 py-3 text-sm leading-6 text-foreground/80'
        >
          {t('module.profileOnboarding.guided.collectionComplete')}
        </div>
      ) : null}
    </section>
  );
}

export function ProfileDialogConfirmationView({
  confirmation,
  headingRef,
}: {
  confirmation: DialogConfirmation;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  const { t } = useTranslation();

  return (
    <section
      data-testid={`learner-profile-confirmation-${confirmation}`}
      className='mx-auto flex h-full min-h-64 max-w-lg flex-col justify-start sm:justify-center [@media(max-height:620px)]:justify-start'
    >
      <h2
        ref={headingRef}
        tabIndex={-1}
        className='text-xl font-semibold leading-7 outline-none'
      >
        {t(
          confirmation === 'discard'
            ? 'module.profileOnboarding.dialog.discardTitle'
            : 'module.profileOnboarding.dialog.replaceResearchTitle',
        )}
      </h2>
      <p className='mt-3 text-sm leading-6 text-muted-foreground'>
        {t(
          confirmation === 'discard'
            ? 'module.profileOnboarding.dialog.discardDescription'
            : 'module.profileOnboarding.dialog.replaceResearchDescription',
        )}
      </p>
      <ProfileInformationUsageControl
        variant='inline'
        className='mt-6 sm:hidden [@media(max-height:620px)]:block'
      />
    </section>
  );
}

export function ProfileInformationUsageControl({
  variant = 'popover',
  className,
}: {
  variant?: 'inline' | 'popover';
  className?: string;
}) {
  const { t } = useTranslation();
  const inline = variant === 'inline';

  return (
    <details
      data-testid={`learner-profile-information-usage-${variant}`}
      className={cn(
        'group min-w-0',
        inline
          ? 'rounded-xl border border-border/80 bg-background/80'
          : 'relative',
        className,
      )}
    >
      <summary
        className={cn(
          buttonVariants({ variant: 'ghost' }),
          'h-auto min-h-11 min-w-0 list-none justify-start px-2 text-start text-sm font-normal text-muted-foreground !whitespace-normal hover:text-foreground [&::-webkit-details-marker]:hidden',
          inline && 'w-full rounded-xl px-3 py-2.5',
        )}
      >
        <span className='flex min-w-0 items-center gap-2'>
          <CircleHelp
            className='size-4 shrink-0'
            aria-hidden='true'
          />
          {t('module.profileOnboarding.dialog.informationUsageTitle')}
        </span>
      </summary>
      <div
        role='note'
        className={cn(
          'text-popover-foreground',
          inline
            ? 'border-t border-border/70 px-4 pb-4 pt-3'
            : 'absolute bottom-[calc(100%+0.5rem)] start-0 z-[110] w-[min(22rem,calc(100vw-2rem))] rounded-xl border bg-popover p-4 shadow-md',
        )}
      >
        <p className='font-medium leading-6'>
          {t('module.profileOnboarding.dialog.informationUsageTitle')}
        </p>
        <ul className='mt-2 list-disc space-y-1.5 ps-5 text-sm leading-5 text-muted-foreground'>
          <li>
            {t('module.profileOnboarding.dialog.informationUsagePurpose')}
          </li>
          <li>
            {t('module.profileOnboarding.dialog.informationUsageSensitive')}
          </li>
          <li>
            {t('module.profileOnboarding.dialog.informationUsageEditable')}
          </li>
        </ul>
      </div>
    </details>
  );
}
