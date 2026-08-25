import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getProfileOnboarding,
  isProfileOnboardingStatus,
  skipProfileOnboarding,
  type ProfileOnboardingStatus,
} from '@/c-api/user';
import type { LearnerProfileDialogProps } from '@/components/profile-onboarding/LearnerProfileDialog';
import { debugWarn } from '@/c-utils/debugConsole';
import { toast } from '@/hooks/useToast';
import {
  resolveLearnerErrorMessage,
  resolveLearnerErrorToast,
} from '@/lib/learnerError';
import type { ErrorWithCode } from '@/lib/request';
import { useUserStore } from '@/store';

type ProfileOnboardingEligibility = 'idle' | 'pending' | 'show' | 'complete';

export const PROFILE_ONBOARDING_ELIGIBILITY_TIMEOUT_MS = 10_000;

type UseCourseProfileOnboardingGateParams = {
  initialized: boolean;
  isLoggedIn: boolean;
  previewMode: boolean;
  courseName: string;
  learnerProfileScope: string;
  refreshUserInfo: () => Promise<unknown>;
};

export const useCourseProfileOnboardingGate = ({
  initialized,
  isLoggedIn,
  previewMode,
  courseName,
  learnerProfileScope,
  refreshUserInfo,
}: UseCourseProfileOnboardingGateParams) => {
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [autoStartCollection, setAutoStartCollection] = useState(false);
  const [status, setStatus] = useState<ProfileOnboardingStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [readyScope, setReadyScope] = useState<string | null>(null);
  const scopeRef = useRef(learnerProfileScope);
  const statusRef = useRef(status);
  const requestedScopeRef = useRef<string | null>(null);
  const requestIdRef = useRef(0);
  const eligibilityRef = useRef<ProfileOnboardingEligibility>('idle');
  scopeRef.current = learnerProfileScope;
  statusRef.current = status;

  const runtimeReady =
    initialized &&
    (!isLoggedIn || previewMode || readyScope === learnerProfileScope);

  const release = useCallback(() => {
    eligibilityRef.current = 'complete';
    setStatus(null);
    setDialogOpen(false);
    setAutoStartCollection(false);
    setError('');
    setReadyScope(learnerProfileScope);
  }, [learnerProfileScope]);

  const resolveSubmitError = useCallback(
    (caughtError: unknown) =>
      resolveLearnerErrorMessage({
        error: caughtError as Partial<ErrorWithCode>,
        fallbackMessage: t('module.profileOnboarding.submitFailed'),
      }),
    [t],
  );

  const notifyLoadFailure = useCallback(
    (caughtError: unknown) => {
      const resolvedToast = resolveLearnerErrorToast({
        error: caughtError as Partial<ErrorWithCode>,
        fallbackMessage: t('module.profileOnboarding.loadFailed'),
      });
      toast({
        title: resolvedToast.message,
        variant: resolvedToast.variant,
      });
    },
    [t],
  );
  const notifyLoadFailureRef = useRef(notifyLoadFailure);
  notifyLoadFailureRef.current = notifyLoadFailure;

  const notifyRefreshDelay = useCallback(() => {
    toast({ title: t('module.profileOnboarding.refreshPending') });
  }, [t]);

  useEffect(() => {
    requestedScopeRef.current = null;
    requestIdRef.current += 1;
    eligibilityRef.current = 'idle';
    setDialogOpen(false);
    setAutoStartCollection(false);
    setStatus(null);
    setSubmitting(false);
    setError('');
    setReadyScope(null);
  }, [initialized, isLoggedIn, learnerProfileScope, previewMode]);

  useEffect(() => {
    if (!initialized) {
      eligibilityRef.current = 'idle';
      setReadyScope(null);
      return;
    }
    if (!isLoggedIn || previewMode) {
      eligibilityRef.current = 'complete';
      return;
    }
    if (!courseName || requestedScopeRef.current === learnerProfileScope) {
      return;
    }

    const token = useUserStore.getState().getToken?.();
    if (!token) {
      eligibilityRef.current = 'complete';
      setReadyScope(learnerProfileScope);
      return;
    }

    eligibilityRef.current = 'pending';
    setReadyScope(null);
    requestedScopeRef.current = learnerProfileScope;
    const requestId = ++requestIdRef.current;
    let requestSettled = false;
    const failOpen = (caughtError: unknown) => {
      if (
        requestSettled ||
        requestId !== requestIdRef.current ||
        scopeRef.current !== learnerProfileScope
      ) {
        return;
      }
      requestSettled = true;
      debugWarn('[profile-onboarding] failed to load status', caughtError);
      notifyLoadFailureRef.current(caughtError);
      eligibilityRef.current = 'complete';
      setReadyScope(learnerProfileScope);
    };
    const timeoutId = window.setTimeout(
      () => failOpen(new Error()),
      PROFILE_ONBOARDING_ELIGIBILITY_TIMEOUT_MS,
    );
    void getProfileOnboarding()
      .then(nextStatus => {
        if (
          requestSettled ||
          requestId !== requestIdRef.current ||
          scopeRef.current !== learnerProfileScope
        ) {
          return;
        }
        requestSettled = true;
        window.clearTimeout(timeoutId);
        if (!isProfileOnboardingStatus(nextStatus)) {
          debugWarn('[profile-onboarding] incompatible status response');
          eligibilityRef.current = 'complete';
          setReadyScope(learnerProfileScope);
          return;
        }
        if (
          !nextStatus.enabled ||
          !nextStatus.guided_available ||
          !nextStatus.should_show ||
          nextStatus.presentation === 'hidden'
        ) {
          eligibilityRef.current = 'complete';
          setReadyScope(learnerProfileScope);
          return;
        }
        if (nextStatus.presentation === 'blocking') {
          eligibilityRef.current = 'show';
          setStatus(nextStatus);
          setError('');
          setAutoStartCollection(true);
          setDialogOpen(true);
          return;
        }
        eligibilityRef.current = 'complete';
        setReadyScope(learnerProfileScope);
      })
      .catch(failOpen);

    return () => {
      requestSettled = true;
      window.clearTimeout(timeoutId);
    };
  }, [courseName, initialized, isLoggedIn, learnerProfileScope, previewMode]);

  const defer = useCallback(
    async (sessionId?: string) => {
      const requestScope = learnerProfileScope;
      setSubmitting(true);
      setError('');
      try {
        await skipProfileOnboarding(sessionId);
        if (scopeRef.current !== requestScope) {
          return false;
        }
        eligibilityRef.current = 'complete';
        return true;
      } catch (caughtError) {
        if (scopeRef.current === requestScope) {
          setError(resolveSubmitError(caughtError));
        }
        return false;
      } finally {
        if (scopeRef.current === requestScope) {
          setSubmitting(false);
        }
      }
    },
    [learnerProfileScope, resolveSubmitError],
  );

  const closeDialog = useCallback(
    (reason: 'dismiss' | 'saved') => {
      const eligibility = eligibilityRef.current;
      const currentStatus = statusRef.current;
      if (
        reason === 'dismiss' &&
        eligibility === 'show' &&
        currentStatus?.presentation === 'blocking'
      ) {
        return;
      }
      if (reason === 'saved' || (currentStatus && eligibility !== 'show')) {
        release();
        return;
      }
      setDialogOpen(false);
      setAutoStartCollection(false);
    },
    [release],
  );

  const handleSaved = useCallback(async () => {
    const requestScope = learnerProfileScope;
    requestIdRef.current += 1;
    requestedScopeRef.current = requestScope;
    await refreshUserInfo().catch(caughtError => {
      if (scopeRef.current !== requestScope) {
        return;
      }
      debugWarn(
        '[profile-onboarding] failed to refresh user info',
        caughtError,
      );
      notifyRefreshDelay();
    });
    if (scopeRef.current !== requestScope) {
      return;
    }
    release();
  }, [learnerProfileScope, notifyRefreshDelay, refreshUserInfo, release]);

  const openFromMenu = useCallback(() => {
    setAutoStartCollection(false);
    setDialogOpen(true);
  }, []);

  const dialogProps = {
    open: dialogOpen,
    autoStartCollection,
    exitPolicy:
      status?.presentation === 'blocking' ? 'blocking' : 'dismissible',
    presentation: status?.presentation ?? 'hidden',
    initialOnboardingStatus: status ?? undefined,
    externalErrorMessage: status?.presentation === 'blocking' ? error : '',
    externalSubmitting:
      status?.presentation === 'blocking' ? submitting : false,
    draftStorageScope: learnerProfileScope,
    onDefer: status?.presentation === 'blocking' ? defer : undefined,
    onSaved: handleSaved,
    onClose: closeDialog,
  } satisfies LearnerProfileDialogProps;

  return { runtimeReady, openFromMenu, dialogProps };
};
