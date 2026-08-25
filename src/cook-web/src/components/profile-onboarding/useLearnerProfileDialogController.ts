import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  completeGuidedProfileOnboarding,
  createProfileOnboardingSession,
  getLearnerProfile,
  getProfileOnboarding,
  isProfileOnboardingV2Status,
  optimizeLearnerProfile,
  runProfileOnboardingSession,
  updateLearnerProfile,
  type ProfileOnboardingSessionIntent,
} from '@/api/learnerProfile';
import { useTracking } from '@/c-common/hooks/useTracking';
import { useToast } from '@/hooks/useToast';
import { PROFILE_ONBOARDING_EVENTS } from './events';
import {
  DEFAULT_NICKNAME_MAX_LENGTH,
  DEFAULT_PROFILE_MAX_LENGTH,
  initialLearnerProfileDialogState,
  learnerProfileDialogReducer,
  selectLearnerProfileDialog,
  type LearnerProfileDialogProps,
  type ProfileCollectionResult,
} from './learnerProfileDialogModel';
import {
  buildLearnerProfileDraft,
  resolveLearnerNicknameDraft,
} from './learnerProfileDraft';
import { countUnicodeCodePoints } from './ProfileDraftEditor';
import type { ProfileOnboardingConversationProps } from './ProfileOnboardingConversation';

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error && error.message ? error.message : fallback;

type RequestEpochs = {
  dialog: number;
  load: number;
  optimize: number;
  collection: number;
};

