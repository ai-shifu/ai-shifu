import React from 'react';
import { CircleHelp, Loader2, Sparkles } from 'lucide-react';
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
  onNicknameChange: (value: string) => void;
  onProfileChange: (value: string) => void;
  onUndoOptimization: () => void;
  onOptimize: () => void;
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
  onNicknameChange,
  onProfileChange,
  onUndoOptimization,
  onOptimize,
}: LearnerProfileSaveViewProps) {
  const { t } = useTranslation();

  return (
    <div className='space-y-5 sm:space-y-4'>
      <h2
        ref={headingRef}
        tabIndex={-1}
        className='text-xl font-semibold leading-7 outline-none'
      >
        {t('module.profileOnboarding.dialog.confirmTitle')}
      </h2>

      {manualFallback ? (
        <div className='rounded-xl border border-primary/20 bg-primary/[0.05] px-4 py-3 text-sm leading-6 text-foreground/80'>
          {t('module.profileOnboarding.dialog.manualFallback')}
        </div>
      ) : null}

      <div className='space-y-1.5 sm:grid sm:grid-cols-[minmax(0,180px)_1fr] sm:items-center sm:gap-3 sm:space-y-0'>
        <label
          htmlFor='learner-profile-dialog-nickname'
          className='text-sm font-semibold text-foreground'
        >
          {t('module.profileOnboarding.dialog.nicknameLabel')}
        </label>
        <div className='space-y-1'>
          <Input
            id='learner-profile-dialog-nickname'
            className='h-10 rounded-lg shadow-none'
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

      <section className='space-y-3'>
        <label
          htmlFor='learner-profile-dialog-draft'
          className='text-sm font-medium'
        >
          {t('module.profileOnboarding.dialog.profileLabel')}
        </label>

        <ProfileDraftEditor
          inputId='learner-profile-dialog-draft'
          textareaRef={textareaRef}
          textareaClassName='h-[clamp(7rem,18dvh,12rem)] min-h-[clamp(7rem,18dvh,12rem)] max-h-[clamp(7rem,18dvh,12rem)] resize-none overflow-y-auto rounded-xl border-border px-4 py-3 leading-6 shadow-none'
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
          className='rounded-xl border border-primary/20 bg-primary/[0.05] px-4 py-3'
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
                  className='min-h-10 flex-1 sm:flex-none'
                  onClick={onUndoOptimization}
                >
                  {t('module.profileOnboarding.dialog.undoOptimize')}
                </Button>
              ) : null}
              <Button
                type='button'
                size='sm'
                className='min-h-10 flex-1 px-4 shadow-sm sm:flex-none'
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
      <div className='min-h-40 flex-1 [@media(max-height:620px)]:min-h-32'>
        <ProfileOnboardingConversation
          key={conversationKey}
          {...conversationProps}
        />
      </div>
      {collectionReady ? (
        <div
          role='status'
          className='mt-3 rounded-xl border border-primary/20 bg-primary/[0.05] px-4 py-3 text-sm leading-6 text-foreground/80'
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
      className='mx-auto flex h-full min-h-64 max-w-lg flex-col justify-center'
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
    </section>
  );
}

export function ProfileInformationUsageControl() {
  const { t } = useTranslation();

  return (
    <details
      data-testid='learner-profile-information-usage'
      className='group relative min-w-0 max-sm:w-full'
    >
      <summary
        className={cn(
          buttonVariants({ variant: 'ghost' }),
          'min-h-10 min-w-0 list-none justify-start px-2 text-left text-sm font-normal text-muted-foreground !whitespace-normal hover:text-foreground max-sm:w-full [&::-webkit-details-marker]:hidden',
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
        className='absolute bottom-[calc(100%+0.5rem)] left-0 z-[110] w-[min(22rem,calc(100vw-2rem))] rounded-xl border bg-popover p-4 text-popover-foreground shadow-md'
      >
        <p className='font-medium leading-6'>
          {t('module.profileOnboarding.dialog.informationUsageTitle')}
        </p>
        <ul className='mt-2 list-disc space-y-1.5 pl-5 text-sm leading-5 text-muted-foreground'>
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
