'use client';

import React from 'react';
import { Loader2, Sparkles, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  completeGuidedProfileOnboarding,
  createProfileOnboardingSession,
  getLearnerProfile,
  getProfileOnboardingV2,
  isProfileOnboardingV2Status,
  optimizeLearnerProfile,
  runProfileOnboardingSession,
  updateLearnerProfile,
  type ProfileOnboardingPresentation,
  type ProfileOnboardingSessionIntent,
  type ProfileOnboardingV2Status,
} from '@/api/learnerProfile';
import { useTracking } from '@/c-common/hooks/useTracking';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { useToast } from '@/hooks/useToast';
import { cn } from '@/lib/utils';
import { PROFILE_ONBOARDING_EVENTS } from './events';
import {
  ProfileDraftEditor,
  countUnicodeCodePoints,
} from './ProfileDraftEditor';
import ProfileOnboardingConversation from './ProfileOnboardingConversation';
import {
  buildLearnerProfileDraft,
  resolveLearnerNicknameDraft,
  type LearnerNicknameSource,
} from './learnerProfileDraft';

const DEFAULT_MAX_LENGTH = 1000;
const DEFAULT_NICKNAME_MAX_LENGTH = 64;

type DialogPhase = 'collect' | 'processing' | 'save';
type DialogConfirmation = 'discard' | 'replace-collection';
type OptimizationStatus = 'idle' | 'success' | 'error';
type CollectionTriggerSource = 'guided' | 'settings';

export type ProfileCollectionResult = {
  draft: string;
  completion: {
    triggerSource: CollectionTriggerSource;
    sessionId: string;
  };
  postProcess: 'optimize';
};

export type LearnerProfileDialogProps = {
  open: boolean;
  exitPolicy: 'blocking' | 'dismissible';
  draftStorageScope: string;
  presentation?: ProfileOnboardingPresentation;
  initialOnboardingStatus?: ProfileOnboardingV2Status;
  externalErrorMessage?: string;
  externalSubmitting?: boolean;
  onDefer?: (sessionId?: string) => boolean | void | Promise<boolean | void>;
  onClose: (reason: 'dismiss' | 'saved') => void | Promise<void>;
  onSaved?: () => void | Promise<void>;
};

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error && error.message ? error.message : fallback;

