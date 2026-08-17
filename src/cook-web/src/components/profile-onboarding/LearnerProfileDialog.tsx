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

const PROFILE_PROMPTS = [
  { key: 'identity', Icon: UserRound },
  { key: 'goals', Icon: BriefcaseBusiness },
  { key: 'teaching', Icon: Target },
] as const;

type DialogView = 'research' | 'optimizing' | 'review';
type DialogConfirmation = 'discard' | 'replace-research';
type OptimizationStatus = 'idle' | 'success' | 'error';
type ResearchTriggerSource = 'guided' | 'settings';

export type LearnerProfileDialogProps = {
  open: boolean;
  mode: 'onboarding' | 'settings';
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
  mode,
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
  const [view, setView] = React.useState<DialogView>('review');
  const [researchJourney, setResearchJourney] = React.useState(false);
  const [researchIntent, setResearchIntent] =
    React.useState<ProfileOnboardingSessionIntent>('onboarding');
  const [researchTriggerSource, setResearchTriggerSource] =
    React.useState<ResearchTriggerSource | null>(null);
  const [researchSessionId, setResearchSessionId] = React.useState('');
  const [researchDraft, setResearchDraft] = React.useState('');
  const [researchError, setResearchError] = React.useState('');
  const [researchKey, setResearchKey] = React.useState(0);
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
  const [preferredResearchIntent, setPreferredResearchIntent] =
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
  const researchJourneyRef = React.useRef(0);
  const researchCompletionRef = React.useRef(false);
  const researchShownAtRef = React.useRef<number | null>(null);
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

  const beginResearch = React.useCallback(
    (
      intent: ProfileOnboardingSessionIntent,
      rerun: boolean,
      journeyPresentation = presentationRef.current,
    ) => {
      const journey = ++researchJourneyRef.current;
      researchCompletionRef.current = false;
      researchShownAtRef.current = Date.now();
      optimizeRequestRef.current += 1;
      setOptimizing(false);
      setResearchIntent(intent);
      setResearchTriggerSource(intent === 'settings' ? 'settings' : 'guided');
      setResearchSessionId('');
      setResearchDraft('');
      setResearchError('');
      setResearchJourney(true);
      setResearchKey(journey);
      setView('research');
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
          setPreferredResearchIntent('settings');
          setManualFallback(false);
          setResearchJourney(false);
          setView('review');
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
        const nextResearchIntent: ProfileOnboardingSessionIntent =
          nextHasCanonicalProfile || validOnboardingStatus?.handled
            ? 'settings'
            : 'onboarding';
        setGuidedAvailable(nextGuidedAvailable);
        setPreferredResearchIntent(nextResearchIntent);

        if (!nextHasCanonicalProfile) {
          setManualFallback(!nextGuidedAvailable);
          setLoaded(true);
          if (nextGuidedAvailable) {
            beginResearch(
              nextResearchIntent,
              false,
              validOnboardingStatus?.presentation ?? presentationRef.current,
            );
          } else {
            setResearchJourney(false);
            setView('review');
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
    [beginResearch, isCurrent, resetOptimization],
  );

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      loadRequestRef.current += 1;
      optimizeRequestRef.current += 1;
      researchJourneyRef.current += 1;
    };
  }, []);

  React.useEffect(() => {
    const generation = ++generationRef.current;
    loadRequestRef.current += 1;
    optimizeRequestRef.current += 1;
    researchJourneyRef.current += 1;
    researchCompletionRef.current = false;
    researchShownAtRef.current = null;
    setConfirmation(null);
    setResearchJourney(false);
    setResearchSessionId('');
    setResearchDraft('');
    setResearchError('');
    setGuidedAvailable(false);
    setManualFallback(false);
    setError('');
    setOptimizing(false);
    resetOptimization();

    if (!open) {
      return;
    }

    const scope = draftStorageScope;
    setView('review');
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
      researchJourneyRef.current += 1;
    };
  }, [draftStorageScope, loadProfile, open, resetOptimization]);

  React.useLayoutEffect(() => {
    if (mode === 'onboarding' && confirmation === 'discard') {
      setConfirmation(null);
    }
  }, [confirmation, mode]);

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
  }, [confirmation, loaded, view]);

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
  const canCompleteOnboarding =
    mode === 'onboarding' && Boolean(normalizedProfile || normalizedNickname);
  const canSave =
    loaded &&
    view === 'review' &&
    !busy &&
    !optimizing &&
    profileLength <= maxLength &&
    !nicknameOverLimit &&
    (dirty ||
      hasUnsavedPrefill ||
      nicknameNeedsMigration ||
      Boolean(researchSessionId && normalizedProfile) ||
      canCompleteOnboarding);

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
      setResearchSessionId('');
      setResearchDraft('');
      setResearchTriggerSource(null);
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
      let guidedSave = false;
      let response: Awaited<ReturnType<typeof updateLearnerProfile>>;
      if (researchSessionId && researchTriggerSource) {
        guidedSave = true;
        response = await completeGuidedProfileOnboarding({
          learner_profile: normalizedProfile,
          trigger_source: researchTriggerSource,
          session_id: researchSessionId,
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
      if (guidedSave) {
        const shownAt = researchShownAtRef.current;
        void trackEvent(PROFILE_ONBOARDING_EVENTS.COMPLETED, {
          source: researchTriggerSource,
          presentation,
          ...(shownAt === null ? {} : { duration_ms: Date.now() - shownAt }),
        });
      } else if (mode === 'settings') {
        void trackEvent(
          normalizedProfile
            ? PROFILE_ONBOARDING_EVENTS.SETTINGS_SAVED
            : PROFILE_ONBOARDING_EVENTS.SETTINGS_CLEARED,
        );
      }
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
    applyProfileResponse,
    canSave,
    draftStorageScope,
    initialNickname,
    isCurrent,
    loaded,
    maxLength,
    mode,
    nicknameNeedsMigration,
    nicknameOverLimit,
    normalizedNickname,
    normalizedProfile,
    onClose,
    optimizing,
    presentation,
    profileLength,
    researchSessionId,
    researchTriggerSource,
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
    if (mode === 'onboarding' || saving || dismissing || deferring) {
      return;
    }
    if (dirty) {
      setConfirmation('discard');
      return;
    }
    void dismiss();
  }, [deferring, dirty, dismiss, dismissing, mode, saving]);

  const performOptimization = React.useCallback(
    async (draft: string, automatic: boolean) => {
      const normalized = draft.trim();
      if (
        !loaded ||
        optimizing ||
        !normalized ||
        countUnicodeCodePoints(normalized) > maxLength
      ) {
        if (automatic) {
          setProfile(draft);
          setView('review');
        }
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
        setView('optimizing');
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
            setView('review');
          }
        }
      }
    },
    [draftStorageScope, isCurrent, loaded, maxLength, optimizing, t],
  );

  const optimizeProfile = React.useCallback(() => {
    void performOptimization(profile, false);
  }, [performOptimization, profile]);

  const useResearchDraft = React.useCallback(() => {
    if (!researchDraft) {
      return;
    }
    setProfile(researchDraft);
    setOptimizationStatus('idle');
    setOptimizationErrorMessage('');
    setOptimizationOriginal(researchDraft);
    setError('');
    textareaRef.current?.focus();
  }, [researchDraft]);

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

  const createResearchSession = React.useCallback(
    () =>
      createProfileOnboardingSession(
        i18n.resolvedLanguage ?? i18n.language,
        researchIntent,
      ),
    [i18n.language, i18n.resolvedLanguage, researchIntent],
  );

  const runResearchSession = React.useCallback(
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

  const handleDraftReady = React.useCallback(
    (
      draft: string,
      sessionId: string,
      journey: number,
      generation: number,
      scope: string,
    ) => {
      if (
        journey !== researchJourneyRef.current ||
        !isCurrent(generation, scope) ||
        researchCompletionRef.current
      ) {
        return;
      }
      researchCompletionRef.current = true;
      setResearchDraft(draft);
      setResearchSessionId(sessionId);
      setResearchError('');
      setProfile(draft);
      void performOptimization(draft, true);
    },
    [isCurrent, performOptimization],
  );

  const cancelResearch = React.useCallback(() => {
    researchJourneyRef.current += 1;
    optimizeRequestRef.current += 1;
    researchCompletionRef.current = false;
    setOptimizing(false);
    setResearchJourney(false);
    setResearchSessionId('');
    setResearchDraft('');
    setResearchError('');
    setResearchTriggerSource(null);
    setView('review');
    resetOptimization();
  }, [resetOptimization]);

  const requestResearch = React.useCallback(() => {
    if (busy || optimizing || !guidedAvailable) {
      return;
    }
    if (dirty) {
      setConfirmation('replace-research');
      return;
    }
    beginResearch(preferredResearchIntent, true);
  }, [
    beginResearch,
    busy,
    dirty,
    guidedAvailable,
    optimizing,
    preferredResearchIntent,
  ]);

  const deferOnboarding = React.useCallback(async () => {
    if (
      mode !== 'onboarding' ||
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
      const result = await onDefer(researchSessionId || undefined);
      if (result === false || !isCurrent(generation, scope)) {
        return;
      }
      optimizeRequestRef.current += 1;
      researchJourneyRef.current += 1;
      setOptimizing(false);
      void trackEvent(PROFILE_ONBOARDING_EVENTS.SKIPPED, {
        source: researchTriggerSource ?? 'guided',
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
    mode,
    onClose,
    onDefer,
    presentation,
    researchSessionId,
    researchTriggerSource,
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
  const showResearchOptimizationActions = Boolean(researchDraft);
  const optimizationDescription = !normalizedProfile
    ? t('module.profileOnboarding.dialog.optimizeEmptyHint')
    : optimizationStatus === 'error'
      ? optimizationErrorMessage ||
        t('module.profileOnboarding.dialog.optimizeFailed')
      : optimizationStatus === 'success'
        ? t('module.profileOnboarding.dialog.optimizeSuccess')
        : t('module.profileOnboarding.dialog.optimizeHint');
  const combinedResearchError = researchError || externalErrorMessage;
  const combinedDialogError =
    error || (view === 'research' ? '' : externalErrorMessage);
  const currentStep = view === 'research' ? 1 : 2;
  const renderedGeneration = generationRef.current;
  const renderedScope = draftStorageScope;
  const primaryLabel =
    mode === 'onboarding'
      ? t('module.profileOnboarding.complete')
      : t('module.profileOnboarding.dialog.saveChanges');

  const renderReview = () => (
    <div className='space-y-5 sm:space-y-4'>
      <div>
        <h2
          ref={viewHeadingRef}
          tabIndex={-1}
          className='text-xl font-semibold leading-7 outline-none'
        >
          {t('module.profileOnboarding.dialog.confirmTitle')}
        </h2>
        <p className='mt-1 text-sm leading-6 text-muted-foreground'>
          {t('module.profileOnboarding.dialog.confirmDescription')}
        </p>
      </div>

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
            <div
              key={key}
              data-testid={`learner-profile-guidance-${key}`}
              className='flex min-h-16 items-start gap-2 rounded-xl border border-primary/15 bg-primary/[0.05] px-3 py-2.5 text-left text-primary'
            >
              <Icon
                className='mt-0.5 size-4 shrink-0'
                aria-hidden='true'
              />
              <span className='min-w-0'>
                <span className='block text-sm font-semibold leading-5'>
                  {t(`module.profileOnboarding.dialog.chips.${key}.label`)}
                </span>
                <span className='mt-0.5 block text-xs font-normal leading-4 text-muted-foreground'>
                  {t(`module.profileOnboarding.dialog.chips.${key}.hint`)}
                </span>
              </span>
            </div>
          ))}
        </div>

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
              className='min-w-0 flex-1 text-sm leading-5 text-foreground/80'
            >
              {optimizationDescription}
            </p>
            <div className='flex flex-wrap gap-2'>
              {showResearchOptimizationActions ? (
                <Button
                  type='button'
                  size='sm'
                  variant='outline'
                  className='min-h-10 flex-1 sm:flex-none'
                  disabled={busy || optimizing}
                  onClick={useResearchDraft}
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
                    : showResearchOptimizationActions
                      ? 'module.profileOnboarding.dialog.retryOptimize'
                      : 'module.profileOnboarding.dialog.optimize',
                )}
              </Button>
            </div>
          </div>
        </div>
      </section>

      {guidedAvailable ? (
        <Button
          type='button'
          variant='outline'
          className='min-h-11 w-full sm:w-auto'
          disabled={busy || optimizing}
          onClick={requestResearch}
        >
          {t('module.profileOnboarding.settings.rerun')}
        </Button>
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
          data-view={view}
          showClose={false}
          overlayClassName='!bg-slate-950/45 backdrop-blur-[1px]'
          onEscapeKeyDown={event => {
            if (mode === 'onboarding') {
              event.preventDefault();
            }
          }}
          onPointerDownOutside={event => {
            if (mode === 'onboarding') {
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
            <DialogHeader className='w-full space-y-2 pr-12 text-left'>
              <DialogTitle className='text-2xl font-bold leading-8 tracking-tight [@media(max-height:620px)]:text-xl [@media(max-height:620px)]:leading-7 sm:text-[28px] sm:leading-9'>
                {t('module.profileOnboarding.dialog.unifiedTitle')}
              </DialogTitle>
              <DialogDescription className='max-w-2xl text-left text-sm leading-6 [@media(max-height:620px)]:hidden sm:text-base'>
                {t('module.profileOnboarding.dialog.unifiedDescription')}
              </DialogDescription>
            </DialogHeader>
            {mode === 'settings' ? (
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

            {researchJourney ? (
              <ol
                className='mt-4 grid grid-cols-2 gap-2 [@media(max-height:620px)]:mt-2'
                aria-label={t('module.profileOnboarding.dialog.progressLabel')}
              >
                {(['collect', 'review'] as const).map((step, index) => {
                  const stepNumber = index + 1;
                  const active = currentStep === stepNumber;
                  const complete = currentStep > stepNumber;
                  return (
                    <li
                      key={step}
                      aria-current={active ? 'step' : undefined}
                      className={cn(
                        'rounded-lg border px-3 py-2 text-xs font-medium [@media(max-height:620px)]:py-1.5 sm:text-sm',
                        active && 'border-primary bg-primary/10 text-primary',
                        complete && 'border-primary/30 text-foreground',
                        !active &&
                          !complete &&
                          'border-border text-muted-foreground',
                      )}
                    >
                      {t(`module.profileOnboarding.steps.${step}`)}
                    </li>
                  );
                })}
              </ol>
            ) : null}
          </header>

          <div
            ref={contentScrollRef}
            data-testid='learner-profile-dialog-body'
            className={cn(
              'min-h-0 flex-1 overscroll-contain px-5 py-5 [scrollbar-gutter:stable] [@media(max-height:620px)]:py-3 sm:px-8 sm:py-6',
              view === 'research' && !confirmation
                ? 'overflow-hidden'
                : 'overflow-y-auto',
            )}
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
            ) : view === 'research' ? (
              <section className='flex h-full min-h-0 flex-col'>
                <div className='mb-4 shrink-0 [@media(max-height:620px)]:mb-2'>
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
                <div className='min-h-0 flex-1'>
                  <ProfileOnboardingConversation
                    key={researchKey}
                    createSession={createResearchSession}
                    runSession={runResearchSession}
                    disabled={busy}
                    errorMessage={combinedResearchError}
                    onSessionStarted={sessionId => {
                      if (
                        researchKey === researchJourneyRef.current &&
                        isCurrent(renderedGeneration, renderedScope)
                      ) {
                        setResearchSessionId(sessionId);
                      }
                    }}
                    onDraftReady={(draft, sessionId) =>
                      handleDraftReady(
                        draft,
                        sessionId,
                        researchKey,
                        renderedGeneration,
                        renderedScope,
                      )
                    }
                    onRetry={() => {
                      if (
                        researchKey === researchJourneyRef.current &&
                        isCurrent(renderedGeneration, renderedScope)
                      ) {
                        setResearchError('');
                      }
                    }}
                    onError={caughtError => {
                      if (
                        researchKey !== researchJourneyRef.current ||
                        !isCurrent(renderedGeneration, renderedScope)
                      ) {
                        return;
                      }
                      void trackEvent(
                        PROFILE_ONBOARDING_EVENTS.RUNTIME_FAILED,
                        { stage: 'guided', presentation },
                      );
                      setResearchError(
                        errorMessage(
                          caughtError,
                          t('module.profileOnboarding.guided.streamError'),
                        ),
                      );
                    }}
                  />
                </div>
              </section>
            ) : view === 'optimizing' ? (
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
              renderReview()
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
            className='flex shrink-0 items-center gap-2.5 border-t bg-background px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 sm:justify-end sm:gap-3 sm:px-8 sm:py-4'
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
                      beginResearch(preferredResearchIntent, true);
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
            ) : mode === 'onboarding' ? (
              <Button
                type='button'
                variant='ghost'
                className='mr-auto min-h-11 px-3 text-muted-foreground !whitespace-normal'
                disabled={!onDefer || saving || deferring || externalSubmitting}
                onClick={() => void deferOnboarding()}
              >
                {deferring || externalSubmitting
                  ? t('module.profileOnboarding.skipping')
                  : t('module.profileOnboarding.skip')}
              </Button>
            ) : view === 'research' ? (
              <Button
                type='button'
                variant='outline'
                className='min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                disabled={busy}
                onClick={cancelResearch}
              >
                {t('module.profileOnboarding.dialog.cancelResearch')}
              </Button>
            ) : (
              <Button
                type='button'
                variant='outline'
                className='min-h-11 min-w-0 flex-1 !whitespace-normal sm:flex-none'
                disabled={busy}
                onClick={requestClose}
              >
                {t('module.profileOnboarding.dialog.cancel')}
              </Button>
            )}

            {!confirmation && view === 'review' ? (
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
            ) : null}
          </footer>
        </DialogContent>
      </Dialog>
    </>
  );
}
