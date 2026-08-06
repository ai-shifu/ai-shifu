'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  clearLearnerProfile,
  completeProfileOnboarding,
  getLearnerProfile,
  getProfileOnboarding,
  isProfileOnboardingV2Status,
  updateLearnerProfile,
} from '@/c-api/user';
import { Button } from '@/components/ui/Button';
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
import { useToast } from '@/hooks/useToast';
import { useTracking } from '@/c-common/hooks/useTracking';
import ProfileOnboardingModal, {
  ProfileDraftEditor,
  countUnicodeCodePoints,
} from './ProfileOnboardingModal';
import { PROFILE_ONBOARDING_EVENTS } from './events';

const DEFAULT_MAX_LENGTH = 1000;

export type LearnerProfileSettingsHandle = {
  saveIfDirty: () => Promise<boolean>;
};

type LearnerProfileSettingsSectionProps = {
  draftStorageScope?: string;
};

const LearnerProfileSettingsSection = React.forwardRef<
  LearnerProfileSettingsHandle,
  LearnerProfileSettingsSectionProps
>(function LearnerProfileSettingsSection({ draftStorageScope = '' }, ref) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [profile, setProfile] = React.useState('');
  const [savedProfile, setSavedProfile] = React.useState('');
  const [updatedAt, setUpdatedAt] = React.useState<string | null>(null);
  const [maxLength, setMaxLength] = React.useState(DEFAULT_MAX_LENGTH);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState('');
  const [clearOpen, setClearOpen] = React.useState(false);
  const [rerunOpen, setRerunOpen] = React.useState(false);
  const [collectionEnabled, setCollectionEnabled] = React.useState(false);
  const [guidedAvailable, setGuidedAvailable] = React.useState(false);
  const loadSequenceRef = React.useRef(0);
  const scopeRef = React.useRef(draftStorageScope);
  scopeRef.current = draftStorageScope;

  const loadProfile = React.useCallback(async (): Promise<boolean> => {
    const loadSequence = ++loadSequenceRef.current;
    const requestScope = draftStorageScope;
    const isCurrentRequest = () =>
      loadSequence === loadSequenceRef.current &&
      requestScope === scopeRef.current;
    setLoading(true);
    try {
      const response = await getLearnerProfile();
      if (!isCurrentRequest()) {
        return false;
      }
      const onboardingStatus = await getProfileOnboarding().catch(() => null);
      if (!isCurrentRequest()) {
        return false;
      }
      const nextProfile = response.learner_profile || '';
      setProfile(nextProfile);
      setSavedProfile(nextProfile);
      setUpdatedAt(response.learner_profile_updated_at || null);
      setMaxLength(response.max_length || DEFAULT_MAX_LENGTH);
      const compatibleStatus = isProfileOnboardingV2Status(onboardingStatus)
        ? onboardingStatus
        : null;
      setCollectionEnabled(Boolean(compatibleStatus?.enabled));
      setGuidedAvailable(Boolean(compatibleStatus?.guided_available));
      setError('');
      return true;
    } catch (caughtError) {
      if (isCurrentRequest()) {
        setError(
          caughtError instanceof Error && caughtError.message
            ? caughtError.message
            : t('module.profileOnboarding.settings.loadFailed'),
        );
      }
      return false;
    } finally {
      if (isCurrentRequest()) {
        setLoading(false);
      }
    }
  }, [draftStorageScope, t]);

  React.useEffect(() => {
    setProfile('');
    setSavedProfile('');
    setUpdatedAt(null);
    setMaxLength(DEFAULT_MAX_LENGTH);
    setSaving(false);
    setError('');
    setClearOpen(false);
    setRerunOpen(false);
    setCollectionEnabled(false);
    setGuidedAvailable(false);
    void loadProfile();
    return () => {
      loadSequenceRef.current += 1;
    };
  }, [loadProfile]);

  const saveProfile = React.useCallback(async (): Promise<boolean> => {
    const normalized = profile.trim();
    if (normalized === savedProfile) {
      return true;
    }
    if (!normalized || countUnicodeCodePoints(normalized) > maxLength) {
      return false;
    }
    const saveScope = draftStorageScope;
    setSaving(true);
    setError('');
    try {
      const response = await updateLearnerProfile(normalized);
      if (scopeRef.current !== saveScope) {
        return false;
      }
      setProfile(response.learner_profile);
      setSavedProfile(response.learner_profile);
      setUpdatedAt(response.learner_profile_updated_at || null);
      setMaxLength(response.max_length || maxLength);
      toast({ title: t('module.profileOnboarding.settings.saveSuccess') });
      void trackEvent(PROFILE_ONBOARDING_EVENTS.SETTINGS_SAVED);
      return true;
    } catch (caughtError) {
      if (scopeRef.current === saveScope) {
        setError(
          caughtError instanceof Error && caughtError.message
            ? caughtError.message
            : t('module.profileOnboarding.settings.saveFailed'),
        );
      }
      return false;
    } finally {
      if (scopeRef.current === saveScope) {
        setSaving(false);
      }
    }
  }, [
    draftStorageScope,
    maxLength,
    profile,
    savedProfile,
    t,
    toast,
    trackEvent,
  ]);

  React.useImperativeHandle(
    ref,
    () => ({
      saveIfDirty: saveProfile,
    }),
    [saveProfile],
  );

  const confirmClear = React.useCallback(async () => {
    const clearScope = draftStorageScope;
    setSaving(true);
    setError('');
    try {
      const response = await clearLearnerProfile();
      if (scopeRef.current !== clearScope) {
        return;
      }
      setProfile('');
      setSavedProfile('');
      setUpdatedAt(response.learner_profile_updated_at || null);
      setClearOpen(false);
      toast({ title: t('module.profileOnboarding.settings.clearSuccess') });
      void trackEvent(PROFILE_ONBOARDING_EVENTS.SETTINGS_CLEARED);
    } catch (caughtError) {
      if (scopeRef.current === clearScope) {
        setError(
          caughtError instanceof Error && caughtError.message
            ? caughtError.message
            : t('module.profileOnboarding.settings.clearFailed'),
        );
      }
    } finally {
      if (scopeRef.current === clearScope) {
        setSaving(false);
      }
    }
  }, [draftStorageScope, t, toast, trackEvent]);

  const hasChanges = profile.trim() !== savedProfile;
  const profileLength = countUnicodeCodePoints(profile.trim());
  const formattedUpdatedAt = updatedAt
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(updatedAt))
    : '';

  return (
    <section className='mt-8 border-t pt-6'>
      <h2 className='text-base font-semibold'>
        {t('module.profileOnboarding.settings.title')}
      </h2>
      <p className='mt-2 text-sm leading-6 text-muted-foreground'>
        {t('module.profileOnboarding.settings.description')}
      </p>

      {loading ? (
        <div
          className='mt-4 text-sm text-muted-foreground'
          role='status'
        >
          {t('module.profileOnboarding.settings.loading')}
        </div>
      ) : (
        <div className='mt-4 space-y-4'>
          <ProfileDraftEditor
            inputId='learner-profile-settings-draft'
            value={profile}
            maxLength={maxLength}
            disabled={saving}
            onChange={setProfile}
          />
          {formattedUpdatedAt ? (
            <p className='text-xs text-muted-foreground'>
              {t('module.profileOnboarding.settings.updatedAt', {
                time: formattedUpdatedAt,
              })}
            </p>
          ) : null}
          {error ? (
            <div
              role='alert'
              className='rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive'
            >
              {error}
            </div>
          ) : null}
          <div className='flex flex-wrap gap-2'>
            <Button
              type='button'
              size='sm'
              disabled={
                !profile.trim() ||
                !hasChanges ||
                profileLength > maxLength ||
                saving
              }
              onClick={() => {
                void saveProfile();
              }}
            >
              {t('module.profileOnboarding.settings.save')}
            </Button>
            {collectionEnabled ? (
              <Button
                type='button'
                size='sm'
                variant='outline'
                disabled={saving}
                onClick={() => {
                  void trackEvent(
                    PROFILE_ONBOARDING_EVENTS.SETTINGS_RERUN_STARTED,
                  );
                  setRerunOpen(true);
                }}
              >
                {t('module.profileOnboarding.settings.rerun')}
              </Button>
            ) : null}
            <Button
              type='button'
              size='sm'
              variant='ghost'
              className='text-destructive hover:text-destructive'
              disabled={!savedProfile || saving}
              onClick={() => setClearOpen(true)}
            >
              {t('module.profileOnboarding.settings.clear')}
            </Button>
          </div>
        </div>
      )}

      <AlertDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
      >
        <AlertDialogContent className='w-[calc(100vw-32px)]'>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('module.profileOnboarding.settings.clearTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('module.profileOnboarding.settings.clearDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={saving}>
              {t('module.profileOnboarding.settings.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={saving}
              className='bg-destructive text-destructive-foreground hover:bg-destructive/90'
              onClick={event => {
                event.preventDefault();
                void confirmClear();
              }}
            >
              {t('module.profileOnboarding.settings.confirmClear')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <ProfileOnboardingModal
        open={rerunOpen}
        draftStorageScope={draftStorageScope}
        presentation='non_blocking'
        sessionIntent='settings'
        guidedAvailable={guidedAvailable}
        maxLength={maxLength}
        submitting={saving}
        errorMessage={error}
        onComplete={async (learnerProfile, source, sessionId) => {
          const completionScope = draftStorageScope;
          setSaving(true);
          setError('');
          try {
            await completeProfileOnboarding({
              learner_profile: learnerProfile,
              trigger_source: source,
              ...(sessionId ? { session_id: sessionId } : {}),
            });
            if (scopeRef.current !== completionScope) {
              return false;
            }
            const refreshed = await loadProfile();
            if (!refreshed || scopeRef.current !== completionScope) {
              return false;
            }
            setRerunOpen(false);
            toast({
              title: t('module.profileOnboarding.settings.regenerateSuccess'),
            });
            return true;
          } catch (caughtError) {
            if (scopeRef.current === completionScope) {
              setError(
                caughtError instanceof Error && caughtError.message
                  ? caughtError.message
                  : t('module.profileOnboarding.settings.saveFailed'),
              );
            }
            return false;
          } finally {
            if (scopeRef.current === completionScope) {
              setSaving(false);
            }
          }
        }}
        onSkip={() => {
          setRerunOpen(false);
          return true;
        }}
      />
    </section>
  );
});

export default LearnerProfileSettingsSection;
