import React from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useTracking } from '@/c-common/hooks/useTracking';
import type {
  ProfileOnboardingRunSession,
  ProfileOnboardingSessionInfo,
} from '@/components/profile-onboarding/ProfileOnboardingConversation';
import { useToast } from '@/hooks/useToast';
import { streamProfileOnboardingRuntime } from '@/lib/profileOnboardingSse';
import type { ErrorWithCode } from '@/lib/request';

type ProfileOnboardingConfig = {
  enabled?: boolean;
  markdownflow?: string;
  assistant_prompt?: string;
  assistant_prompts?: Record<string, string>;
  cache_refresh_pending?: boolean;
  config_revision?: number;
  updated_by?: string;
  updated_at?: string;
};

type ProfileOnboardingDraft = {
  enabled: boolean;
  markdownflow: string;
  assistantPrompt: string;
};

type NormalizedProfileOnboardingConfig = {
  draft: ProfileOnboardingDraft;
  revision: number;
  updatedBy: string;
  updatedAt: string;
};

type GenerateAssistantPromptResponse = {
  assistant_prompt?: string;
};

type GenerateMode = 'generate' | 'regenerate';
type GenerateOutcome = 'success' | 'failed' | 'superseded';
type SaveOutcome = 'failed' | 'saved' | 'saved_with_newer_edits';
type DirtyNavigationDecision = 'cancel' | 'discard' | 'save_and_leave';
type DirtyNavigationSaveOutcome = 'success' | 'failed' | 'superseded';

export const PROFILE_PROMPT_GENERATE_ATTEMPT_EVENT =
  'operator_profile_prompt_generate_attempt';
export const PROFILE_PROMPT_GENERATE_RESULT_EVENT =
  'operator_profile_prompt_generate_result';
export const PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT =
  'operator_profile_dirty_navigation_shown';
export const PROFILE_DIRTY_NAVIGATION_DECISION_EVENT =
  'operator_profile_dirty_navigation_decision';
export const PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT =
  'operator_profile_dirty_navigation_save_result';

const EMPTY_DRAFT: ProfileOnboardingDraft = {
  enabled: false,
  markdownflow: '',
  assistantPrompt: '',
};

const normalizeProfileOnboardingConfig = (
  response: ProfileOnboardingConfig,
  defaultMarkdownflow: string,
): NormalizedProfileOnboardingConfig => {
  const revision = Number(response.config_revision ?? 0);
  const hasStoredConfiguration = revision > 0;
  return {
    draft: {
      enabled: Boolean(response.enabled),
      markdownflow: hasStoredConfiguration
        ? (response.markdownflow ?? defaultMarkdownflow)
        : response.markdownflow || defaultMarkdownflow,
      assistantPrompt: response.assistant_prompt || '',
    },
    revision,
    updatedBy: response.updated_by || '',
    updatedAt: response.updated_at || '',
  };
};

const draftsMatch = (
  left: ProfileOnboardingDraft,
  right: ProfileOnboardingDraft,
) =>
  left.enabled === right.enabled &&
  left.markdownflow === right.markdownflow &&
  left.assistantPrompt === right.assistantPrompt;

