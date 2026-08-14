'use client';

import React from 'react';
import {
  BriefcaseBusiness,
  Info,
  Loader2,
  Sparkles,
  Target,
  UserRound,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  getLearnerProfile,
  LEARNER_PROFILE_OPTIMIZATION_REJECTED_CODE,
  optimizeLearnerProfile,
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
import { Input } from '@/components/ui/Input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { useToast } from '@/hooks/useToast';
import { notifyLearnerProfileChanged } from '@/lib/learnerProfileEvents';
import {
  ProfileDraftEditor,
  countUnicodeCodePoints,
} from './ProfileDraftEditor';
import {
  buildLearnerProfileDraft,
  resolveLearnerNicknameDraft,
  type LearnerNicknameSource,
} from './learnerProfileDraft';

const DEFAULT_MAX_LENGTH = 1000;
const DEFAULT_NICKNAME_MAX_LENGTH = 64;

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

type OptimizationStatus =
  | 'idle'
  | 'success'
  | 'unchanged'
  | 'rejected'
  | 'error';

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
  const [initialProfile, setInitialProfile] = React.useState('');
  const [savedProfile, setSavedProfile] = React.useState('');
  const [nickname, setNickname] = React.useState('');
  const [initialNickname, setInitialNickname] = React.useState('');
  const [savedNickname, setSavedNickname] = React.useState<string | undefined>(
    undefined,
  );
  const [nicknameSource, setNicknameSource] =
    React.useState<LearnerNicknameSource>('unavailable');
  const [maxLength, setMaxLength] = React.useState(DEFAULT_MAX_LENGTH);
  const [nicknameMaxLength, setNicknameMaxLength] = React.useState(
    DEFAULT_NICKNAME_MAX_LENGTH,
  );
  const [loading, setLoading] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [dismissing, setDismissing] = React.useState(false);
  const [error, setError] = React.useState('');
  const [optimizing, setOptimizing] = React.useState(false);
  const [optimizationStatus, setOptimizationStatus] =
    React.useState<OptimizationStatus>('idle');
  const [optimizationOriginal, setOptimizationOriginal] = React.useState<
    string | null
  >(null);
  const [discardOpen, setDiscardOpen] = React.useState(false);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const translationRef = React.useRef(t);
  const mountedRef = React.useRef(false);
  const openRef = React.useRef(open);
  const scopeRef = React.useRef(draftStorageScope);
  const generationRef = React.useRef(0);
  const loadRequestRef = React.useRef(0);
  const optimizeRequestRef = React.useRef(0);

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

  const resetOptimization = React.useCallback(() => {
    setOptimizationStatus('idle');
    setOptimizationOriginal(null);
  }, []);

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
        const nextProfile = buildLearnerProfileDraft(
          response,
          translationRef.current,
        );
        setProfile(nextProfile);
        setInitialProfile(nextProfile);
        setSavedProfile(response.learner_profile || '');
        const nicknameDraft = resolveLearnerNicknameDraft(response);
        setNickname(nicknameDraft.value);
        setInitialNickname(nicknameDraft.value);
        setSavedNickname(nicknameDraft.savedValue);
        setNicknameSource(nicknameDraft.source);
        setMaxLength(response.max_length || DEFAULT_MAX_LENGTH);
        setNicknameMaxLength(
          response.nickname_max_length || DEFAULT_NICKNAME_MAX_LENGTH,
        );
        resetOptimization();
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
    [isCurrent, resetOptimization],
  );

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      loadRequestRef.current += 1;
      optimizeRequestRef.current += 1;
    };
  }, []);

  React.useEffect(() => {
    const generation = ++generationRef.current;
    loadRequestRef.current += 1;
    optimizeRequestRef.current += 1;
    setDiscardOpen(false);
    setError('');
    setOptimizing(false);
    resetOptimization();

    if (!open) {
      return;
    }

    const scope = draftStorageScope;
    setProfile('');
    setInitialProfile('');
    setSavedProfile('');
    setNickname('');
    setInitialNickname('');
    setSavedNickname(undefined);
    setNicknameSource('unavailable');
    setMaxLength(DEFAULT_MAX_LENGTH);
    setNicknameMaxLength(DEFAULT_NICKNAME_MAX_LENGTH);
    setLoaded(false);
    setSaving(false);
    setDismissing(false);
    void loadProfile(generation, scope);

    return () => {
      if (generationRef.current === generation) {
        generationRef.current += 1;
      }
      loadRequestRef.current += 1;
      optimizeRequestRef.current += 1;
    };
  }, [draftStorageScope, loadProfile, open, resetOptimization]);

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
    if (!loaded || saving || optimizing) {
      return;
    }

    const normalized = profile.trim();
    const normalizedNickname = nickname.trim();
    if (countUnicodeCodePoints(normalized) > maxLength) {
      textareaRef.current?.focus();
      return;
    }

    const generation = generationRef.current;
    const scope = draftStorageScope;
    const nicknameChanged = normalizedNickname !== initialNickname;
    const nicknameNeedsMigration =
      nicknameSource === 'legacy-migration' &&
      normalizedNickname === initialNickname &&
      normalizedNickname !== savedNickname;
    if (
      (nicknameChanged || nicknameNeedsMigration) &&
      countUnicodeCodePoints(normalizedNickname) > nicknameMaxLength
    ) {
      return;
    }
    setSaving(true);
    setError('');
    try {
      const response =
        nicknameChanged || nicknameNeedsMigration
          ? await updateLearnerProfile(normalized, normalizedNickname)
          : await updateLearnerProfile(normalized);
      if (!isCurrent(generation, scope)) {
        return;
      }
      setProfile(response.learner_profile);
      setInitialProfile(response.learner_profile);
      setSavedProfile(response.learner_profile);
      setMaxLength(response.max_length || maxLength);
      const responseNickname = resolveLearnerNicknameDraft(response);
      const nextNickname =
        responseNickname.savedValue === undefined
          ? normalizedNickname
          : responseNickname.value;
      setNickname(nextNickname);
      setInitialNickname(nextNickname);
      setSavedNickname(responseNickname.savedValue);
      setNicknameSource(
        responseNickname.savedValue === undefined
          ? 'legacy-compat'
          : responseNickname.source,
      );
      setNicknameMaxLength(response.nickname_max_length || nicknameMaxLength);
      resetOptimization();
      notifyLearnerProfileChanged();
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
    draftStorageScope,
    initialNickname,
    isCurrent,
    loaded,
    maxLength,
    nickname,
    nicknameMaxLength,
    nicknameSource,
    onClose,
    optimizing,
    profile,
    resetOptimization,
    runOnSaved,
    savedNickname,
    saving,
    t,
  ]);

  const normalizedProfile = profile.trim();
  const normalizedNickname = nickname.trim();
  const dirty =
    loaded &&
    (normalizedProfile !== initialProfile ||
      normalizedNickname !== initialNickname);
  const busy = saving || dismissing;
  const profileLength = countUnicodeCodePoints(normalizedProfile);
  const nicknameLength = countUnicodeCodePoints(normalizedNickname);
  const hasUnsavedPrefill = normalizedProfile !== savedProfile;
  const nicknameNeedsMigration =
    nicknameSource === 'legacy-migration' &&
    normalizedNickname === initialNickname &&
    normalizedNickname !== savedNickname;
  const nicknameWillBeSaved =
    normalizedNickname !== initialNickname || nicknameNeedsMigration;
  const canCompleteOnboarding =
    mode === 'onboarding' && Boolean(normalizedProfile || normalizedNickname);
  const canSave =
    loaded &&
    !busy &&
    !optimizing &&
    profileLength <= maxLength &&
    (!nicknameWillBeSaved || nicknameLength <= nicknameMaxLength) &&
    (dirty ||
      hasUnsavedPrefill ||
      nicknameNeedsMigration ||
      canCompleteOnboarding);

  const dismiss = React.useCallback(async () => {
    if (busy) {
      return;
    }
    const generation = generationRef.current;
    const scope = draftStorageScope;
    optimizeRequestRef.current += 1;
    setOptimizing(false);
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
      resetOptimization();
      setError('');
      textareaRef.current?.focus();
    },
    [resetOptimization, t],
  );

  const optimizeProfile = React.useCallback(async () => {
    const normalized = profile.trim();
    if (
      !loaded ||
      busy ||
      optimizing ||
      !normalized ||
      countUnicodeCodePoints(normalized) > maxLength
    ) {
      return;
    }

    const request = ++optimizeRequestRef.current;
    const generation = generationRef.current;
    const scope = draftStorageScope;
    const original = profile;
    setOptimizing(true);
    setOptimizationStatus('idle');
    setOptimizationOriginal(null);
    setError('');

    try {
      const response = await optimizeLearnerProfile(normalized);
      if (
        !isCurrent(generation, scope) ||
        request !== optimizeRequestRef.current
      ) {
        return;
      }

      const optimized = response?.optimized_learner_profile?.trim();
      if (!optimized || countUnicodeCodePoints(optimized) > maxLength) {
        throw new Error('Invalid learner profile optimization response');
      }

      if (optimized === normalized) {
        setOptimizationStatus('unchanged');
        return;
      }

      setProfile(optimized);
      setOptimizationOriginal(original);
      setOptimizationStatus('success');
    } catch (caughtError) {
      if (
        isCurrent(generation, scope) &&
        request === optimizeRequestRef.current
      ) {
        const code = (caughtError as { code?: number } | null)?.code;
        setOptimizationStatus(
          code === LEARNER_PROFILE_OPTIMIZATION_REJECTED_CODE
            ? 'rejected'
            : 'error',
        );
      }
    } finally {
      if (
        isCurrent(generation, scope) &&
        request === optimizeRequestRef.current
      ) {
        setOptimizing(false);
      }
    }
  }, [
    busy,
    draftStorageScope,
    isCurrent,
    loaded,
    maxLength,
    optimizing,
    profile,
  ]);

  const undoOptimization = React.useCallback(() => {
    if (optimizationOriginal === null) {
      return;
    }
    setProfile(optimizationOriginal);
    resetOptimization();
    setError('');
    textareaRef.current?.focus();
  }, [optimizationOriginal, resetOptimization]);

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
  const optimizeDisabled =
    !loaded ||
    busy ||
    optimizing ||
    !normalizedProfile ||
    profileLength > maxLength;
  const optimizationDescriptionKey = !normalizedProfile
    ? 'module.profileOnboarding.dialog.optimizeEmptyHint'
    : optimizationStatus === 'unchanged'
      ? 'module.profileOnboarding.dialog.optimizeUnchanged'
      : optimizationStatus === 'rejected'
        ? 'module.profileOnboarding.dialog.optimizeRejected'
        : optimizationStatus === 'error'
          ? 'module.profileOnboarding.dialog.optimizeFailed'
          : 'module.profileOnboarding.dialog.optimizeHint';
  const showOptimizationSuccess =
    optimizationStatus === 'success' && optimizationOriginal !== null;

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
          className='bottom-0 left-3 top-auto flex h-[calc(100dvh-96px)] w-[calc(100vw-24px)] max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-t-3xl border-b-0 p-0 sm:bottom-auto sm:left-1/2 sm:top-1/2 sm:h-auto sm:max-h-[min(97dvh,800px)] sm:w-[calc(100vw-48px)] sm:max-w-[680px] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border'
        >
          <div
            data-testid='learner-profile-mobile-handle'
            className='mx-auto mt-3 h-1 w-10 shrink-0 rounded-full bg-muted-foreground/35 sm:hidden'
            aria-hidden='true'
          />

          <div className='sticky top-0 z-10 bg-background px-5 pb-4 pt-5 sm:px-8 sm:pb-3 sm:pt-6'>
            <DialogHeader className='w-full space-y-3 text-left sm:space-y-2 sm:pr-12'>
              <DialogTitle className='text-2xl font-bold leading-8 tracking-tight sm:text-[28px] sm:leading-9'>
                {t(
                  mode === 'onboarding'
                    ? 'module.profileOnboarding.dialog.onboardingTitle'
                    : 'module.profileOnboarding.dialog.settingsTitle',
                )}
              </DialogTitle>
              <DialogDescription className='text-left text-sm leading-6 sm:text-base'>
                {t(
                  mode === 'settings'
                    ? 'module.profileOnboarding.dialog.settingsDescription'
                    : 'module.profileOnboarding.dialog.description',
                )}
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

          <div className='min-h-0 flex-1 overflow-y-auto px-5 pb-5 sm:px-8 sm:pb-5'>
            <div className='space-y-5 sm:space-y-3'>
              <div className='space-y-1.5 sm:grid sm:grid-cols-[minmax(0,180px)_1fr] sm:items-center sm:gap-3 sm:space-y-0'>
                <label
                  htmlFor='learner-profile-dialog-nickname'
                  className='text-sm font-semibold text-foreground'
                >
                  {t('module.profileOnboarding.dialog.nicknameLabel')}
                </label>
                <Input
                  id='learner-profile-dialog-nickname'
                  className='h-10 rounded-lg shadow-none focus-visible:ring-2 focus-visible:ring-primary/30'
                  value={nickname}
                  maxLength={nicknameMaxLength}
                  disabled={!loaded || busy}
                  placeholder={t(
                    'module.profileOnboarding.dialog.nicknamePlaceholder',
                  )}
                  onChange={event => {
                    setNickname(event.target.value);
                    setError('');
                  }}
                />
              </div>

              <section className='space-y-3'>
                <div className='space-y-1'>
                  <label
                    htmlFor='learner-profile-dialog-draft'
                    className='text-sm font-medium'
                  >
                    {t('module.profileOnboarding.dialog.profileLabel')}
                  </label>
                  <p className='text-xs leading-5 text-muted-foreground'>
                    {t('module.profileOnboarding.dialog.promptHeading')}
                  </p>
                </div>

                <div className='grid grid-cols-1 gap-2 sm:grid-cols-3'>
                  {PROFILE_PROMPTS.map(({ key, Icon }) => (
                    <Button
                      key={key}
                      type='button'
                      variant='outline'
                      data-testid={`learner-profile-guidance-${key}`}
                      className='h-auto min-h-16 items-start justify-start gap-2 rounded-xl border-primary/15 bg-primary/[0.05] px-3 py-2.5 text-left text-primary whitespace-normal hover:bg-primary/10 hover:text-primary'
                      disabled={!loaded || busy || optimizing}
                      onClick={() => insertPrompt(key)}
                    >
                      <Icon
                        className='mt-0.5 size-4 shrink-0'
                        aria-hidden='true'
                      />
                      <span className='min-w-0'>
                        <span className='block text-sm font-semibold leading-5'>
                          {t(
                            `module.profileOnboarding.dialog.chips.${key}.label`,
                          )}
                        </span>
                        <span className='mt-0.5 block text-xs font-normal leading-4 text-muted-foreground'>
                          {t(
                            `module.profileOnboarding.dialog.chips.${key}.hint`,
                          )}
                        </span>
                      </span>
                    </Button>
                  ))}
                </div>

                <ProfileDraftEditor
                  inputId='learner-profile-dialog-draft'
                  textareaRef={textareaRef}
                  textareaClassName='h-[clamp(7rem,16dvh,11rem)] min-h-[clamp(7rem,16dvh,11rem)] max-h-[clamp(7rem,16dvh,11rem)] resize-none overflow-y-auto rounded-xl border-border px-4 py-3 leading-6 shadow-none focus-visible:ring-primary/30'
                  minRows={4}
                  autoResize={false}
                  value={profile}
                  maxLength={maxLength}
                  disabled={!loaded || busy || optimizing}
                  label={null}
                  placeholder={t(
                    'module.profileOnboarding.dialog.profilePlaceholder',
                  )}
                  descriptionId='learner-profile-optimization-status'
                  onChange={value => {
                    setProfile(value);
                    resetOptimization();
                    setError('');
                  }}
                />

                <div
                  data-testid='learner-profile-optimization-card'
                  className='w-full'
                  aria-live='polite'
                >
                  <div className='flex h-24 items-center justify-between gap-3 rounded-xl border border-primary/20 bg-primary/[0.05] px-4 py-3 sm:h-20'>
                    <p
                      id='learner-profile-optimization-status'
                      className='min-w-0 flex-1 text-sm leading-5 text-foreground/80'
                    >
                      {t(
                        showOptimizationSuccess
                          ? 'module.profileOnboarding.dialog.optimizeSuccess'
                          : optimizationDescriptionKey,
                      )}
                    </p>
                    {showOptimizationSuccess ? (
                      <Button
                        type='button'
                        size='sm'
                        variant='outline'
                        className='min-h-11 shrink-0 px-4 sm:min-h-10'
                        onClick={undoOptimization}
                      >
                        {t('module.profileOnboarding.dialog.undoOptimize')}
                      </Button>
                    ) : (
                      <Button
                        type='button'
                        className='min-h-11 shrink-0 px-4 shadow-sm sm:min-h-10'
                        disabled={optimizeDisabled}
                        aria-describedby='learner-profile-optimization-status'
                        onClick={() => {
                          void optimizeProfile();
                        }}
                      >
                        {optimizing ? (
                          <Loader2
                            className='size-4 animate-spin'
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
                    )}
                  </div>
                </div>
              </section>

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

              <div
                data-testid='learner-profile-reassurance'
                className='flex items-start gap-2 px-1 text-xs leading-5 text-muted-foreground sm:text-sm'
              >
                <Info
                  className='mt-0.5 size-4 shrink-0 text-primary'
                  aria-hidden='true'
                />
                <span>{t('module.profileOnboarding.dialog.reassurance')}</span>
              </div>
            </div>
          </div>

          <div className='sticky bottom-0 z-10 flex items-center gap-2.5 border-t bg-background px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 sm:justify-end sm:gap-3 sm:px-8 sm:py-4'>
            <Button
              type='button'
              variant='outline'
              className='min-h-11 min-w-0 flex-1 sm:flex-none'
              disabled={busy}
              onClick={requestClose}
            >
              {secondaryLabel}
            </Button>
            <Button
              type='button'
              className='min-h-11 min-w-0 flex-[1.4] sm:flex-none'
              disabled={!canSave}
              onClick={() => {
                void saveProfile();
              }}
            >
              {saving
                ? t('module.profileOnboarding.dialog.saving')
                : primaryLabel}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

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
