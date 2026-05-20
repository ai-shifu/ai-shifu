'use client';

import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { useBillingOverview } from '@/hooks/useBillingData';
import { useUserStore } from '@/store';
import { WelcomeTrialDialog } from '@/components/billing/WelcomeTrialDialog';
import { ContactSideRail } from '@/components/contact/ContactSideRail';
import { buildAdminMenuItems } from './admin-menu';
import { SidebarContent } from './SidebarContent';

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
  const isOperator = useUserStore(state =>
    Boolean(state.userInfo?.is_operator),
  );
  const hasAuthenticatedAdminSession = isInitialized && isLoggedIn && !isGuest;
  const hasResolvedAdminSession =
    hasAuthenticatedAdminSession && Boolean(currentUserId);
  const menuReady = hasResolvedAdminSession;

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

  useEffect(() => {
    document.title = t('common.core.adminTitle');
  }, [t, i18n.language]);

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

  const menuItems = useMemo(
    () => buildAdminMenuItems({ t, isOperator }),
    [isOperator, t],
  );

  const {
    data: billingOverview,
    isLoading: billingOverviewLoading,
    mutate: mutateBillingOverview,
  } = useBillingOverview();
  const billingEnabled = useEnvStore(
    (state: EnvStoreState) => state.billingEnabled === 'true',
  );

  return (
    <>
      {billingEnabled ? (
        <WelcomeTrialDialog
          billingOverview={billingOverview}
          menuReady={menuReady}
          mutateBillingOverview={mutateBillingOverview}
        />
      ) : null}
      <ContactSideRail />
      <div className='flex h-screen bg-stone-50'>
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
          <div className='mx-auto flex h-full max-w-6xl flex-col px-5 py-5'>
            {children}
          </div>
        </div>
      </div>
    </>
  );
};

export default MainInterface;