export const useProfileOnboardingAdminController = (isReady: boolean) => {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const [enabled, setEnabledState] = React.useState(false);
  const [markdownflow, setMarkdownflowState] = React.useState('');
  const [assistantPrompt, setAssistantPromptState] = React.useState('');
  const [savedConfig, setSavedConfig] =
    React.useState<ProfileOnboardingDraft>(EMPTY_DRAFT);
  const [configRevision, setConfigRevision] = React.useState(0);
  const [updatedBy, setUpdatedBy] = React.useState('');
  const [updatedAt, setUpdatedAt] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [configLoaded, setConfigLoaded] = React.useState(false);
  const [loadFailed, setLoadFailed] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [generating, setGenerating] = React.useState(false);
  const [error, setError] = React.useState('');
  const [generationNotice, setGenerationNotice] = React.useState('');
  const [documentChanged, setDocumentChanged] = React.useState(false);
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [previewKey, setPreviewKey] = React.useState(0);
  const [previewDraft, setPreviewDraft] = React.useState('');
  const [pendingNavigation, setPendingNavigation] = React.useState<
    string | null
  >(null);
  const [navigationStatus, setNavigationStatus] = React.useState('');
  const loadStartedRef = React.useRef(false);
  const savingRef = React.useRef(false);
  const generatingRef = React.useRef(false);
  const enabledRef = React.useRef(false);
  const markdownflowRef = React.useRef('');
  const assistantPromptRef = React.useRef('');
  const promptDocumentRef = React.useRef('');
  const pendingNavigationRef = React.useRef<string | null>(null);
  const dirtyNavigationShownRef = React.useRef(false);
  const defaultMarkdownflow = t(
    'module.profileOnboarding.admin.defaultMarkdownflow',
  );

  const currentDraft = React.useMemo(
    () => ({ enabled, markdownflow, assistantPrompt }),
    [assistantPrompt, enabled, markdownflow],
  );
  const isDirty = configLoaded && !draftsMatch(currentDraft, savedConfig);

  const setEnabled = React.useCallback((value: boolean) => {
    enabledRef.current = value;
    setEnabledState(value);
  }, []);

  const setMarkdownflow = React.useCallback((value: string) => {
    markdownflowRef.current = value;
    setMarkdownflowState(value);
    setGenerationNotice('');
    setDocumentChanged(
      Boolean(assistantPromptRef.current.trim()) &&
        value !== promptDocumentRef.current,
    );
  }, []);

  const setAssistantPrompt = React.useCallback((value: string) => {
    assistantPromptRef.current = value;
    setAssistantPromptState(value);
    promptDocumentRef.current = markdownflowRef.current;
    setDocumentChanged(false);
    setGenerationNotice('');
  }, []);

  const applyDraft = React.useCallback((draft: ProfileOnboardingDraft) => {
    enabledRef.current = draft.enabled;
    markdownflowRef.current = draft.markdownflow;
    assistantPromptRef.current = draft.assistantPrompt;
    promptDocumentRef.current = draft.markdownflow;
    setEnabledState(draft.enabled);
    setMarkdownflowState(draft.markdownflow);
    setAssistantPromptState(draft.assistantPrompt);
    setDocumentChanged(false);
    setGenerationNotice('');
  }, []);

  const loadConfig = React.useCallback(async () => {
    if (!isReady || loadStartedRef.current) {
      return;
    }
    loadStartedRef.current = true;
    setLoading(true);
    setConfigLoaded(false);
    setLoadFailed(false);
    setError('');
    try {
      const response = (await api.getAdminOperationProfileOnboardingConfig(
        {},
      )) as ProfileOnboardingConfig;
      const loaded = normalizeProfileOnboardingConfig(
        response,
        defaultMarkdownflow,
      );
      applyDraft(loaded.draft);
      setSavedConfig(loaded.draft);
      setConfigRevision(loaded.revision);
      setUpdatedBy(loaded.updatedBy);
      setUpdatedAt(loaded.updatedAt);
      setConfigLoaded(true);
    } catch {
      setLoadFailed(true);
      setError(t('module.profileOnboarding.admin.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [applyDraft, defaultMarkdownflow, isReady, t]);

  React.useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const reload = React.useCallback(() => {
    loadStartedRef.current = false;
    void loadConfig();
  }, [loadConfig]);

  const trackEventSafely = React.useCallback(
    (eventName: string, payload: Record<string, unknown>) => {
      try {
        void Promise.resolve(trackEvent(eventName, payload)).catch(
          () => undefined,
        );
      } catch {
        // Analytics is best-effort and must not affect the operator action.
      }
    },
    [trackEvent],
  );

  const trackGenerationResult = React.useCallback(
    (mode: GenerateMode, outcome: GenerateOutcome) => {
      trackEventSafely(PROFILE_PROMPT_GENERATE_RESULT_EVENT, {
        mode,
        outcome,
      });
    },
    [trackEventSafely],
  );

  const trackDirtyNavigationDecision = React.useCallback(
    (decision: DirtyNavigationDecision) => {
      trackEventSafely(PROFILE_DIRTY_NAVIGATION_DECISION_EVENT, { decision });
    },
    [trackEventSafely],
  );

  const trackDirtyNavigationSaveResult = React.useCallback(
    (outcome: DirtyNavigationSaveOutcome) => {
      trackEventSafely(PROFILE_DIRTY_NAVIGATION_SAVE_RESULT_EVENT, { outcome });
    },
    [trackEventSafely],
  );

  const refreshSavedBaselineAfterConflict = React.useCallback(
    async (submittedRevision: number) => {
      try {
        const response = (await api.getAdminOperationProfileOnboardingConfig(
          {},
          { skipErrorToast: true },
        )) as ProfileOnboardingConfig;
        const latest = normalizeProfileOnboardingConfig(
          response,
          defaultMarkdownflow,
        );
        if (
          !Number.isInteger(latest.revision) ||
          latest.revision <= submittedRevision
        ) {
          throw new Error(
            'The refreshed configuration revision did not advance.',
          );
        }
        setSavedConfig(latest.draft);
        setConfigRevision(latest.revision);
        setUpdatedBy(latest.updatedBy);
        setUpdatedAt(latest.updatedAt);
        setError(t('module.profileOnboarding.admin.configConflictRecovered'));
      } catch {
        setError(
          t('module.profileOnboarding.admin.configConflictRefreshFailed'),
        );
      }
    },
    [defaultMarkdownflow, t],
  );

  const generateAssistantPrompt = React.useCallback(async () => {
    if (
      !configLoaded ||
      loadFailed ||
      generatingRef.current ||
      savingRef.current
    ) {
      return;
    }
    const submittedMarkdownflow = markdownflowRef.current;
    const submittedAssistantPrompt = assistantPromptRef.current;
    if (!submittedMarkdownflow.trim()) {
      setError(t('module.profileOnboarding.admin.generateRequiresDocument'));
      return;
    }
    const mode: GenerateMode = submittedAssistantPrompt.trim()
      ? 'regenerate'
      : 'generate';
    generatingRef.current = true;
    setGenerating(true);
    setError('');
    setGenerationNotice('');
    trackEventSafely(PROFILE_PROMPT_GENERATE_ATTEMPT_EVENT, { mode });
    try {
      const response =
        (await api.generateAdminOperationProfileOnboardingAssistantPrompt({
          markdownflow: submittedMarkdownflow,
        })) as GenerateAssistantPromptResponse;
      const generatedPrompt = response.assistant_prompt;
      if (typeof generatedPrompt !== 'string' || !generatedPrompt.trim()) {
        throw new Error('The generated assistant prompt was empty.');
      }
      if (
        markdownflowRef.current !== submittedMarkdownflow ||
        assistantPromptRef.current !== submittedAssistantPrompt
      ) {
        setGenerationNotice(
          t('module.profileOnboarding.admin.generationSuperseded'),
        );
        trackGenerationResult(mode, 'superseded');
        return;
      }
      assistantPromptRef.current = generatedPrompt;
      promptDocumentRef.current = submittedMarkdownflow;
      setAssistantPromptState(generatedPrompt);
      setDocumentChanged(false);
      setGenerationNotice(t('module.profileOnboarding.admin.generateSuccess'));
      trackGenerationResult(mode, 'success');
    } catch {
      setError(t('module.profileOnboarding.admin.generateFailed'));
      trackGenerationResult(mode, 'failed');
    } finally {
      generatingRef.current = false;
      setGenerating(false);
    }
  }, [configLoaded, loadFailed, t, trackEventSafely, trackGenerationResult]);

  const save = React.useCallback(async (): Promise<SaveOutcome> => {
    if (
      !configLoaded ||
      loadFailed ||
      savingRef.current ||
      generatingRef.current
    ) {
      return 'failed';
    }
    const submittedConfig = {
      enabled: enabledRef.current,
      markdownflow: markdownflowRef.current,
      assistantPrompt: assistantPromptRef.current,
    };
    if (
      !submittedConfig.markdownflow.trim() &&
      submittedConfig.assistantPrompt.trim()
    ) {
      setError(t('module.profileOnboarding.admin.promptRequiresDocument'));
      return 'failed';
    }
    if (submittedConfig.enabled && !submittedConfig.markdownflow.trim()) {
      setError(t('module.profileOnboarding.admin.documentRequired'));
      return 'failed';
    }
    if (submittedConfig.enabled && !submittedConfig.assistantPrompt.trim()) {
      setError(t('module.profileOnboarding.admin.assistantPromptRequired'));
      return 'failed';
    }
    const submittedRevision = configRevision;
    savingRef.current = true;
    setSaving(true);
    setError('');
    try {
      const response = (await api.updateAdminOperationProfileOnboardingConfig(
        {
          enabled: submittedConfig.enabled,
          markdownflow: submittedConfig.markdownflow,
          assistant_prompt: submittedConfig.assistantPrompt,
          config_revision: submittedRevision,
        },
        { skipErrorToast: true },
      )) as ProfileOnboardingConfig;
      const savedDraft = {
        enabled: response.enabled ?? submittedConfig.enabled,
        markdownflow: response.markdownflow ?? submittedConfig.markdownflow,
        assistantPrompt:
          response.assistant_prompt ?? submittedConfig.assistantPrompt,
      };
      setSavedConfig(savedDraft);
      if (enabledRef.current === submittedConfig.enabled) {
        enabledRef.current = savedDraft.enabled;
        setEnabledState(savedDraft.enabled);
      }
      if (markdownflowRef.current === submittedConfig.markdownflow) {
        markdownflowRef.current = savedDraft.markdownflow;
        setMarkdownflowState(savedDraft.markdownflow);
      }
      if (assistantPromptRef.current === submittedConfig.assistantPrompt) {
        assistantPromptRef.current = savedDraft.assistantPrompt;
        setAssistantPromptState(savedDraft.assistantPrompt);
      }
      setConfigRevision(Number(response.config_revision ?? submittedRevision));
      setUpdatedBy(response.updated_by || updatedBy);
      setUpdatedAt(response.updated_at || updatedAt);
      if (response.cache_refresh_pending) {
        toast({
          title: t('module.profileOnboarding.admin.saveCacheRefreshPending'),
          className: 'border-amber-300 bg-amber-50 text-amber-950',
          duration: 8000,
        });
      } else {
        toast({ title: t('module.profileOnboarding.admin.saveSuccess') });
      }
      const hasNoNewerEdits = draftsMatch(
        {
          enabled: enabledRef.current,
          markdownflow: markdownflowRef.current,
          assistantPrompt: assistantPromptRef.current,
        },
        savedDraft,
      );
      return hasNoNewerEdits ? 'saved' : 'saved_with_newer_edits';
    } catch (caughtError) {
      const typedError = caughtError as Partial<ErrorWithCode>;
      if (typedError.code === 4015) {
        await refreshSavedBaselineAfterConflict(submittedRevision);
        return 'failed';
      }
      setError(
        typedError.message || t('module.profileOnboarding.admin.saveFailed'),
      );
      return 'failed';
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }, [
    configLoaded,
    configRevision,
    loadFailed,
    refreshSavedBaselineAfterConflict,
    t,
    toast,
    updatedAt,
    updatedBy,
  ]);

  React.useEffect(() => {
    if (!isDirty) {
      return undefined;
    }
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  React.useEffect(() => {
    const isShown = Boolean(pendingNavigation);
    if (isShown && !dirtyNavigationShownRef.current) {
      trackEventSafely(PROFILE_DIRTY_NAVIGATION_SHOWN_EVENT, {});
    }
    dirtyNavigationShownRef.current = isShown;
  }, [pendingNavigation, trackEventSafely]);

  React.useEffect(() => {
    if (!isDirty) {
      return undefined;
    }
    const handleDocumentClick = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      const target = event.target as Element | null;
      const anchor = target?.closest<HTMLAnchorElement>('a[href]');
      if (
        !anchor ||
        anchor.target === '_blank' ||
        anchor.hasAttribute('download')
      ) {
        return;
      }
      const href = anchor.getAttribute('href') || '';
      if (!href || href.startsWith('#')) {
        return;
      }
      const nextUrl = new URL(href, window.location.href);
      if (nextUrl.origin !== window.location.origin) {
        return;
      }
      const nextPath = `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`;
      const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      if (nextPath === currentPath) {
        return;
      }
      event.preventDefault();
      if (savingRef.current) {
        return;
      }
      setError('');
      setNavigationStatus('');
      pendingNavigationRef.current = nextPath;
      setPendingNavigation(nextPath);
    };
    document.addEventListener('click', handleDocumentClick, true);
    return () =>
      document.removeEventListener('click', handleDocumentClick, true);
  }, [isDirty]);

  const discardPendingChanges = React.useCallback(() => {
    const target = pendingNavigationRef.current;
    if (!target || savingRef.current) {
      return;
    }
    trackDirtyNavigationDecision('discard');
    pendingNavigationRef.current = null;
    applyDraft(savedConfig);
    setError('');
    setNavigationStatus('');
    setPendingNavigation(null);
    router.push(target, { scroll: false });
  }, [applyDraft, router, savedConfig, trackDirtyNavigationDecision]);

  const dismissPendingNavigation = React.useCallback(() => {
    if (!pendingNavigationRef.current || savingRef.current) {
      return;
    }
    trackDirtyNavigationDecision('cancel');
    pendingNavigationRef.current = null;
    setNavigationStatus('');
    setPendingNavigation(null);
  }, [trackDirtyNavigationDecision]);

  const saveAndProceed = React.useCallback(async () => {
    const target = pendingNavigationRef.current;
    if (!target || savingRef.current) {
      return;
    }
    trackDirtyNavigationDecision('save_and_leave');
    setNavigationStatus('');
    const saveOutcome = await save();
    if (saveOutcome === 'saved_with_newer_edits') {
      trackDirtyNavigationSaveResult('superseded');
      setNavigationStatus(
        t('module.profileOnboarding.admin.unsavedDialog.newerEditsAfterSave'),
      );
      return;
    }
    if (saveOutcome !== 'saved') {
      trackDirtyNavigationSaveResult('failed');
      return;
    }
    trackDirtyNavigationSaveResult('success');
    pendingNavigationRef.current = null;
    setNavigationStatus('');
    setPendingNavigation(null);
    router.push(target, { scroll: false });
  }, [
    router,
    save,
    t,
    trackDirtyNavigationDecision,
    trackDirtyNavigationSaveResult,
  ]);

  const createPreviewSession = React.useCallback(async () => {
    setPreviewDraft('');
    setError('');
    return (await api.createAdminOperationProfileOnboardingPreview({
      markdownflow: markdownflowRef.current,
      language: i18n.resolvedLanguage ?? i18n.language,
    })) as ProfileOnboardingSessionInfo;
  }, [i18n.language, i18n.resolvedLanguage]);

  const runPreviewSession = React.useCallback<ProfileOnboardingRunSession>(
    ({
      sessionId,
      expectedBlockIndex,
      requestId,
      userInput,
      onMessage,
      onError,
    }) =>
      streamProfileOnboardingRuntime({
        path: `/api/shifu/admin/operations/profile-onboarding/preview/${encodeURIComponent(sessionId)}/run`,
        payload: {
          expected_block_index: expectedBlockIndex,
          request_id: requestId,
          ...(userInput ? { user_input: userInput } : {}),
        },
        language: i18n.resolvedLanguage ?? i18n.language,
        onMessage,
        onError,
      }),
    [i18n.language, i18n.resolvedLanguage],
  );

  const startPreview = React.useCallback(() => {
    if (
      !configLoaded ||
      loadFailed ||
      savingRef.current ||
      generatingRef.current
    ) {
      return;
    }
    setPreviewDraft('');
    setPreviewOpen(true);
    setPreviewKey(key => key + 1);
  }, [configLoaded, loadFailed]);

  const handlePreviewError = React.useCallback(
    (caughtError: unknown) => {
      setError(
        caughtError instanceof Error && caughtError.message
          ? caughtError.message
          : t('module.profileOnboarding.admin.previewFailed'),
      );
    },
    [t],
  );

  return {
    enabled,
    setEnabled,
    markdownflow,
    setMarkdownflow,
    assistantPrompt,
    setAssistantPrompt,
    configRevision,
    updatedBy,
    updatedAt,
    loading,
    configLoaded,
    loadFailed,
    reload,
    saving,
    generating,
    error,
    generationNotice,
    documentChanged,
    isDirty,
    pendingNavigation,
    navigationStatus,
    dismissPendingNavigation,
    discardPendingChanges,
    saveAndProceed,
    previewOpen,
    previewKey,
    previewDraft,
    setPreviewDraft,
    generateAssistantPrompt,
    save,
    startPreview,
    hidePreview: () => setPreviewOpen(false),
    previewConversationProps: {
      createSession: createPreviewSession,
      runSession: runPreviewSession,
      onDraftReady: setPreviewDraft,
      onRetry: () => setError(''),
      onError: handlePreviewError,
    },
  };
};
