import type {
  ProfileOnboardingSessionIntent,
  ProfileOnboardingV2Status,
  ProfileOnboardingPresentation,
} from '@/api/learnerProfile';
import { countUnicodeCodePoints } from './ProfileDraftEditor';
import type { LearnerNicknameSource } from './learnerProfileDraft';

export const DEFAULT_PROFILE_MAX_LENGTH = 1000;
export const DEFAULT_NICKNAME_MAX_LENGTH = 64;

export type LearnerProfileDialogPhase = 'collect' | 'save';
export type LearnerProfileDialogLoadStatus =
  | 'closed'
  | 'loading'
  | 'ready'
  | 'error';
export type LearnerProfileCollectionStatus =
  | 'starting'
  | 'running'
  | 'ready'
  | 'retryable_error';
export type LearnerProfileOptimizationStatus =
  | 'idle'
  | 'running'
  | 'success'
  | 'error';
export type LearnerProfileSubmissionStatus =
  | 'idle'
  | 'saving'
  | 'dismissing'
  | 'deferring';
export type LearnerProfileDialogConfirmation =
  | 'none'
  | 'discard'
  | 'replace-collection';
export type CollectionTriggerSource = 'guided' | 'settings';

export type ProfileCollectionResult = {
  draft: string;
  nickname?: string;
  completion: {
    triggerSource: CollectionTriggerSource;
    sessionId: string;
  };
};

export type LearnerProfileDialogProps = {
  open: boolean;
  exitPolicy: 'blocking' | 'dismissible';
  draftStorageScope: string;
  autoStartCollection?: boolean;
  presentation?: ProfileOnboardingPresentation;
  initialOnboardingStatus?: ProfileOnboardingV2Status;
  externalErrorMessage?: string;
  externalSubmitting?: boolean;
  onDefer?: (sessionId?: string) => boolean | void | Promise<boolean | void>;
  onClose: (reason: 'dismiss' | 'saved') => void | Promise<void>;
  onSaved?: () => void | Promise<void>;
};

export type LearnerProfileFormSnapshot = {
  profile: string;
  initialProfile: string;
  savedProfile: string;
  nickname: string;
  initialNickname: string;
  savedNickname?: string;
  nicknameSource: LearnerNicknameSource;
  maxLength: number;
  nicknameMaxLength: number;
};

export type LearnerProfileDialogState = {
  loadStatus: LearnerProfileDialogLoadStatus;
  phase: LearnerProfileDialogPhase;
  collectionStatus: LearnerProfileCollectionStatus;
  collectionRunInFlight: boolean;
  collectionIntent: ProfileOnboardingSessionIntent;
  activeCollectionSessionId: string;
  collectionResult: ProfileCollectionResult | null;
  collectionError: string;
  collectionKey: number;
  form: LearnerProfileFormSnapshot;
  hasCanonicalProfile: boolean;
  guidedAvailable: boolean;
  preferredCollectionIntent: ProfileOnboardingSessionIntent;
  manualFallback: boolean;
  optimizationStatus: LearnerProfileOptimizationStatus;
  optimizationErrorMessage: string;
  optimizationOriginal: string | null;
  submissionStatus: LearnerProfileSubmissionStatus;
  confirmation: LearnerProfileDialogConfirmation;
  error: string;
};

export const initialLearnerProfileDialogState: LearnerProfileDialogState = {
  loadStatus: 'closed',
  phase: 'save',
  collectionStatus: 'starting',
  collectionRunInFlight: false,
  collectionIntent: 'onboarding',
  activeCollectionSessionId: '',
  collectionResult: null,
  collectionError: '',
  collectionKey: 0,
  form: {
    profile: '',
    initialProfile: '',
    savedProfile: '',
    nickname: '',
    initialNickname: '',
    savedNickname: undefined,
    nicknameSource: 'unavailable',
    maxLength: DEFAULT_PROFILE_MAX_LENGTH,
    nicknameMaxLength: DEFAULT_NICKNAME_MAX_LENGTH,
  },
  hasCanonicalProfile: false,
  guidedAvailable: false,
  preferredCollectionIntent: 'onboarding',
  manualFallback: false,
  optimizationStatus: 'idle',
  optimizationErrorMessage: '',
  optimizationOriginal: null,
  submissionStatus: 'idle',
  confirmation: 'none',
  error: '',
};

