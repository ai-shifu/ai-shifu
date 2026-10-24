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
import { useDisclosure } from '@/hooks/useDisclosure';
import { useEnvStore } from '@/store';
import { EnvStoreState } from '@/types/store';
import { useBillingOverview } from '@/hooks/useBillingData';
import { useUserStore } from '@/store';
import { ContactSideRail } from '@/components/contact/ContactSideRail';
import LearnerProfileDialog from '@/components/profile-onboarding/LearnerProfileDialog';
import { WelcomeTrialDialog } from '@/components/billing/WelcomeTrialDialog';
import { applyCreatorBranding } from '@/lib/initializeEnvData';
import type { ReferralInviteProfile } from '@/types/referral';
import { buildAdminMenuItems } from './admin-menu';
import { SidebarContent } from './SidebarContent';
import AdminDocumentTitleSync from './AdminDocumentTitleSync';

const MainInterface = ({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) => {
  const { t, i18n } = useTranslation();
  const pathname = usePathname();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isGuest = useUserStore(state => state.isGuest);
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const currentUserId = useUserStore(state => state.userInfo?.user_id || '');
  const refreshUserInfo = useUserStore(state => state.refreshUserInfo);
  const isOperator = useUserStore(state =>
    Boolean(state.userInfo?.is_operator),
  );
  const hasAuthenticatedAdminSession = isInitialized && isLoggedIn && !isGuest;
  const hasResolvedAdminSession =
    hasAuthenticatedAdminSession && Boolean(currentUserId);
  const menuReady = hasResolvedAdminSession;
  const adminTitle = t('common.core.adminTitle');
  const [learnerProfileSettingsScope, setLearnerProfileSettingsScope] =
    React.useState<string | null>(null);
  const learnerProfileSettingsOpen =
    hasResolvedAdminSession && learnerProfileSettingsScope === currentUserId;

  const openLearnerProfileSettings = useCallback(() => {
    if (hasResolvedAdminSession) {
      setLearnerProfileSettingsScope(currentUserId);
    }
  }, [currentUserId, hasResolvedAdminSession]);

  const closeLearnerProfileSettings = useCallback(() => {
    setLearnerProfileSettingsScope(null);
  }, []);

  const handleLearnerProfileSaved = useCallback(async () => {
    await refreshUserInfo();
  }, [refreshUserInfo]);

  useEffect(() => {
    setLearnerProfileSettingsScope(null);
  }, [currentUserId, hasResolvedAdminSession]);

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

  const paymentChannels = useEnvStore(
    (state: EnvStoreState) => state.paymentChannels,
  );
  const billingEnabled = useEnvStore(
    (state: EnvStoreState) => state.billingEnabled === 'true',
  );
  const stripeEnabled = useEnvStore(
    (state: EnvStoreState) => state.stripeEnabled === 'true',
  );
  const normalizedPaymentChannels = useMemo(
    () => (Array.isArray(paymentChannels) ? paymentChannels : []),
    [paymentChannels],
  );
  const showPackageManagement = useMemo(
    () =>
      billingEnabled &&
      stripeEnabled &&
      normalizedPaymentChannels.some(
        channel =>
          String(channel || '')
            .trim()
            .toLowerCase() === 'stripe',
      ),
    [billingEnabled, normalizedPaymentChannels, stripeEnabled],
  );

  const activeAdminLanguage = i18n.resolvedLanguage || i18n.language;
  const menuItems = useMemo(() => {
    const translateMenuLabel = (key: string) => {
      void activeAdminLanguage;
      return t(key);
    };
    return buildAdminMenuItems({
      t: translateMenuLabel,
      isOperator,
      showReferralInvite,
      showPackageManagement,
    });
  }, [
    activeAdminLanguage,
    isOperator,
    showPackageManagement,
    showReferralInvite,
    t,
  ]);

  const {
    data: billingOverview,
    isLoading: billingOverviewLoading,
    mutate: mutateBillingOverview,
  } = useBillingOverview();
  return (
    <>
      <Suspense fallback={null}>
        <AdminDocumentTitleSync title={adminTitle} />
      </Suspense>
      <WelcomeTrialDialog
        billingOverview={billingOverview}
        menuReady={menuReady}
        mutateBillingOverview={mutateBillingOverview}
      />
      {learnerProfileSettingsOpen ? (
        <LearnerProfileDialog
          key={learnerProfileSettingsScope}
          open
          autoStartCollection={false}
          exitPolicy='dismissible'
          draftStorageScope={learnerProfileSettingsScope}
          onSaved={handleLearnerProfileSaved}
          onClose={closeLearnerProfileSettings}
        />
      ) : null}
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
            onPersonalInfoClick={openLearnerProfileSettings}
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
