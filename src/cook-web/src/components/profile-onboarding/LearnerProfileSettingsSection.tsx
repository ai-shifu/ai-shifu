'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  clearLearnerProfile,
  getLearnerProfile,
  updateLearnerProfile,
} from '@/api/learnerProfile';
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
import { notifyLearnerProfileChanged } from '@/lib/learnerProfileEvents';
import {
  ProfileDraftEditor,
  countUnicodeCodePoints,
} from './ProfileDraftEditor';
import { buildLearnerProfileDraft } from './learnerProfileDraft';

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
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const [profile, setProfile] = React.useState('');
  const [savedProfile, setSavedProfile] = React.useState('');
  const [updatedAt, setUpdatedAt] = React.useState<string | null>(null);
  const [maxLength, setMaxLength] = React.useState(DEFAULT_MAX_LENGTH);
  const [loading, setLoading] = React.useState(true);
  const [profileLoaded, setProfileLoaded] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState('');
  const [clearOpen, setClearOpen] = React.useState(false);
  const translationRef = React.useRef(t);
  const loadSequenceRef = React.useRef(0);
  const operationGenerationRef = React.useRef(0);
  const mountedRef = React.useRef(true);
  const scopeRef = React.useRef(draftStorageScope);
  scopeRef.current = draftStorageScope;
  translationRef.current = t;

  const loadProfile = React.useCallback(async (): Promise<boolean> => {
    const loadSequence = ++loadSequenceRef.current;
    const requestGeneration = operationGenerationRef.current;
    const requestScope = draftStorageScope;
    const isCurrentRequest = () =>
      mountedRef.current &&
      requestGeneration === operationGenerationRef.current &&
      loadSequence === loadSequenceRef.current &&
      requestScope === scopeRef.current;
    setLoading(true);
    setProfileLoaded(false);
    try {
      const response = await getLearnerProfile();
      if (!isCurrentRequest()) {
        return false;
      }
      const nextProfile = buildLearnerProfileDraft(
        response,
        translationRef.current,
      );
      setProfile(nextProfile);
      setSavedProfile(response.learner_profile || '');
      setUpdatedAt(response.learner_profile_updated_at || null);
      setMaxLength(response.max_length || DEFAULT_MAX_LENGTH);
      setProfileLoaded(true);
      setError('');
      return true;
    } catch (caughtError) {
      if (isCurrentRequest()) {
        setError(
          caughtError instanceof Error && caughtError.message
            ? caughtError.message
            : translationRef.current(
                'module.profileOnboarding.settings.loadFailed',
              ),
        );
      }
      return false;
    } finally {
      if (isCurrentRequest()) {
        setLoading(false);
      }
    }
  }, [draftStorageScope]);

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      operationGenerationRef.current += 1;
      loadSequenceRef.current += 1;
    };
  }, []);

  React.useEffect(() => {
    const scopeGeneration = ++operationGenerationRef.current;
    setProfile('');
    setSavedProfile('');
    setUpdatedAt(null);
    setMaxLength(DEFAULT_MAX_LENGTH);
    setProfileLoaded(false);
    setSaving(false);
    setError('');
    setClearOpen(false);
    void loadProfile();
    return () => {
      if (operationGenerationRef.current === scopeGeneration) {
        operationGenerationRef.current += 1;
      }
      loadSequenceRef.current += 1;
    };
  }, [loadProfile]);

  const saveProfile = React.useCallback(async (): Promise<boolean> => {
    if (!profileLoaded) {
      return true;
    }
    const normalized = profile.trim();
    if (normalized === savedProfile) {
      return true;
    }
    if (!normalized) {
      setError(t('module.profileOnboarding.settings.emptyProfile'));
      return false;
    }
    if (countUnicodeCodePoints(normalized) > maxLength) {
      return false;
    }
    const saveScope = draftStorageScope;
    const saveGeneration = operationGenerationRef.current;
    const isCurrentSave = () =>
      mountedRef.current &&
      saveGeneration === operationGenerationRef.current &&
      scopeRef.current === saveScope;
    setSaving(true);
    setError('');
    try {
      const response = await updateLearnerProfile(normalized);
      if (!isCurrentSave()) {
        return false;
      }
      setProfile(response.learner_profile);
      setSavedProfile(response.learner_profile);
      setUpdatedAt(response.learner_profile_updated_at || null);
      setMaxLength(response.max_length || maxLength);
      notifyLearnerProfileChanged();
      toast({ title: t('module.profileOnboarding.settings.saveSuccess') });
      return true;
    } catch (caughtError) {
      if (isCurrentSave()) {
        setError(
          caughtError instanceof Error && caughtError.message
            ? caughtError.message
            : t('module.profileOnboarding.settings.saveFailed'),
        );
      }
      return false;
    } finally {
      if (isCurrentSave()) {
        setSaving(false);
      }
    }
  }, [
    draftStorageScope,
    maxLength,
    profileLoaded,
    profile,
    savedProfile,
    t,
    toast,
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
    const clearGeneration = operationGenerationRef.current;
    const isCurrentClear = () =>
      mountedRef.current &&
      clearGeneration === operationGenerationRef.current &&
      scopeRef.current === clearScope;
    setSaving(true);
    setError('');
    try {
      const response = await clearLearnerProfile();
      if (!isCurrentClear()) {
        return;
      }
      setProfile('');
      setSavedProfile('');
      setUpdatedAt(response.learner_profile_updated_at || null);
      setClearOpen(false);
      notifyLearnerProfileChanged();
      toast({ title: t('module.profileOnboarding.settings.clearSuccess') });
    } catch (caughtError) {
      if (isCurrentClear()) {
        setError(
          caughtError instanceof Error && caughtError.message
            ? caughtError.message
            : t('module.profileOnboarding.settings.clearFailed'),
        );
      }
    } finally {
      if (isCurrentClear()) {
        setSaving(false);
      }
    }
  }, [draftStorageScope, t, toast]);

  const hasChanges = profile.trim() !== savedProfile;
  const profileLength = countUnicodeCodePoints(profile.trim());
  const formDisabled = saving || !profileLoaded;
  const formattedUpdatedAt = updatedAt
    ? new Intl.DateTimeFormat(i18n.resolvedLanguage || i18n.language, {
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
            disabled={formDisabled}
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
            {!profileLoaded ? (
              <Button
                type='button'
                size='sm'
                variant='outline'
                disabled={loading || saving}
                onClick={() => {
                  void loadProfile();
                }}
              >
                {t('module.profileOnboarding.settings.retry')}
              </Button>
            ) : null}
            <Button
              type='button'
              size='sm'
              disabled={
                !profile.trim() ||
                !hasChanges ||
                profileLength > maxLength ||
                formDisabled
              }
              onClick={() => {
                void saveProfile();
              }}
            >
              {t('module.profileOnboarding.settings.save')}
            </Button>
            <Button
              type='button'
              size='sm'
              variant='ghost'
              className='text-destructive hover:text-destructive'
              disabled={!savedProfile || formDisabled}
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
    </section>
  );
});

export default LearnerProfileSettingsSection;