export type LearnerProfileDialogAction =
  | {
      type: 'reset';
      state?: Partial<LearnerProfileDialogState>;
    }
  | {
      type: 'patch';
      patch: Partial<LearnerProfileDialogState>;
    }
  | {
      type: 'patch_form';
      patch: Partial<LearnerProfileFormSnapshot>;
    }
  | { type: 'reset_optimization' };

export const learnerProfileDialogReducer = (
  state: LearnerProfileDialogState,
  action: LearnerProfileDialogAction,
): LearnerProfileDialogState => {
  switch (action.type) {
    case 'reset':
      return {
        ...initialLearnerProfileDialogState,
        ...action.state,
        form: {
          ...initialLearnerProfileDialogState.form,
          ...action.state?.form,
        },
      };
    case 'patch':
      return { ...state, ...action.patch };
    case 'patch_form':
      return { ...state, form: { ...state.form, ...action.patch } };
    case 'reset_optimization':
      return {
        ...state,
        optimizationStatus: 'idle',
        optimizationErrorMessage: '',
        optimizationOriginal: null,
      };
  }
};

export const selectLearnerProfileDialog = (
  state: LearnerProfileDialogState,
  exitPolicy: LearnerProfileDialogProps['exitPolicy'],
  externalSubmitting: boolean,
) => {
  const normalizedProfile = state.form.profile.trim();
  const normalizedNickname = state.form.nickname.trim();
  const loaded = state.loadStatus === 'ready';
  const loading = state.loadStatus === 'loading';
  const optimizing = state.optimizationStatus === 'running';
  const saving = state.submissionStatus === 'saving';
  const dismissing = state.submissionStatus === 'dismissing';
  const deferring = state.submissionStatus === 'deferring';
  const busy = state.submissionStatus !== 'idle' || externalSubmitting;
  const dirty =
    loaded &&
    (normalizedProfile !== state.form.initialProfile ||
      normalizedNickname !== state.form.initialNickname);
  const profileLength = countUnicodeCodePoints(normalizedProfile);
  const nicknameLength = countUnicodeCodePoints(normalizedNickname);
  const hasUnsavedPrefill = normalizedProfile !== state.form.savedProfile;
  const nicknameNeedsMigration =
    state.form.nicknameSource === 'legacy-migration' &&
    normalizedNickname === state.form.initialNickname &&
    normalizedNickname !== state.form.savedNickname;
  const nicknameWillBeSaved =
    normalizedNickname !== state.form.initialNickname || nicknameNeedsMigration;
  const nicknameOverLimit =
    nicknameWillBeSaved && nicknameLength > state.form.nicknameMaxLength;
  const canCompleteBlocking =
    exitPolicy === 'blocking' &&
    Boolean(normalizedProfile || normalizedNickname);
  const canSave =
    loaded &&
    state.phase === 'save' &&
    !busy &&
    !optimizing &&
    profileLength <= state.form.maxLength &&
    !nicknameOverLimit &&
    (dirty ||
      hasUnsavedPrefill ||
      nicknameNeedsMigration ||
      Boolean(state.collectionResult && normalizedProfile) ||
      canCompleteBlocking);

  return {
    normalizedProfile,
    normalizedNickname,
    loaded,
    loading,
    optimizing,
    saving,
    dismissing,
    deferring,
    busy,
    dirty,
    profileLength,
    nicknameLength,
    nicknameNeedsMigration,
    nicknameOverLimit,
    canSave,
  };
};
