'use client';

import React from 'react';
import {
  BriefcaseBusiness,
  Info,
  MoreHorizontal,
  Target,
  UserRound,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  clearLearnerProfile,
  getLearnerProfile,
  updateLearnerProfile,
} from '@/api/learnerProfile';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { useToast } from '@/hooks/useToast';
import { notifyLearnerProfileChanged } from '@/lib/learnerProfileEvents';
import {
  ProfileDraftEditor,
  countUnicodeCodePoints,
} from './ProfileDraftEditor';

const DEFAULT_MAX_LENGTH = 1000;

const PROFILE_PROMPTS = [
  { key: 'identity', Icon: UserRound },
  { key: 'goals', Icon: BriefcaseBusiness },
  { key: 'teaching', Icon: Target },
] as const;

type LearnerProfileDialogProps = {
  open: boolean;
  mode: 'onboarding' | 'settings';
  draftStorageScope: string;
  onClose: (reason: 'dismiss' | 'saved') => void | Promise<void>;
  onSaved?: () => void | Promise<void>;
};

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error && error.message ? error.message : fallback;

export default function LearnerProfileDialog({
  open,
  mode,
  draftStorageScope,
  onClose,
  onSaved,
}: LearnerProfileDialogProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [profile, setProfile] = React.useState('');
  const [savedProfile, setSavedProfile] = React.useState('');
  const [maxLength, setMaxLength] = React.useState(DEFAULT_MAX_LENGTH);
  const [loading, setLoading] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [clearing, setClearing] = React.useState(false);
  const [dismissing, setDismissing] = React.useState(false);
  const [error, setError] = React.useState('');
  const [clearError, setClearError] = React.useState('');
  const [clearOpen, setClearOpen] = React.useState(false);
  const [discardOpen, setDiscardOpen] = React.useState(false);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const translationRef = React.useRef(t);
  const mountedRef = React.useRef(false);
  const openRef = React.useRef(open);
  const scopeRef = React.useRef(draftStorageScope);
  const generationRef = React.useRef(0);
  const loadRequestRef = React.useRef(0);

  openRef.current = open;
  scopeRef.current = draftStorageScope;
  translationRef.current = t;

  const isCurrent = React.useCallback(
    (generation: number, scope: string) =>
      mountedRef.current &&
      openRef.current &&
      generationRef.current === generation &&
      scopeRef.current === scope,
    [],
  );

  const loadProfile = React.useCallback(
    async (generation: number, scope: string) => {
      const request = ++loadRequestRef.current;
      setLoading(true);
      setLoaded(false);
      setError('');
      try {
        const response = await getLearnerProfile();
        if (
          !isCurrent(generation, scope) ||
          request !== loadRequestRef.current
        ) {
          return;
        }
        const nextProfile = response.learner_profile || '';
        setProfile(nextProfile);
        setSavedProfile(nextProfile);
        setMaxLength(response.max_length || DEFAULT_MAX_LENGTH);
        setLoaded(true);
      } catch (caughtError) {
        if (
          isCurrent(generation, scope) &&
          request === loadRequestRef.current
        ) {
          setError(
            errorMessage(
              caughtError,
              translationRef.current(
                'module.profileOnboarding.dialog.loadFailed',
              ),
            ),
          );
        }
      } finally {
        if (
          isCurrent(generation, scope) &&
          request === loadRequestRef.current
        ) {
          setLoading(false);
        }
      }
    },
    [isCurrent],
  );

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      loadRequestRef.current += 1;
    };
  }, []);

  React.useEffect(() => {
    const generation = ++generationRef.current;
    loadRequestRef.current += 1;
    setClearOpen(false);
    setDiscardOpen(false);
    setClearError('');
    setError('');

    if (!open) {
      return;
    }

    const scope = draftStorageScope;
    setProfile('');
    setSavedProfile('');
    setMaxLength(DEFAULT_MAX_LENGTH);
    setLoaded(false);
    setSaving(false);
    setClearing(false);
    setDismissing(false);
    void loadProfile(generation, scope);

    return () => {
      if (generationRef.current === generation) {
        generationRef.current += 1;
      }
      loadRequestRef.current += 1;
    };
  }, [draftStorageScope, loadProfile, open]);

  const runOnSaved = React.useCallback(
    async (generation: number, scope: string) => {
      try {
        await onSaved?.();
      } catch {
        if (isCurrent(generation, scope)) {
          toast({ title: t('module.profileOnboarding.refreshPending') });
        }
      }
    },
    [isCurrent, onSaved, t, toast],
  );

  const saveProfile = React.useCallback(async () => {
    if (!loaded || saving || clearing) {
      return;
    }

    const normalized = profile.trim();
    if (!normalized) {
      setError(t('module.profileOnboarding.dialog.emptyProfile'));
      textareaRef.current?.focus();
      return;
    }
    if (countUnicodeCodePoints(normalized) > maxLength) {
      textareaRef.current?.focus();
      return;
    }

    const generation = generationRef.current;
    const scope = draftStorageScope;
    setSaving(true);
    setError('');
    try {
      const response = await updateLearnerProfile(normalized);
      if (!isCurrent(generation, scope)) {
        return;
      }
      setProfile(response.learner_profile);
      setSavedProfile(response.learner_profile);
      setMaxLength(response.max_length || maxLength);
      notifyLearnerProfileChanged();
      toast({ title: t('module.profileOnboarding.dialog.saveSuccess') });
      await runOnSaved(generation, scope);
      if (isCurrent(generation, scope)) {
        await onClose('saved');
      }
    } catch (caughtError) {
      if (isCurrent(generation, scope)) {
        setError(
          errorMessage(
            caughtError,
            t('module.profileOnboarding.dialog.saveFailed'),
          ),
        );
      }
    } finally {
      if (isCurrent(generation, scope)) {
        setSaving(false);
      }
    }
  }, [
    clearing,
    draftStorageScope,
    isCurrent,
    loaded,
    maxLength,
    onClose,
    profile,
    runOnSaved,
    saving,
    t,
    toast,
  ]);

  const clearProfile = React.useCallback(async () => {
    if (saving || clearing) {
      return;
    }

    const generation = generationRef.current;
    const scope = draftStorageScope;
    setClearing(true);
    setClearError('');
    try {
      const response = await clearLearnerProfile();
      if (!isCurrent(generation, scope)) {
        return;
      }
      setProfile('');
      setSavedProfile('');
      setMaxLength(response.max_length || maxLength);
      setClearOpen(false);
      notifyLearnerProfileChanged();
      toast({ title: t('module.profileOnboarding.dialog.clearSuccess') });
      await runOnSaved(generation, scope);
    } catch (caughtError) {
      if (isCurrent(generation, scope)) {
        setClearError(
          errorMessage(
            caughtError,
            t('module.profileOnboarding.dialog.clearFailed'),
          ),
        );
      }
    } finally {
      if (isCurrent(generation, scope)) {
        setClearing(false);
      }
    }
  }, [
    clearing,
    draftStorageScope,
    isCurrent,
    maxLength,
    runOnSaved,
    saving,
    t,
    toast,
  ]);

  const dirty = loaded && profile.trim() !== savedProfile;
  const busy = saving || clearing || dismissing;
  const profileLength = countUnicodeCodePoints(profile.trim());
  const canSave =
    loaded &&
    !busy &&
    Boolean(profile.trim()) &&
    profileLength <= maxLength &&
    profile.trim() !== savedProfile;

  const dismiss = React.useCallback(async () => {
    if (busy) {
      return;
    }
    const generation = generationRef.current;
    const scope = draftStorageScope;
    setDismissing(true);
    setError('');
    try {
      await onClose('dismiss');
    } catch (caughtError) {
      if (isCurrent(generation, scope)) {
        setError(
          errorMessage(
            caughtError,
            t('module.profileOnboarding.dialog.dismissFailed'),
          ),
        );
      }
    } finally {
      if (isCurrent(generation, scope)) {
        setDismissing(false);
      }
    }
  }, [busy, draftStorageScope, isCurrent, onClose, t]);

  const requestClose = React.useCallback(() => {
    if (busy) {
      return;
    }
    if (dirty) {
      setDiscardOpen(true);
      return;
    }
    void dismiss();
  }, [busy, dirty, dismiss]);

  const insertPrompt = React.useCallback(
    (prompt: (typeof PROFILE_PROMPTS)[number]['key']) => {
      const insertion = t(
        `module.profileOnboarding.dialog.chips.${prompt}.text`,
      );
      setProfile(current =>
        current.trim() ? `${current.trimEnd()}\n${insertion}` : insertion,
      );
      setError('');
      textareaRef.current?.focus();
    },
    [t],
  );

  const retryLoad = React.useCallback(() => {
    const generation = generationRef.current;
    void loadProfile(generation, draftStorageScope);
  }, [draftStorageScope, loadProfile]);

  const secondaryLabel =
    mode === 'onboarding'
      ? t('module.profileOnboarding.dialog.later')
      : t('module.profileOnboarding.dialog.cancel');
  const primaryLabel =
    mode === 'onboarding'
      ? t('module.profileOnboarding.dialog.saveAndContinue')
      : t('module.profileOnboarding.dialog.saveChanges');

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={nextOpen => {
          if (!nextOpen) {
            requestClose();
          }
        }}
      >
        <DialogContent
          showClose={false}
          overlayClassName='!bg-slate-950/45 backdrop-blur-[1px]'
          className='bottom-0 left-3 top-auto flex h-[calc(100dvh-96px)] w-[calc(100vw-24px)] max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-t-3xl border-b-0 p-0 sm:bottom-auto sm:left-1/2 sm:top-1/2 sm:h-auto sm:max-h-[min(90dvh,800px)] sm:w-[calc(100vw-48px)] sm:max-w-[680px] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border'
        >
          <div
            data-testid='learner-profile-mobile-handle'
            className='mx-auto mt-3 h-1 w-10 shrink-0 rounded-full bg-muted-foreground/35 sm:hidden'
            aria-hidden='true'
          />

          <div className='sticky top-0 z-10 bg-background px-5 pb-4 pt-5 sm:px-8 sm:pb-5 sm:pt-8'>
            <DialogHeader className='mx-auto max-w-[560px] space-y-3 text-center'>
              <DialogTitle className='text-2xl font-bold leading-8 tracking-tight sm:text-[28px] sm:leading-9'>
                {t(
                  mode === 'onboarding'
                    ? 'module.profileOnboarding.dialog.onboardingTitle'
                    : 'module.profileOnboarding.dialog.settingsTitle',
                )}
              </DialogTitle>
              <DialogDescription className='text-left text-sm leading-6 sm:text-center sm:text-base'>
                {t('module.profileOnboarding.dialog.description')}
              </DialogDescription>
            </DialogHeader>
            <Button
              type='button'
              size='icon'
              variant='ghost'
              className='absolute right-4 top-4 hidden size-11 rounded-full sm:inline-flex'
              disabled={busy}
              aria-label={t('module.profileOnboarding.dialog.close')}
              onClick={requestClose}
            >
              <X aria-hidden='true' />
            </Button>
          </div>

          <div className='min-h-0 flex-1 overflow-y-auto px-5 pb-5 sm:px-8 sm:pb-7'>
            <div className='space-y-5'>
              <div className='flex flex-wrap justify-center gap-2 sm:gap-3'>
                {PROFILE_PROMPTS.map(({ key, Icon }) => (
                  <Button
                    key={key}
                    type='button'
                    variant='outline'
                    className='h-auto min-h-11 rounded-full border-primary/10 bg-primary/[0.06] px-4 py-2 text-left text-primary whitespace-normal hover:bg-primary/10 hover:text-primary'
                    disabled={!loaded || busy}
                    onClick={() => insertPrompt(key)}
                  >
                    <Icon aria-hidden='true' />
                    {t(`module.profileOnboarding.dialog.chips.${key}.label`)}
                  </Button>
                ))}
              </div>

              <ProfileDraftEditor
                inputId='learner-profile-dialog-draft'
                textareaRef={textareaRef}
                textareaClassName='min-h-[215px] resize-none rounded-xl border-border px-4 py-3 leading-6 shadow-none focus-visible:ring-primary/30 sm:min-h-[185px]'
                value={profile}
                maxLength={maxLength}
                disabled={!loaded || busy}
                label={t('module.profileOnboarding.dialog.profileLabel')}
                placeholder={t(
                  'module.profileOnboarding.dialog.profilePlaceholder',
                )}
                onChange={value => {
                  setProfile(value);
                  setError('');
                }}
              />

              {loading ? (
                <div
                  role='status'
                  className='rounded-lg bg-muted px-4 py-3 text-sm text-muted-foreground'
                >
                  {t('module.profileOnboarding.dialog.loading')}
                </div>
              ) : null}

              {error ? (
                <div
                  role='alert'
                  className='rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'
                >
                  <p>{error}</p>
                  {!loaded ? (
                    <Button
                      type='button'
                      variant='outline'
                      className='mt-3 min-h-11 border-destructive/30 bg-background text-foreground'
                      disabled={loading || busy}
                      onClick={retryLoad}
                    >
                      {t('module.profileOnboarding.dialog.retry')}
                    </Button>
                  ) : null}
                </div>
              ) : null}

              <section
                data-testid='learner-profile-writing-guide'
                className='rounded-xl bg-primary/[0.07] px-4 py-4 text-sm leading-6 sm:px-5'
              >
                <h3 className='font-semibold text-primary'>
                  {t('module.profileOnboarding.dialog.writingGuideTitle')}
                </h3>
                <ul className='mt-1.5 list-disc space-y-0.5 pl-5 text-foreground/80'>
                  <li>
                    {t('module.profileOnboarding.dialog.writingGuideIdentity')}
                  </li>
                  <li>
                    {t('module.profileOnboarding.dialog.writingGuideGoals')}
                  </li>
                  <li>
                    {t('module.profileOnboarding.dialog.writingGuideTeaching')}
                  </li>
                </ul>
              </section>

              <div
                data-testid='learner-profile-reassurance'
                className='flex items-start gap-2 rounded-lg border bg-muted/40 px-3 py-2.5 text-sm leading-5 text-muted-foreground'
              >
                <Info
                  className='mt-0.5 size-4 shrink-0 text-primary'
                  aria-hidden='true'
                />
                <span>{t('module.profileOnboarding.dialog.reassurance')}</span>
              </div>
            </div>
          </div>

          <div className='sticky bottom-0 z-10 flex items-center gap-2.5 border-t bg-background px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 sm:gap-3 sm:px-8 sm:py-5'>
            <Button
              type='button'
              variant='outline'
              className='min-h-11 min-w-0 flex-1 sm:min-w-40 sm:flex-none'
              disabled={busy}
              onClick={requestClose}
            >
              {secondaryLabel}
            </Button>
            <Button
              type='button'
              className='min-h-11 min-w-0 flex-[1.4] sm:min-w-72 sm:flex-none'
              disabled={!canSave}
              onClick={() => {
                void saveProfile();
              }}
            >
              {saving
                ? t('module.profileOnboarding.dialog.saving')
                : primaryLabel}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type='button'
                  size='icon'
                  variant='ghost'
                  className='size-11 shrink-0 rounded-full'
                  disabled={busy}
                  aria-label={t('module.profileOnboarding.dialog.moreActions')}
                >
                  <MoreHorizontal aria-hidden='true' />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align='end'>
                <DropdownMenuItem
                  disabled={!loaded || !savedProfile || busy}
                  className='min-h-11 text-destructive focus:text-destructive'
                  onSelect={() => {
                    setClearError('');
                    setClearOpen(true);
                  }}
                >
                  {t('module.profileOnboarding.dialog.clear')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={clearOpen}
        onOpenChange={nextOpen => {
          if (!clearing) {
            setClearOpen(nextOpen);
            if (!nextOpen) {
              setClearError('');
            }
          }
        }}
      >
        <AlertDialogContent className='w-[calc(100vw-32px)] rounded-xl'>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('module.profileOnboarding.dialog.clearTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('module.profileOnboarding.dialog.clearDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {clearError ? (
            <div
              role='alert'
              className='rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'
            >
              {clearError}
            </div>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel
              className='min-h-11'
              disabled={clearing}
            >
              {t('module.profileOnboarding.dialog.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              className='min-h-11 bg-destructive text-destructive-foreground hover:bg-destructive/90'
              disabled={clearing}
              onClick={event => {
                event.preventDefault();
                void clearProfile();
              }}
            >
              {clearing
                ? t('module.profileOnboarding.dialog.clearing')
                : t('module.profileOnboarding.dialog.confirmClear')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={discardOpen}
        onOpenChange={setDiscardOpen}
      >
        <AlertDialogContent className='w-[calc(100vw-32px)] rounded-xl'>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('module.profileOnboarding.dialog.discardTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('module.profileOnboarding.dialog.discardDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className='min-h-11'>
              {t('module.profileOnboarding.dialog.keepEditing')}
            </AlertDialogCancel>
            <AlertDialogAction
              className='min-h-11 bg-destructive text-destructive-foreground hover:bg-destructive/90'
              onClick={() => {
                setDiscardOpen(false);
                void dismiss();
              }}
            >
              {t('module.profileOnboarding.dialog.discard')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