export const useLearnerProfileDialogController = ({
  open,
  exitPolicy,
  draftStorageScope,
  autoStartCollection = false,
  presentation = 'hidden',
  initialOnboardingStatus,
  externalErrorMessage = '',
  externalSubmitting = false,
  onDefer,
  onClose,
  onSaved,
}: LearnerProfileDialogProps) => {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [state, dispatch] = React.useReducer(
    learnerProfileDialogReducer,
    initialLearnerProfileDialogState,
  );
  const stateRef = React.useRef(state);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const mountedRef = React.useRef(false);
  const openRef = React.useRef(open);
  const scopeRef = React.useRef(draftStorageScope);
  const presentationRef = React.useRef(presentation);
  const autoStartCollectionRef = React.useRef(autoStartCollection);
  const initialOnboardingStatusRef = React.useRef(initialOnboardingStatus);
  const translationRef = React.useRef(t);
  const requestEpochRef = React.useRef<RequestEpochs>({
    dialog: 0,
    load: 0,
    optimize: 0,
    collection: 0,
  });
  const collectionCompletionRef = React.useRef(false);
  const collectionShownAtRef = React.useRef<number | null>(null);
  const autoCollectionStartedRef = React.useRef(false);

  stateRef.current = state;
  openRef.current = open;
  scopeRef.current = draftStorageScope;
  presentationRef.current = presentation;
  autoStartCollectionRef.current = autoStartCollection;
  initialOnboardingStatusRef.current = initialOnboardingStatus;
  translationRef.current = t;

  const bumpEpoch = React.useCallback((kind: keyof RequestEpochs) => {
    requestEpochRef.current[kind] += 1;
    return requestEpochRef.current[kind];
  }, []);

  const invalidateAsyncWork = React.useCallback(() => {
    bumpEpoch('load');
    bumpEpoch('optimize');
    bumpEpoch('collection');
  }, [bumpEpoch]);

  const isCurrent = React.useCallback((dialog: number, scope: string) => {
    return (
      mountedRef.current &&
      openRef.current &&
      requestEpochRef.current.dialog === dialog &&
      scopeRef.current === scope
    );
  }, []);

  const resetOptimization = React.useCallback(() => {
    dispatch({ type: 'reset_optimization' });
  }, []);

  const setError = React.useCallback((error: string) => {
    dispatch({ type: 'patch', patch: { error } });
  }, []);

  const setProfile = React.useCallback((profile: string) => {
    dispatch({ type: 'patch_form', patch: { profile } });
  }, []);

  const setNickname = React.useCallback((nickname: string) => {
    dispatch({ type: 'patch_form', patch: { nickname } });
  }, []);

  const setConfirmation = React.useCallback(
    (confirmation: 'discard' | 'replace-collection' | null) => {
      dispatch({
        type: 'patch',
        patch: { confirmation: confirmation ?? 'none' },
      });
    },
    [],
  );

  const beginCollection = React.useCallback(
    (
      intent: ProfileOnboardingSessionIntent,
      rerun: boolean,
      journeyPresentation = presentationRef.current,
    ) => {
      const journey = bumpEpoch('collection');
      collectionCompletionRef.current = false;
      collectionShownAtRef.current = Date.now();
      bumpEpoch('optimize');
      dispatch({
        type: 'patch',
        patch: {
          phase: 'collect',
          collectionStatus: 'starting',
          collectionRunInFlight: false,
          collectionIntent: intent,
          activeCollectionSessionId: '',
          collectionError: '',
          collectionKey: journey,
          optimizationStatus: 'idle',
          optimizationErrorMessage: '',
          optimizationOriginal: null,
        },
      });
      if (rerun) {
        void trackEvent(PROFILE_ONBOARDING_EVENTS.SETTINGS_RERUN_STARTED);
      }
      void trackEvent(PROFILE_ONBOARDING_EVENTS.SHOWN, {
        source: intent === 'settings' ? 'settings' : 'guided',
        presentation: journeyPresentation,
        has_profile: stateRef.current.hasCanonicalProfile,
      });
    },
    [bumpEpoch, trackEvent],
  );

  const loadProfile = React.useCallback(
    async (dialog: number, scope: string): Promise<boolean> => {
      const request = bumpEpoch('load');
      dispatch({
        type: 'patch',
        patch: { loadStatus: 'loading', error: '' },
      });
      try {
        const openingOnboardingStatus = initialOnboardingStatusRef.current;
        const onboardingStatusRequest = openingOnboardingStatus
          ? Promise.resolve(openingOnboardingStatus)
          : getProfileOnboarding().catch(() => null);
        const response = await getLearnerProfile();
        if (
          !isCurrent(dialog, scope) ||
          request !== requestEpochRef.current.load
        ) {
          return false;
        }

        const hasCanonicalProfile = Boolean(response.has_learner_profile);
        const profile = buildLearnerProfileDraft(
          response,
          translationRef.current,
        );
        const nickname = resolveLearnerNicknameDraft(response);
        dispatch({
          type: 'patch_form',
          patch: {
            profile,
            initialProfile: profile,
            savedProfile: response.learner_profile || '',
            nickname: nickname.value,
            initialNickname: nickname.value,
            savedNickname: nickname.savedValue,
            nicknameSource: nickname.source,
            maxLength: response.max_length || DEFAULT_PROFILE_MAX_LENGTH,
            nicknameMaxLength:
              response.nickname_max_length || DEFAULT_NICKNAME_MAX_LENGTH,
          },
        });
        dispatch({
          type: 'patch',
          patch: { hasCanonicalProfile },
        });
        resetOptimization();

        if (hasCanonicalProfile) {
          dispatch({
            type: 'patch',
            patch: {
              preferredCollectionIntent: 'settings',
              manualFallback: false,
              phase: 'save',
              loadStatus: 'ready',
            },
          });
        }

        const onboardingStatus = await onboardingStatusRequest;
        if (
          !isCurrent(dialog, scope) ||
          request !== requestEpochRef.current.load
        ) {
          return false;
        }
        const validOnboardingStatus = isProfileOnboardingV2Status(
          onboardingStatus,
        )
          ? onboardingStatus
          : null;
        const guidedAvailable = Boolean(
          validOnboardingStatus?.enabled &&
          validOnboardingStatus.guided_available,
        );
        const collectionIntent: ProfileOnboardingSessionIntent =
          hasCanonicalProfile || validOnboardingStatus?.handled
            ? 'settings'
            : 'onboarding';
        dispatch({
          type: 'patch',
          patch: {
            guidedAvailable,
            preferredCollectionIntent: collectionIntent,
          },
        });

        if (!hasCanonicalProfile) {
          dispatch({
            type: 'patch',
            patch: {
              manualFallback: !guidedAvailable,
              loadStatus: 'ready',
            },
          });
          if (
            guidedAvailable &&
            autoStartCollectionRef.current &&
            !autoCollectionStartedRef.current
          ) {
            autoCollectionStartedRef.current = true;
            beginCollection(
              collectionIntent,
              false,
              validOnboardingStatus?.presentation ?? presentationRef.current,
            );
          } else {
            dispatch({ type: 'patch', patch: { phase: 'save' } });
          }
        }
        return true;
      } catch (caughtError) {
        if (
          isCurrent(dialog, scope) &&
          request === requestEpochRef.current.load
        ) {
          dispatch({
            type: 'patch',
            patch: {
              loadStatus: 'error',
              error: errorMessage(
                caughtError,
                translationRef.current(
                  'module.profileOnboarding.dialog.loadFailed',
                ),
              ),
            },
          });
        }
        return false;
      }
    },
    [beginCollection, bumpEpoch, isCurrent, resetOptimization],
  );

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      bumpEpoch('dialog');
      invalidateAsyncWork();
    };
  }, [bumpEpoch, invalidateAsyncWork]);

  React.useEffect(() => {
    const dialog = bumpEpoch('dialog');
    invalidateAsyncWork();
    collectionCompletionRef.current = false;
    collectionShownAtRef.current = null;
    autoCollectionStartedRef.current = false;
    dispatch({
      type: 'reset',
      state: { loadStatus: open ? 'loading' : 'closed' },
    });
    if (!open) {
      return;
    }
    void loadProfile(dialog, draftStorageScope);
    return invalidateAsyncWork;
  }, [bumpEpoch, draftStorageScope, invalidateAsyncWork, loadProfile, open]);

  const derived = selectLearnerProfileDialog(
    state,
    exitPolicy,
    externalSubmitting,
  );

  React.useEffect(() => {
    if (
      !open ||
      !autoStartCollection ||
      autoCollectionStartedRef.current ||
      !derived.loaded ||
      state.hasCanonicalProfile ||
      !state.guidedAvailable
    ) {
      return;
    }
    autoCollectionStartedRef.current = true;
    beginCollection(state.preferredCollectionIntent, false);
  }, [
    autoStartCollection,
    beginCollection,
    derived.loaded,
    open,
    state.guidedAvailable,
    state.hasCanonicalProfile,
    state.preferredCollectionIntent,
  ]);

  React.useLayoutEffect(() => {
    if (exitPolicy === 'blocking' && state.confirmation === 'discard') {
      setConfirmation(null);
    }
  }, [exitPolicy, setConfirmation, state.confirmation]);

  const runOnSaved = React.useCallback(
    async (dialog: number, scope: string) => {
      try {
        await onSaved?.();
      } catch {
        if (isCurrent(dialog, scope)) {
          toast({ title: t('module.profileOnboarding.refreshPending') });
        }
      }
    },
    [isCurrent, onSaved, t, toast],
  );

  const applyProfileResponse = React.useCallback(
    (response: Awaited<ReturnType<typeof updateLearnerProfile>>) => {
      const profile = buildLearnerProfileDraft(
        response,
        translationRef.current,
      );
      const nickname = resolveLearnerNicknameDraft(response);
      dispatch({
        type: 'patch_form',
        patch: {
          profile,
          initialProfile: profile,
          savedProfile: response.learner_profile || '',
          nickname: nickname.value,
          initialNickname: nickname.value,
          savedNickname: nickname.savedValue,
          nicknameSource: nickname.source,
          maxLength: response.max_length || stateRef.current.form.maxLength,
          nicknameMaxLength:
            response.nickname_max_length ||
            stateRef.current.form.nicknameMaxLength,
        },
      });
      dispatch({
        type: 'patch',
        patch: {
          hasCanonicalProfile: Boolean(response.has_learner_profile),
          activeCollectionSessionId: '',
          collectionResult: null,
          collectionStatus: 'starting',
          optimizationStatus: 'idle',
          optimizationErrorMessage: '',
          optimizationOriginal: null,
        },
      });
    },
    [],
  );

  const saveProfile = React.useCallback(async () => {
    const current = stateRef.current;
    const values = selectLearnerProfileDialog(
      current,
      exitPolicy,
      externalSubmitting,
    );
    if (!values.loaded || !values.canSave || values.optimizing) {
      return;
    }
    if (
      values.profileLength > current.form.maxLength ||
      values.nicknameOverLimit
    ) {
      textareaRef.current?.focus();
      return;
    }

    const dialog = requestEpochRef.current.dialog;
    const scope = draftStorageScope;
    const nicknameChanged =
      values.normalizedNickname !== current.form.initialNickname;
    dispatch({
      type: 'patch',
      patch: { submissionStatus: 'saving', error: '' },
    });
    try {
      const nicknamePayload =
        nicknameChanged || values.nicknameNeedsMigration
          ? { nickname: values.normalizedNickname }
          : {};
      const completion = current.collectionResult?.completion;
      const response = completion
        ? await completeGuidedProfileOnboarding({
            learner_profile: values.normalizedProfile,
            trigger_source: completion.triggerSource,
            session_id: completion.sessionId,
            ...nicknamePayload,
          })
        : await updateLearnerProfile(
            values.normalizedProfile,
            nicknameChanged || values.nicknameNeedsMigration
              ? values.normalizedNickname
              : undefined,
          );
      if (!isCurrent(dialog, scope)) {
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
          values.normalizedProfile
            ? PROFILE_ONBOARDING_EVENTS.SETTINGS_SAVED
            : PROFILE_ONBOARDING_EVENTS.SETTINGS_CLEARED,
        );
      }
      await onClose('saved');
      void runOnSaved(dialog, scope);
    } catch (caughtError) {
      if (isCurrent(dialog, scope)) {
        setError(
          errorMessage(
            caughtError,
            t('module.profileOnboarding.dialog.saveFailed'),
          ),
        );
      }
    } finally {
      if (isCurrent(dialog, scope)) {
        dispatch({ type: 'patch', patch: { submissionStatus: 'idle' } });
      }
    }
  }, [
    applyProfileResponse,
    draftStorageScope,
    exitPolicy,
    externalSubmitting,
    isCurrent,
    onClose,
    presentation,
    runOnSaved,
    setError,
    t,
    trackEvent,
  ]);

  const dismiss = React.useCallback(async () => {
    const current = stateRef.current;
    if (current.submissionStatus !== 'idle') {
      return;
    }
    const dialog = requestEpochRef.current.dialog;
    const scope = draftStorageScope;
    bumpEpoch('optimize');
    dispatch({
      type: 'patch',
      patch: { submissionStatus: 'dismissing', error: '' },
    });
    try {
      await onClose('dismiss');
    } catch (caughtError) {
      if (isCurrent(dialog, scope)) {
        setError(
          errorMessage(
            caughtError,
            t('module.profileOnboarding.dialog.dismissFailed'),
          ),
        );
      }
    } finally {
      if (isCurrent(dialog, scope)) {
        dispatch({ type: 'patch', patch: { submissionStatus: 'idle' } });
      }
    }
  }, [bumpEpoch, draftStorageScope, isCurrent, onClose, setError, t]);

  const requestClose = React.useCallback(() => {
    const values = selectLearnerProfileDialog(
      stateRef.current,
      exitPolicy,
      externalSubmitting,
    );
    if (exitPolicy === 'blocking' || values.busy) {
      return;
    }
    if (values.dirty) {
      setConfirmation('discard');
      return;
    }
    void dismiss();
  }, [dismiss, exitPolicy, externalSubmitting, setConfirmation]);

  const performOptimization = React.useCallback(
    async (draft: string) => {
      const current = stateRef.current;
      const normalized = draft.trim();
      if (
        current.loadStatus !== 'ready' ||
        current.optimizationStatus === 'running' ||
        !normalized ||
        countUnicodeCodePoints(normalized) > current.form.maxLength
      ) {
        return;
      }
      const request = bumpEpoch('optimize');
      const dialog = requestEpochRef.current.dialog;
      const scope = draftStorageScope;
      dispatch({
        type: 'patch',
        patch: {
          optimizationStatus: 'running',
          optimizationErrorMessage: '',
          optimizationOriginal: draft,
          error: '',
        },
      });
      try {
        const response = await optimizeLearnerProfile(normalized);
        if (
          !isCurrent(dialog, scope) ||
          request !== requestEpochRef.current.optimize
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
        dispatch({ type: 'patch_form', patch: { profile: optimized } });
        dispatch({
          type: 'patch',
          patch: { optimizationStatus: 'success' },
        });
      } catch (caughtError) {
        if (
          isCurrent(dialog, scope) &&
          request === requestEpochRef.current.optimize
        ) {
          dispatch({ type: 'patch_form', patch: { profile: draft } });
          dispatch({
            type: 'patch',
            patch: {
              optimizationStatus: 'error',
              optimizationErrorMessage: errorMessage(
                caughtError,
                t('module.profileOnboarding.dialog.optimizeFailed'),
              ),
            },
          });
        }
      }
    },
    [bumpEpoch, draftStorageScope, isCurrent, t],
  );

  const optimizeProfile = React.useCallback(() => {
    void performOptimization(stateRef.current.form.profile);
  }, [performOptimization]);

  const undoOptimization = React.useCallback(() => {
    const original = stateRef.current.optimizationOriginal;
    if (original === null) {
      return;
    }
    dispatch({ type: 'patch_form', patch: { profile: original } });
    resetOptimization();
    setError('');
    textareaRef.current?.focus();
  }, [resetOptimization, setError]);

  const retryLoad = React.useCallback(() => {
    void loadProfile(requestEpochRef.current.dialog, draftStorageScope);
  }, [draftStorageScope, loadProfile]);

  const createCollectionSession = React.useCallback(
    () =>
      createProfileOnboardingSession(
        i18n.resolvedLanguage ?? i18n.language,
        stateRef.current.collectionIntent,
      ),
    [i18n.language, i18n.resolvedLanguage],
  );

  const runCollectionSession = React.useCallback<
    ProfileOnboardingConversationProps['runSession']
  >(
    ({
      sessionId,
      expectedBlockIndex,
      requestId,
      userInput,
      onMessage,
      onError,
    }) =>
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
    (result: ProfileCollectionResult, collection: number) => {
      if (
        collection !== requestEpochRef.current.collection ||
        !isCurrent(requestEpochRef.current.dialog, scopeRef.current) ||
        collectionCompletionRef.current
      ) {
        return;
      }
      collectionCompletionRef.current = true;
      dispatch({
        type: 'patch',
        patch: {
          collectionResult: result,
          activeCollectionSessionId: result.completion.sessionId,
          collectionError: '',
          collectionStatus: 'ready',
          collectionRunInFlight: false,
          optimizationStatus: 'idle',
          optimizationErrorMessage: '',
          optimizationOriginal: null,
        },
      });
      dispatch({
        type: 'patch_form',
        patch: {
          profile: result.draft,
          ...(result.nickname === undefined
            ? {}
            : { nickname: result.nickname }),
        },
      });
    },
    [isCurrent],
  );

  const handleSessionStarted = React.useCallback((sessionId: string) => {
    if (stateRef.current.collectionKey !== requestEpochRef.current.collection) {
      return;
    }
    dispatch({
      type: 'patch',
      patch: {
        activeCollectionSessionId: sessionId,
        collectionStatus: 'running',
      },
    });
  }, []);

  const handleCollectionRunInFlightChange = React.useCallback(
    (runInFlight: boolean) => {
      if (stateRef.current.phase !== 'collect') {
        return;
      }
      dispatch({
        type: 'patch',
        patch: { collectionRunInFlight: runInFlight },
      });
    },
    [],
  );

  const handleCollectionDraftReady = React.useCallback(
    (draft: string, sessionId: string, nickname?: string) => {
      const current = stateRef.current;
      acceptCollectionResult(
        {
          draft,
          ...(nickname ? { nickname } : {}),
          completion: {
            triggerSource:
              current.collectionIntent === 'settings' ? 'settings' : 'guided',
            sessionId,
          },
        },
        current.collectionKey,
      );
    },
    [acceptCollectionResult],
  );

  const handleCollectionRetry = React.useCallback(() => {
    if (stateRef.current.collectionKey !== requestEpochRef.current.collection) {
      return;
    }
    dispatch({
      type: 'patch',
      patch: { collectionError: '', collectionStatus: 'running' },
    });
  }, []);

  const handleCollectionError = React.useCallback(
    (caughtError: unknown) => {
      if (
        stateRef.current.collectionKey !== requestEpochRef.current.collection
      ) {
        return;
      }
      void trackEvent(PROFILE_ONBOARDING_EVENTS.RUNTIME_FAILED, {
        stage: 'guided',
        presentation: presentationRef.current,
      });
      dispatch({
        type: 'patch',
        patch: {
          collectionError: errorMessage(
            caughtError,
            translationRef.current(
              'module.profileOnboarding.guided.streamError',
            ),
          ),
          collectionStatus: 'retryable_error',
          collectionRunInFlight: false,
        },
      });
    },
    [trackEvent],
  );

  const continueToSave = React.useCallback(() => {
    const current = stateRef.current;
    const values = selectLearnerProfileDialog(
      current,
      exitPolicy,
      externalSubmitting,
    );
    if (
      current.collectionStatus !== 'ready' ||
      !current.collectionResult ||
      values.busy
    ) {
      return;
    }
    dispatch({
      type: 'patch',
      patch: {
        collectionStatus: 'starting',
        collectionRunInFlight: false,
        phase: 'save',
      },
    });
  }, [exitPolicy, externalSubmitting]);

  const cancelCollection = React.useCallback(() => {
    bumpEpoch('collection');
    bumpEpoch('optimize');
    collectionCompletionRef.current = false;
    const completion = stateRef.current.collectionResult?.completion;
    dispatch({
      type: 'patch',
      patch: {
        activeCollectionSessionId: completion?.sessionId ?? '',
        collectionError: '',
        collectionStatus: 'starting',
        collectionRunInFlight: false,
        phase: 'save',
        optimizationStatus: 'idle',
        optimizationErrorMessage: '',
        optimizationOriginal: null,
      },
    });
  }, [bumpEpoch]);

  const requestCollection = React.useCallback(() => {
    const current = stateRef.current;
    const values = selectLearnerProfileDialog(
      current,
      exitPolicy,
      externalSubmitting,
    );
    if (values.busy || values.optimizing || !current.guidedAvailable) {
      return;
    }
    if (values.dirty) {
      setConfirmation('replace-collection');
      return;
    }
    beginCollection(current.preferredCollectionIntent, true);
  }, [beginCollection, exitPolicy, externalSubmitting, setConfirmation]);

  const deferOnboarding = React.useCallback(async () => {
    const current = stateRef.current;
    if (
      exitPolicy !== 'blocking' ||
      !onDefer ||
      current.submissionStatus !== 'idle' ||
      current.collectionRunInFlight ||
      externalSubmitting
    ) {
      return;
    }
    const dialog = requestEpochRef.current.dialog;
    const scope = draftStorageScope;
    dispatch({
      type: 'patch',
      patch: { submissionStatus: 'deferring', error: '' },
    });
    try {
      const result = await onDefer(
        current.activeCollectionSessionId || undefined,
      );
      if (result === false || !isCurrent(dialog, scope)) {
        return;
      }
      bumpEpoch('optimize');
      bumpEpoch('collection');
      void trackEvent(PROFILE_ONBOARDING_EVENTS.SKIPPED, {
        source:
          current.collectionResult?.completion.triggerSource ??
          (current.collectionIntent === 'settings' ? 'settings' : 'guided'),
        presentation,
      });
      await onClose('dismiss');
    } catch (caughtError) {
      if (isCurrent(dialog, scope)) {
        setError(
          errorMessage(
            caughtError,
            t('module.profileOnboarding.dialog.dismissFailed'),
          ),
        );
      }
    } finally {
      if (isCurrent(dialog, scope)) {
        dispatch({ type: 'patch', patch: { submissionStatus: 'idle' } });
      }
    }
  }, [
    bumpEpoch,
    draftStorageScope,
    exitPolicy,
    externalSubmitting,
    isCurrent,
    onClose,
    onDefer,
    presentation,
    setError,
    t,
    trackEvent,
  ]);

  const confirmPendingAction = React.useCallback(() => {
    const confirmation = stateRef.current.confirmation;
    setConfirmation(null);
    if (confirmation === 'discard') {
      void dismiss();
    } else if (confirmation === 'replace-collection') {
      beginCollection(stateRef.current.preferredCollectionIntent, true);
    }
  }, [beginCollection, dismiss, setConfirmation]);

  const optimizeDisabled =
    !derived.loaded ||
    derived.busy ||
    derived.optimizing ||
    !derived.normalizedProfile ||
    derived.profileLength > state.form.maxLength;
  const optimizationDescription = !derived.normalizedProfile
    ? t('module.profileOnboarding.dialog.optimizeEmptyHint')
    : state.optimizationStatus === 'error'
      ? state.optimizationErrorMessage ||
        t('module.profileOnboarding.dialog.optimizeFailed')
      : state.optimizationStatus === 'success'
        ? t('module.profileOnboarding.dialog.optimizeSuccess')
        : t('module.profileOnboarding.dialog.optimizeHint');
  const combinedCollectionError = state.collectionError || externalErrorMessage;
  const combinedDialogError =
    state.error || (state.phase === 'collect' ? '' : externalErrorMessage);
  const primaryLabel =
    state.hasCanonicalProfile && !state.collectionResult
      ? t('module.profileOnboarding.dialog.saveChanges')
      : t('module.profileOnboarding.complete');

  return {
    state,
    derived,
    textareaRef,
    collectionReady: state.collectionStatus === 'ready',
    confirmation: state.confirmation === 'none' ? null : state.confirmation,
    optimizeDisabled,
    optimizationDescription,
    combinedCollectionError,
    combinedDialogError,
    primaryLabel,
    conversationProps: {
      createSession: createCollectionSession,
      runSession: runCollectionSession,
      disabled: derived.busy,
      errorMessage: combinedCollectionError,
      onSessionStarted: handleSessionStarted,
      onRunInFlightChange: handleCollectionRunInFlightChange,
      onDraftReady: handleCollectionDraftReady,
      onRetry: handleCollectionRetry,
      onError: handleCollectionError,
    } satisfies ProfileOnboardingConversationProps,
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
  };
};