export default function LearnerProfileDialog({
  open,
  exitPolicy,
  draftStorageScope,
  presentation = 'hidden',
  initialOnboardingStatus,
  externalErrorMessage = '',
  externalSubmitting = false,
  onDefer,
  onClose,
  onSaved,
}: LearnerProfileDialogProps) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [phase, setPhase] = React.useState<DialogPhase>('save');
  const [collectionIntent, setCollectionIntent] =
    React.useState<ProfileOnboardingSessionIntent>('onboarding');
  const [activeCollectionSessionId, setActiveCollectionSessionId] =
    React.useState('');
  const [collectionResult, setCollectionResult] =
    React.useState<ProfileCollectionResult | null>(null);
  const [collectionError, setCollectionError] = React.useState('');
  const [collectionKey, setCollectionKey] = React.useState(0);
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
  const [guidedAvailable, setGuidedAvailable] = React.useState(false);
  const [preferredCollectionIntent, setPreferredCollectionIntent] =
    React.useState<ProfileOnboardingSessionIntent>('onboarding');
  const [manualFallback, setManualFallback] = React.useState(false);
  const [maxLength, setMaxLength] = React.useState(DEFAULT_MAX_LENGTH);
  const [nicknameMaxLength, setNicknameMaxLength] = React.useState(
    DEFAULT_NICKNAME_MAX_LENGTH,
  );
  const [loading, setLoading] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [dismissing, setDismissing] = React.useState(false);
  const [deferring, setDeferring] = React.useState(false);
  const [error, setError] = React.useState('');
  const [optimizing, setOptimizing] = React.useState(false);
  const [optimizationStatus, setOptimizationStatus] =
    React.useState<OptimizationStatus>('idle');
  const [optimizationErrorMessage, setOptimizationErrorMessage] =
    React.useState('');
  const [optimizationOriginal, setOptimizationOriginal] = React.useState<
    string | null
  >(null);
  const [confirmation, setConfirmation] =
    React.useState<DialogConfirmation | null>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const viewHeadingRef = React.useRef<HTMLHeadingElement | null>(null);
  const confirmationHeadingRef = React.useRef<HTMLHeadingElement | null>(null);
  const contentScrollRef = React.useRef<HTMLDivElement | null>(null);
  const translationRef = React.useRef(t);
  const mountedRef = React.useRef(false);
  const openRef = React.useRef(open);
  const scopeRef = React.useRef(draftStorageScope);
  const presentationRef = React.useRef(presentation);
  const initialOnboardingStatusRef = React.useRef(initialOnboardingStatus);
  const generationRef = React.useRef(0);
  const loadRequestRef = React.useRef(0);
  const optimizeRequestRef = React.useRef(0);
  const collectionJourneyRef = React.useRef(0);
  const collectionCompletionRef = React.useRef(false);
  const collectionShownAtRef = React.useRef<number | null>(null);
  const hasCanonicalProfileRef = React.useRef(false);

  openRef.current = open;
  scopeRef.current = draftStorageScope;
  presentationRef.current = presentation;
  initialOnboardingStatusRef.current = initialOnboardingStatus;
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
    setOptimizationErrorMessage('');
    setOptimizationOriginal(null);
  }, []);

  const beginCollection = React.useCallback(
    (
      intent: ProfileOnboardingSessionIntent,
      rerun: boolean,
      journeyPresentation = presentationRef.current,
    ) => {
      const journey = ++collectionJourneyRef.current;
      collectionCompletionRef.current = false;
      collectionShownAtRef.current = Date.now();
      optimizeRequestRef.current += 1;
      setOptimizing(false);
      setCollectionIntent(intent);
      setActiveCollectionSessionId('');
      setCollectionError('');
      setCollectionKey(journey);
      setPhase('collect');
      resetOptimization();
      if (rerun) {
        void trackEvent(PROFILE_ONBOARDING_EVENTS.SETTINGS_RERUN_STARTED);
      }
      void trackEvent(PROFILE_ONBOARDING_EVENTS.SHOWN, {
        source: intent === 'settings' ? 'settings' : 'guided',
        presentation: journeyPresentation,
        has_profile: hasCanonicalProfileRef.current,
      });
    },
    [resetOptimization, trackEvent],
  );

  const loadProfile = React.useCallback(
    async (generation: number, scope: string): Promise<boolean> => {
      const request = ++loadRequestRef.current;
      setLoading(true);
      setLoaded(false);
      setError('');
      try {
        const openingOnboardingStatus = initialOnboardingStatusRef.current;
        const onboardingStatusRequest = openingOnboardingStatus
          ? Promise.resolve(openingOnboardingStatus)
          : getProfileOnboardingV2().catch(() => null);
        const response = await getLearnerProfile();
        if (
          !isCurrent(generation, scope) ||
          request !== loadRequestRef.current
        ) {
          return false;
        }

        const nextHasCanonicalProfile = Boolean(response.has_learner_profile);
        const nextProfile = buildLearnerProfileDraft(
          response,
          translationRef.current,
        );
        const nicknameDraft = resolveLearnerNicknameDraft(response);

        setProfile(nextProfile);
        setInitialProfile(nextProfile);
        setSavedProfile(response.learner_profile || '');
        setNickname(nicknameDraft.value);
        setInitialNickname(nicknameDraft.value);
        setSavedNickname(nicknameDraft.savedValue);
        setNicknameSource(nicknameDraft.source);
        hasCanonicalProfileRef.current = nextHasCanonicalProfile;
        setMaxLength(response.max_length || DEFAULT_MAX_LENGTH);
        setNicknameMaxLength(
          response.nickname_max_length || DEFAULT_NICKNAME_MAX_LENGTH,
        );
        resetOptimization();

        if (nextHasCanonicalProfile) {
          setPreferredCollectionIntent('settings');
          setManualFallback(false);
          setPhase('save');
          setLoaded(true);
          setLoading(false);
        }

        const onboardingStatus = await onboardingStatusRequest;
        if (
          !isCurrent(generation, scope) ||
          request !== loadRequestRef.current
        ) {
          return false;
        }

        const validOnboardingStatus = isProfileOnboardingV2Status(
          onboardingStatus,
        )
          ? onboardingStatus
          : null;
        const nextGuidedAvailable = Boolean(
          validOnboardingStatus?.enabled &&
          validOnboardingStatus.guided_available,
        );
        const nextCollectionIntent: ProfileOnboardingSessionIntent =
          nextHasCanonicalProfile || validOnboardingStatus?.handled
            ? 'settings'
            : 'onboarding';
        setGuidedAvailable(nextGuidedAvailable);
        setPreferredCollectionIntent(nextCollectionIntent);

        if (!nextHasCanonicalProfile) {
          setManualFallback(!nextGuidedAvailable);
          setLoaded(true);
          if (nextGuidedAvailable) {
            beginCollection(
              nextCollectionIntent,
              false,
              validOnboardingStatus?.presentation ?? presentationRef.current,
            );
          } else {
            setPhase('save');
          }
        }
        return true;
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
        return false;
      } finally {
        if (
          isCurrent(generation, scope) &&
          request === loadRequestRef.current
        ) {
          setLoading(false);
        }
      }
    },
    [beginCollection, isCurrent, resetOptimization],
  );

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      loadRequestRef.current += 1;
      optimizeRequestRef.current += 1;
      collectionJourneyRef.current += 1;
    };
  }, []);

  React.useEffect(() => {
    const generation = ++generationRef.current;
    loadRequestRef.current += 1;
    optimizeRequestRef.current += 1;
    collectionJourneyRef.current += 1;
    collectionCompletionRef.current = false;
    collectionShownAtRef.current = null;
    setConfirmation(null);
    setActiveCollectionSessionId('');
    setCollectionResult(null);
    setCollectionError('');
    setGuidedAvailable(false);
    setManualFallback(false);
    setError('');
    setOptimizing(false);
    resetOptimization();

    if (!open) {
      return;
    }

    const scope = draftStorageScope;
    setPhase('save');
    setProfile('');
    setInitialProfile('');
    setSavedProfile('');
    setNickname('');
    setInitialNickname('');
    setSavedNickname(undefined);
    setNicknameSource('unavailable');
    hasCanonicalProfileRef.current = false;
    setMaxLength(DEFAULT_MAX_LENGTH);
    setNicknameMaxLength(DEFAULT_NICKNAME_MAX_LENGTH);
    setLoaded(false);
    setSaving(false);
    setDismissing(false);
    setDeferring(false);
    void loadProfile(generation, scope);

    return () => {
      if (generationRef.current === generation) {
        generationRef.current += 1;
      }
      loadRequestRef.current += 1;
      optimizeRequestRef.current += 1;
      collectionJourneyRef.current += 1;
    };
  }, [draftStorageScope, loadProfile, open, resetOptimization]);

  React.useLayoutEffect(() => {
    if (exitPolicy === 'blocking' && confirmation === 'discard') {
      setConfirmation(null);
    }
  }, [confirmation, exitPolicy]);

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

  const normalizedProfile = profile.trim();
  const normalizedNickname = nickname.trim();
  const dirty =
    loaded &&
    (normalizedProfile !== initialProfile ||
      normalizedNickname !== initialNickname);
  const busy = saving || dismissing || deferring || externalSubmitting;
  const profileLength = countUnicodeCodePoints(normalizedProfile);
  const nicknameLength = countUnicodeCodePoints(normalizedNickname);
  const hasUnsavedPrefill = normalizedProfile !== savedProfile;
  const nicknameNeedsMigration =
    nicknameSource === 'legacy-migration' &&
    normalizedNickname === initialNickname &&
    normalizedNickname !== savedNickname;
  const nicknameWillBeSaved =
    normalizedNickname !== initialNickname || nicknameNeedsMigration;
  const nicknameOverLimit =
    nicknameWillBeSaved && nicknameLength > nicknameMaxLength;
  const canCompleteBlocking =
    exitPolicy === 'blocking' &&
    Boolean(normalizedProfile || normalizedNickname);
  const canSave =
    loaded &&
    phase === 'save' &&
    !busy &&
    !optimizing &&
    profileLength <= maxLength &&
    !nicknameOverLimit &&
    (dirty ||
      hasUnsavedPrefill ||
      nicknameNeedsMigration ||
      Boolean(collectionResult && normalizedProfile) ||
      canCompleteBlocking);

  const applyProfileResponse = React.useCallback(
    (response: Awaited<ReturnType<typeof updateLearnerProfile>>) => {
      const nextProfile = buildLearnerProfileDraft(
        response,
        translationRef.current,
      );
      const responseNickname = resolveLearnerNicknameDraft(response);
      setProfile(nextProfile);
      setInitialProfile(nextProfile);
      setSavedProfile(response.learner_profile || '');
      setNickname(responseNickname.value);
      setInitialNickname(responseNickname.value);
      setSavedNickname(responseNickname.savedValue);
      setNicknameSource(responseNickname.source);
      hasCanonicalProfileRef.current = Boolean(response.has_learner_profile);
      setMaxLength(response.max_length || maxLength);
      setNicknameMaxLength(response.nickname_max_length || nicknameMaxLength);
      setActiveCollectionSessionId('');
      setCollectionResult(null);
      resetOptimization();
    },
    [maxLength, nicknameMaxLength, resetOptimization],
  );

  const saveProfile = React.useCallback(async () => {
    if (!loaded || !canSave || saving || optimizing) {
      return;
    }
    if (profileLength > maxLength || nicknameOverLimit) {
      textareaRef.current?.focus();
      return;
    }

    const generation = generationRef.current;
    const scope = draftStorageScope;
    const nicknameChanged = normalizedNickname !== initialNickname;
    setSaving(true);
    setError('');
    try {
      const nicknamePayload =
        nicknameChanged || nicknameNeedsMigration
          ? { nickname: normalizedNickname }
          : {};
      let response: Awaited<ReturnType<typeof updateLearnerProfile>>;
      const completion = collectionResult?.completion;
      if (completion) {
        response = await completeGuidedProfileOnboarding({
          learner_profile: normalizedProfile,
          trigger_source: completion.triggerSource,
          session_id: completion.sessionId,
          ...nicknamePayload,
        });
      } else {
        response = await updateLearnerProfile(
          normalizedProfile,
          nicknameChanged || nicknameNeedsMigration
            ? normalizedNickname
            : undefined,
        );
      }
      if (!isCurrent(generation, scope)) {
        return;
      }

      applyProfileResponse(response);
      if (completion) {
        const shownAt = collectionShownAtRef.current;
        void trackEvent(PROFILE_ONBOARDING_EVENTS.COMPLETED, {
          source: completion.triggerSource,
          presentation,
          ...(shownAt === null ? {} : { duration_ms: Date.now() - shownAt }),
        });
      } else if (exitPolicy === 'dismissible') {
        void trackEvent(
          normalizedProfile
            ? PROFILE_ONBOARDING_EVENTS.SETTINGS_SAVED
            : PROFILE_ONBOARDING_EVENTS.SETTINGS_CLEARED,
        );
      }
      await onClose('saved');
      void runOnSaved(generation, scope);
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
    applyProfileResponse,
    canSave,
    draftStorageScope,
    exitPolicy,
    initialNickname,
    isCurrent,
    loaded,
    maxLength,
    nicknameNeedsMigration,
    nicknameOverLimit,
    normalizedNickname,
    normalizedProfile,
    onClose,
    optimizing,
    presentation,
    profileLength,
    collectionResult,
    runOnSaved,
    saving,
    t,
    trackEvent,
  ]);

  const dismiss = React.useCallback(async () => {
    if (saving || dismissing || deferring) {
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
  }, [deferring, dismissing, draftStorageScope, isCurrent, onClose, saving, t]);

  const requestClose = React.useCallback(() => {
    if (exitPolicy === 'blocking' || saving || dismissing || deferring) {
      return;
    }
    if (dirty) {
      setConfirmation('discard');
      return;
    }
    void dismiss();
  }, [deferring, dirty, dismiss, dismissing, exitPolicy, saving]);

  const performOptimization = React.useCallback(
    async (draft: string, automatic: boolean) => {
      const normalized = draft.trim();
      if (!loaded || optimizing) {
        return;
      }

      const invalidAutomaticDraft =
        !normalized || countUnicodeCodePoints(normalized) > maxLength;
      if (!automatic && invalidAutomaticDraft) {
        return;
      }

      const request = ++optimizeRequestRef.current;
      const generation = generationRef.current;
      const scope = draftStorageScope;
      setOptimizing(true);
      setOptimizationStatus('idle');
      setOptimizationErrorMessage('');
      setOptimizationOriginal(draft);
      setError('');
      if (automatic) {
        setPhase('processing');
      }

      if (invalidAutomaticDraft) {
        // Keep the processing transition perceptible before returning the raw
        // collection result with a corrective status.
        await new Promise<void>(resolve => setTimeout(resolve, 0));
        if (
          !isCurrent(generation, scope) ||
          request !== optimizeRequestRef.current
        ) {
          return;
        }
        setProfile(draft);
        setOptimizationErrorMessage(
          t('module.profileOnboarding.dialog.optimizeFailed'),
        );
        setOptimizationStatus('error');
        setOptimizing(false);
        setPhase('save');
        return;
      }

      try {
        const response = await optimizeLearnerProfile(normalized);
        if (
          !isCurrent(generation, scope) ||
          request !== optimizeRequestRef.current
        ) {
          return;
        }
        const optimized = response?.optimized_learner_profile;
        if (typeof optimized !== 'string') {
          throw new Error(
            t('module.profileOnboarding.dialog.optimizeInvalidResponse'),
          );
        }
        if (!optimized.trim()) {
          throw new Error(
            t('module.profileOnboarding.dialog.optimizeEmptyResponse'),
          );
        }
        setProfile(optimized);
        setOptimizationStatus('success');
      } catch (caughtError) {
        if (
          isCurrent(generation, scope) &&
          request === optimizeRequestRef.current
        ) {
          setProfile(draft);
          setOptimizationErrorMessage(
            errorMessage(
              caughtError,
              t('module.profileOnboarding.dialog.optimizeFailed'),
            ),
          );
          setOptimizationStatus('error');
        }
      } finally {
        if (
          isCurrent(generation, scope) &&
          request === optimizeRequestRef.current
        ) {
          setOptimizing(false);
          if (automatic) {
            setPhase('save');
          }
        }
      }
    },
    [draftStorageScope, isCurrent, loaded, maxLength, optimizing, t],
  );

  const optimizeProfile = React.useCallback(() => {
    void performOptimization(profile, false);
  }, [performOptimization, profile]);

  const useCollectionDraft = React.useCallback(() => {
    const draft = collectionResult?.draft;
    if (!draft) {
      return;
    }
    setProfile(draft);
    setOptimizationStatus('idle');
    setOptimizationErrorMessage('');
    setOptimizationOriginal(draft);
    setError('');
    textareaRef.current?.focus();
  }, [collectionResult]);

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

  const createCollectionSession = React.useCallback(
    () =>
      createProfileOnboardingSession(
        i18n.resolvedLanguage ?? i18n.language,
        collectionIntent,
      ),
    [collectionIntent, i18n.language, i18n.resolvedLanguage],
  );

  const runCollectionSession = React.useCallback(
    ({
      sessionId,
      expectedBlockIndex,
      requestId,
      userInput,
      onMessage,
      onError,
    }: Parameters<
      React.ComponentProps<typeof ProfileOnboardingConversation>['runSession']
    >[0]) =>
      runProfileOnboardingSession({
        sessionId,
        expectedBlockIndex,
        requestId,
        userInput,
        language: i18n.resolvedLanguage ?? i18n.language,
        onMessage,
        onError,
      }),
    [i18n.language, i18n.resolvedLanguage],
  );

  const acceptCollectionResult = React.useCallback(
    (
      result: ProfileCollectionResult,
      journey: number,
      generation: number,
      scope: string,
    ) => {
      if (
        journey !== collectionJourneyRef.current ||
        !isCurrent(generation, scope) ||
        collectionCompletionRef.current
      ) {
        return;
      }
      collectionCompletionRef.current = true;
      setCollectionResult(result);
      setActiveCollectionSessionId(result.completion.sessionId);
      setCollectionError('');
      setProfile(result.draft);
      if (result.postProcess === 'optimize') {
        void performOptimization(result.draft, true);
      } else {
        setPhase('save');
      }
    },
    [isCurrent, performOptimization],
  );

  const cancelCollection = React.useCallback(() => {
    collectionJourneyRef.current += 1;
    optimizeRequestRef.current += 1;
    collectionCompletionRef.current = false;
    setOptimizing(false);
    setActiveCollectionSessionId(collectionResult?.completion.sessionId ?? '');
    setCollectionError('');
    setPhase('save');
    resetOptimization();
  }, [collectionResult, resetOptimization]);

  const requestCollection = React.useCallback(() => {
    if (busy || optimizing || !guidedAvailable) {
      return;
    }
    if (dirty) {
      setConfirmation('replace-collection');
      return;
    }
    beginCollection(preferredCollectionIntent, true);
  }, [
    beginCollection,
    busy,
    dirty,
    guidedAvailable,
    optimizing,
    preferredCollectionIntent,
  ]);

  const deferOnboarding = React.useCallback(async () => {
    if (
      exitPolicy !== 'blocking' ||
      !onDefer ||
      saving ||
      deferring ||
      externalSubmitting
    ) {
      return;
    }
    const generation = generationRef.current;
    const scope = draftStorageScope;
    setDeferring(true);
    setError('');
    try {
      const result = await onDefer(activeCollectionSessionId || undefined);
      if (result === false || !isCurrent(generation, scope)) {
        return;
      }
      optimizeRequestRef.current += 1;
      collectionJourneyRef.current += 1;
      setOptimizing(false);
      void trackEvent(PROFILE_ONBOARDING_EVENTS.SKIPPED, {
        source:
          collectionResult?.completion.triggerSource ??
          (collectionIntent === 'settings' ? 'settings' : 'guided'),
        presentation,
      });
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
        setDeferring(false);
      }
    }
  }, [
    deferring,
    draftStorageScope,
    externalSubmitting,
    isCurrent,
    exitPolicy,
    onClose,
    onDefer,
    presentation,
    activeCollectionSessionId,
    collectionIntent,
    collectionResult,
    saving,
    t,
    trackEvent,
  ]);

  const optimizeDisabled =
    !loaded ||
    busy ||
    optimizing ||
    !normalizedProfile ||
    profileLength > maxLength;
  const showCollectionOptimizationActions = Boolean(collectionResult?.draft);
  const optimizationDescription = !normalizedProfile
    ? t('module.profileOnboarding.dialog.optimizeEmptyHint')
    : optimizationStatus === 'error'
      ? optimizationErrorMessage ||
        t('module.profileOnboarding.dialog.optimizeFailed')
      : optimizationStatus === 'success'
        ? t('module.profileOnboarding.dialog.optimizeSuccess')
        : t('module.profileOnboarding.dialog.optimizeHint');
  const combinedCollectionError = collectionError || externalErrorMessage;
  const combinedDialogError =
    error || (phase === 'collect' ? '' : externalErrorMessage);
  const renderedGeneration = generationRef.current;
  const renderedScope = draftStorageScope;
  const primaryLabel =
    hasCanonicalProfileRef.current && !collectionResult
      ? t('module.profileOnboarding.dialog.saveChanges')
      : t('module.profileOnboarding.complete');

  const renderSave = () => (
    <div className='space-y-5 sm:space-y-4'>
      <h2
        ref={viewHeadingRef}
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
            onChange={event => {
              setNickname(event.target.value);
              setError('');
            }}
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
          placeholder={t('module.profileOnboarding.dialog.profilePlaceholder')}
          descriptionId='learner-profile-optimization-status'
          onChange={value => {
            setProfile(value);
            resetOptimization();
            setError('');
          }}
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
              {showCollectionOptimizationActions ? (
                <Button
                  type='button'
                  size='sm'
                  variant='outline'
                  className='min-h-10 flex-1 sm:flex-none'
                  disabled={busy || optimizing}
                  onClick={useCollectionDraft}
                >
                  {t('module.profileOnboarding.dialog.useResearchDraft')}
                </Button>
              ) : optimizationStatus === 'success' &&
                optimizationOriginal !== null ? (
                <Button
                  type='button'
                  size='sm'
                  variant='outline'
                  className='min-h-10 flex-1 sm:flex-none'
                  onClick={undoOptimization}
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
                onClick={optimizeProfile}
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
                    : showCollectionOptimizationActions
                      ? 'module.profileOnboarding.dialog.retryOptimize'
                      : 'module.profileOnboarding.dialog.optimize',
                )}
              </Button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );

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
          className='bottom-3 left-3 top-3 flex h-auto max-h-none w-[calc(100vw-24px)] max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-2xl p-0 motion-reduce:animate-none motion-reduce:duration-0 sm:bottom-auto sm:left-1/2 sm:top-1/2 sm:h-[min(88dvh,760px)] sm:w-[calc(100vw-48px)] sm:max-w-[900px] sm:-translate-x-1/2 sm:-translate-y-1/2'
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
                {error ? (
                  <div
                    role='alert'
                    className='rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'
                  >
                    <p>{error}</p>
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
              <section
                data-testid={`learner-profile-confirmation-${confirmation}`}
                className='mx-auto flex h-full min-h-64 max-w-lg flex-col justify-center'
              >
                <h2
                  ref={confirmationHeadingRef}
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
            ) : phase === 'collect' ? (
              <section className='flex min-h-0 flex-1 flex-col'>
                <div className='mb-3 shrink-0 [@media(max-height:620px)]:mb-2'>
                  <h2
                    ref={viewHeadingRef}
                    tabIndex={-1}
                    className='text-xl font-semibold leading-7 outline-none'
                  >
                    {t('module.profileOnboarding.guided.title')}
                  </h2>
                  <p className='mt-1 text-sm leading-6 text-muted-foreground'>
                    {t('module.profileOnboarding.guided.description')}
                  </p>
                </div>
                <div className='min-h-40 flex-1 [@media(max-height:620px)]:min-h-32'>
                  <ProfileOnboardingConversation
                    key={collectionKey}
                    createSession={createCollectionSession}
                    runSession={runCollectionSession}
                    disabled={busy}
                    errorMessage={combinedCollectionError}
                    onSessionStarted={sessionId => {
                      if (
                        collectionKey === collectionJourneyRef.current &&
                        isCurrent(renderedGeneration, renderedScope)
                      ) {
                        setActiveCollectionSessionId(sessionId);
                      }
                    }}
                    onDraftReady={(draft, sessionId) =>
                      acceptCollectionResult(
                        {
                          draft,
                          completion: {
                            triggerSource:
                              collectionIntent === 'settings'
                                ? 'settings'
                                : 'guided',
                            sessionId,
                          },
                          postProcess: 'optimize',
                        },
                        collectionKey,
                        renderedGeneration,
                        renderedScope,
                      )
                    }
                    onRetry={() => {
                      if (
                        collectionKey === collectionJourneyRef.current &&
                        isCurrent(renderedGeneration, renderedScope)
                      ) {
                        setCollectionError('');
                      }
                    }}
                    onError={caughtError => {
                      if (
                        collectionKey !== collectionJourneyRef.current ||
                        !isCurrent(renderedGeneration, renderedScope)
                      ) {
                        return;
                      }
                      void trackEvent(
                        PROFILE_ONBOARDING_EVENTS.RUNTIME_FAILED,
                        { stage: 'guided', presentation },
                      );
                      setCollectionError(
                        errorMessage(
                          caughtError,
                          t('module.profileOnboarding.guided.streamError'),
                        ),
                      );
                    }}
                  />
                </div>
                <details className='mt-3 max-h-[min(10rem,35dvh)] shrink-0 overflow-y-auto rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground [@media(max-height:620px)]:mt-2'>
                  <summary className='cursor-pointer font-medium text-foreground'>
                    {t('module.profileOnboarding.dialog.informationUsageTitle')}
                  </summary>
                  <ul className='mt-2 list-disc space-y-1 pl-5 leading-5'>
                    <li>
                      {t(
                        'module.profileOnboarding.dialog.informationUsagePurpose',
                      )}
                    </li>
                    <li>
                      {t(
                        'module.profileOnboarding.dialog.informationUsageSensitive',
                      )}
                    </li>
                    <li>
                      {t(
                        'module.profileOnboarding.dialog.informationUsageEditable',
                      )}
                    </li>
                  </ul>
                </details>
              </section>
            ) : phase === 'processing' ? (
              <section className='flex h-full min-h-64 flex-col items-center justify-center px-4 text-center'>
                <Loader2
                  className='size-8 animate-spin text-primary motion-reduce:animate-none'
                  aria-hidden='true'
                />
                <h2
                  ref={viewHeadingRef}
                  tabIndex={-1}
                  className='mt-5 text-xl font-semibold leading-7 outline-none'
                >
                  {t('module.profileOnboarding.dialog.autoOptimizing')}
                </h2>
                <p className='mt-2 max-w-md text-sm leading-6 text-muted-foreground'>
                  {t('module.profileOnboarding.dialog.autoOptimizingHint')}
                </p>
              </section>
            ) : (
              renderSave()
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
                  onClick={() => {
                    const action = confirmation;
                    setConfirmation(null);
                    if (action === 'discard') {
                      void dismiss();
                    } else {
                      beginCollection(preferredCollectionIntent, true);
                    }
                  }}
                >
                  {t(
                    confirmation === 'discard'
                      ? 'module.profileOnboarding.dialog.discard'
                      : 'module.profileOnboarding.dialog.replaceResearchConfirm',
                  )}
                </Button>
              </>
            ) : (
              <>
                {phase !== 'save' && exitPolicy === 'blocking' ? (
                  <Button
                    type='button'
                    variant='ghost'
                    className='mr-auto min-h-11 px-3 text-muted-foreground !whitespace-normal'
                    disabled={
                      !onDefer || saving || deferring || externalSubmitting
                    }
                    onClick={() => void deferOnboarding()}
                  >
                    {deferring || externalSubmitting
                      ? t('module.profileOnboarding.skipping')
                      : t('module.profileOnboarding.skip')}
                  </Button>
                ) : phase === 'collect' ? (
                  <Button
                    type='button'
                    variant='outline'
                    className='min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                    disabled={busy}
                    onClick={cancelCollection}
                  >
                    {t('module.profileOnboarding.dialog.cancelResearch')}
                  </Button>
                ) : null}

                {phase === 'save' ? (
                  <>
                    {guidedAvailable || exitPolicy === 'blocking' ? (
                      <div
                        data-testid='learner-profile-dialog-left-actions'
                        className='mr-auto flex w-full min-w-0 flex-wrap items-center justify-start gap-2.5 sm:w-auto sm:gap-3'
                      >
                        {guidedAvailable ? (
                          <Button
                            type='button'
                            variant='outline'
                            className='min-h-11 min-w-0 !whitespace-normal'
                            disabled={busy || optimizing}
                            onClick={requestCollection}
                          >
                            {t(
                              'module.profileOnboarding.dialog.interactiveCollection',
                            )}
                          </Button>
                        ) : null}
                        {exitPolicy === 'blocking' ? (
                          <Button
                            type='button'
                            variant='ghost'
                            className='min-h-11 px-3 text-muted-foreground !whitespace-normal'
                            disabled={
                              !onDefer ||
                              saving ||
                              deferring ||
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
                    ) : null}
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
                ) : null}
              </>
            )}
          </footer>
        </DialogContent>
      </Dialog>
    </>
  );
}
