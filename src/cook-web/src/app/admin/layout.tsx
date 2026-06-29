'use client';

import React, {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from 'react';
import { usePathname } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { useTracking } from '@/c-common/hooks/useTracking';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { useBillingOverview } from '@/hooks/useBillingData';
import {
  useCreatorOnboardingStatus,
  useOnboarding,
} from '@/hooks/useOnboarding';
import { useOnboardingReplayStore, useUserStore } from '@/store';
import { ContactSideRail } from '@/components/contact/ContactSideRail';
import { OnboardingOverlay } from '@/components/onboarding/OnboardingOverlay';
import { buildAdminHomeOnboardingSteps } from '@/components/onboarding/onboardingSteps';
import { WelcomeTrialDialog } from '@/components/billing/WelcomeTrialDialog';
import { applyCreatorBranding } from '@/lib/initializeEnvData';
import type { ReferralInviteProfile } from '@/types/referral';
import { buildAdminMenuItems } from './admin-menu';
import { SidebarContent } from './SidebarContent';
import { getCourseCreatorUrl } from '@/c-utils/urlUtils';
import AdminDocumentTitleSync from './AdminDocumentTitleSync';

const MainInterface = ({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) => {
  const { t, i18n } = useTranslation();
  const { t: tOnboarding } = useTranslation('module.onboarding');
  const pathname = usePathname();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const currentUserId = useUserStore(state => state.userInfo?.user_id || '');
  const currentLanguage = useUserStore(state => state.userInfo?.language || '');
  const isOperator = useUserStore(state =>
    Boolean(state.userInfo?.is_operator),
  );
  const { trackEvent } = useTracking();
  const hasAuthenticatedAdminSession = isInitialized && isLoggedIn && !isGuest;
  const hasResolvedAdminSession =
    hasAuthenticatedAdminSession && Boolean(currentUserId);
  const menuReady = hasResolvedAdminSession;
  const adminTitle = t('common.core.adminTitle');

  useEffect(() => {
    if (
      !isInitialized ||
      hasAuthenticatedAdminSession ||
      typeof window === 'undefined'
    ) {
      return;
    }

    const currentPath = encodeURIComponent(
      window.location.pathname + window.location.search,
    );
    window.location.href = `/login?redirect=${currentPath}`;
  }, [hasAuthenticatedAdminSession, isInitialized]);

  // The /admin path carries no shifu_bid, so the bootstrap runtime-config
  // cannot resolve a creator. Once the logged-in creator is known, re-fetch
  // their branding so the sidebar logo and its click-through use the creator's
  // own logo/home url (falls back to defaults when unconfigured).
  useEffect(() => {
    if (hasResolvedAdminSession && currentUserId) {
      applyCreatorBranding(currentUserId);
    }
  }, [hasResolvedAdminSession, currentUserId]);

  useEffect(() => {
    const html = document.documentElement;
    const root = document.getElementById('root');
    html.classList.add('admin-mode');
    document.body.classList.add('admin-mode');
    root?.classList.add('admin-mode');
    return () => {
      html.classList.remove('admin-mode');
      document.body.classList.remove('admin-mode');
      root?.classList.remove('admin-mode');
    };
  }, []);

  const desktopFooterRef = useRef<any>(null);
  const {
    open: desktopMenuOpen,
    onToggle: toggleDesktopMenu,
    onClose: closeDesktopMenu,
  } = useDisclosure();

  const onDesktopFooterClick = useCallback(() => {
    toggleDesktopMenu();
  }, [toggleDesktopMenu]);

  const handleDesktopMenuClose = useCallback(
    (e?: Event | React.MouseEvent) => {
      if (desktopFooterRef.current?.containElement?.(e?.target)) {
        return;
      }
      closeDesktopMenu();
    },
    [closeDesktopMenu],
  );

  const [showReferralInvite, setShowReferralInvite] = React.useState(false);

  useEffect(() => {
    if (!menuReady) {
      setShowReferralInvite(false);
      return;
    }

    let isActive = true;
    setShowReferralInvite(false);

    api
      .getReferralInviteProfile({})
      .then(response => {
        if (!isActive) {
          return;
        }
        const profile = response as ReferralInviteProfile;
        setShowReferralInvite(
          profile.available !== false && Boolean(profile.invite_url),
        );
      })
      .catch(() => {
        if (isActive) {
          setShowReferralInvite(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, [currentUserId, menuReady]);

  const menuItems = useMemo(
    () => buildAdminMenuItems({ t, isOperator, showReferralInvite }),
    [isOperator, showReferralInvite, t],
  );

  const {
    data: billingOverview,
    isLoading: billingOverviewLoading,
    mutate: mutateBillingOverview,
  } = useBillingOverview();
  const billingEnabled = useEnvStore(
    (state: EnvStoreState) => state.billingEnabled === 'true',
  );
  const { data: onboardingStatus, mutate: mutateOnboardingStatus } =
    useCreatorOnboardingStatus(menuReady);
  const adminHomeSceneStatus = onboardingStatus?.scenes.admin_home_onboarding;
  const courseCreatorUrl = useMemo(() => getCourseCreatorUrl(), []);

  const adminHomeSteps = useMemo(
    () =>
      buildAdminHomeOnboardingSteps({
        t: tOnboarding,
        billingEnabled,
        courseCreatorUrl,
      }),
    [billingEnabled, courseCreatorUrl, tOnboarding],
  );
  const canRunAdminHomeOnboarding =
    pathname === '/admin' &&
    menuReady &&
    (!billingEnabled || !billingOverviewLoading);
  const shouldShowAdminHomeOnboarding =
    canRunAdminHomeOnboarding &&
    adminHomeSceneStatus?.eligible === true &&
    (adminHomeSceneStatus?.status ?? null) === null;
  const replayScenes = useOnboardingReplayStore(state => state.replayScenes);
  const clearReplay = useOnboardingReplayStore(state => state.clearReplay);
  const isAdminHomeReplay = replayScenes.admin_home_onboarding;
  const adminHomeOnboardingEnabled =
    canRunAdminHomeOnboarding &&
    (shouldShowAdminHomeOnboarding || isAdminHomeReplay);

  const persistAdminHomeOnboarding = useCallback(
    async (status: 'completed' | 'skipped') => {
      const version = onboardingStatus?.version || 'v1';
      const language = currentLanguage || i18n.language;
      try {
        await api.completeCreatorOnboarding({
          scene_key: 'admin_home_onboarding',
          version,
          trigger_source: 'admin_entry',
          status,
        });
        trackEvent(
          status === 'skipped'
            ? 'creator_onboarding_skipped'
            : 'creator_onboarding_completed',
          {
            scene_key: 'admin_home_onboarding',
            version,
            user_segment: onboardingStatus?.user_segment || 'ineligible',
            trigger_source: 'admin_entry',
            language,
          },
        );
      } catch {
        trackEvent('creator_onboarding_complete_failed', {
          scene_key: 'admin_home_onboarding',
          version,
          user_segment: onboardingStatus?.user_segment || 'ineligible',
          trigger_source: 'admin_entry',
          language,
        });
      }
      await mutateOnboardingStatus(current => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          scenes: {
            ...current.scenes,
            admin_home_onboarding: {
              ...current.scenes.admin_home_onboarding,
              completed: status === 'completed',
              completed_at: new Date().toISOString(),
              status,
            },
          },
        };
      }, false);
    },
    [
      currentLanguage,
      i18n.language,
      mutateOnboardingStatus,
      onboardingStatus?.user_segment,
      onboardingStatus?.version,
      trackEvent,
    ],
  );

  const {
    isOpen: adminHomeOnboardingOpen,
    currentStep: adminHomeOnboardingStep,
    currentStepIndex: adminHomeOnboardingStepIndex,
    totalSteps: adminHomeOnboardingTotalSteps,
    targetRect: adminHomeOnboardingTargetRect,
    advance: advanceAdminHomeOnboarding,
    skip: skipAdminHomeOnboarding,
  } = useOnboarding({
    enabled: adminHomeOnboardingEnabled,
    steps: adminHomeSteps,
    onStepResolved: (step, stepIndex) => {
      trackEvent('creator_onboarding_step_viewed', {
        scene_key: 'admin_home_onboarding',
        version: onboardingStatus?.version || 'v1',
        user_segment: onboardingStatus?.user_segment || 'ineligible',
        step_id: step.id,
        step_index: stepIndex + 1,
        trigger_source: 'admin_entry',
        language: currentLanguage || i18n.language,
      });
    },
    onComplete: async () => {
      if (isAdminHomeReplay) {
        clearReplay('admin_home_onboarding');
        return;
      }
      await persistAdminHomeOnboarding('completed');
      clearReplay('admin_home_onboarding');
    },
    onSkip: async () => {
      if (isAdminHomeReplay) {
        clearReplay('admin_home_onboarding');
        return;
      }
      await persistAdminHomeOnboarding('skipped');
      clearReplay('admin_home_onboarding');
    },
  });

  const trackedOnboardingStartRef = useRef(false);
  useEffect(() => {
    if (!adminHomeOnboardingOpen || trackedOnboardingStartRef.current) {
      return;
    }
    trackedOnboardingStartRef.current = true;
    trackEvent('creator_onboarding_started', {
      scene_key: 'admin_home_onboarding',
      version: onboardingStatus?.version || 'v1',
      user_segment: onboardingStatus?.user_segment || 'ineligible',
      trigger_source: 'admin_entry',
      language: currentLanguage || i18n.language,
    });
  }, [
    adminHomeOnboardingOpen,
    currentLanguage,
    i18n.language,
    onboardingStatus?.user_segment,
    onboardingStatus?.version,
    trackEvent,
  ]);

  return (
    <>
      <Suspense fallback={null}>
        <AdminDocumentTitleSync title={adminTitle} />
      </Suspense>
      {adminHomeOnboardingStep ? (
        <OnboardingOverlay
          open={adminHomeOnboardingOpen}
          advanceAriaLabel={tOnboarding('common.continue')}
          title={adminHomeOnboardingStep.title}
          description={adminHomeOnboardingStep.description}
          stepIndex={adminHomeOnboardingStepIndex}
          totalSteps={adminHomeOnboardingTotalSteps}
          continueLabel={tOnboarding('common.continue')}
          actionLabel={adminHomeOnboardingStep.actionLabel}
          actionHref={adminHomeOnboardingStep.actionHref}
          targetRect={adminHomeOnboardingTargetRect}
          highlightPadding={adminHomeOnboardingStep.highlightPadding}
          onAdvance={() => {
            void advanceAdminHomeOnboarding();
          }}
          skipLabel={tOnboarding('common.skip')}
          onSkip={() => {
            void skipAdminHomeOnboarding();
          }}
        />
      ) : null}
      <WelcomeTrialDialog
        billingOverview={billingOverview}
        menuReady={menuReady}
        mutateBillingOverview={mutateBillingOverview}
      />
      <ContactSideRail />
      <div className='flex h-dvh overflow-hidden bg-stone-50'>
        <div className='w-[280px] shrink-0'>
          <SidebarContent
            menuItems={menuItems}
            loading={!menuReady}
            footerRef={desktopFooterRef}
            userMenuOpen={desktopMenuOpen}
            onFooterClick={onDesktopFooterClick}
            onUserMenuClose={handleDesktopMenuClose}
            activePath={pathname}
            showBillingCard={billingEnabled}
            billingOverview={billingOverview}
            billingOverviewLoading={billingOverviewLoading}
          />
        </div>
        <div
          className='flex-1 overflow-y-auto overflow-x-hidden bg-background'
          data-testid='admin-layout-content'
        >
          <div className='mx-auto box-border flex h-full min-h-0 max-w-6xl flex-col px-6 py-[22px]'>
            {children}
          </div>
        </div>
      </div>
    </>
  );
};

export default MainInterface;
