'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { type StaticImageData } from 'next/image';
import { usePathname } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import defaultLogo from '@/c-assets/logos/ai-shifu-logo-horizontal.png';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { environment } from '@/config/environment';
import { useBillingOverview } from '@/hooks/useBillingData';
import { useUserStore } from '@/store';
import { WelcomeTrialDialog } from '@/components/billing/WelcomeTrialDialog';
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
  const isOperator = useUserStore(state =>
    Boolean(state.userInfo?.is_operator),
  );
  const menuReady = isInitialized && !isGuest;

  useEffect(() => {
    if (!isInitialized || !isGuest || typeof window === 'undefined') {
      return;
    }

    const currentPath = encodeURIComponent(
      window.location.pathname + window.location.search,
    );
    window.location.href = `/login?redirect=${currentPath}`;
  }, [isGuest, isInitialized]);

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

  const [logoSrc, setLogoSrc] = useState<string | StaticImageData>(
    environment.logoWideUrl || defaultLogo,
  );
  const {
    data: billingOverview,
    isLoading: billingOverviewLoading,
    mutate: mutateBillingOverview,
  } = useBillingOverview();
  const billingEnabled = useEnvStore(
    (state: EnvStoreState) => state.billingEnabled === 'true',
  );
  const logoWideUrl = useEnvStore((state: EnvStoreState) => state.logoWideUrl);

  useEffect(() => {
    setLogoSrc(logoWideUrl || environment.logoWideUrl || defaultLogo);
  }, [logoWideUrl]);

  const resolvedLogo = logoSrc || defaultLogo;

  return (
    <>
      {billingEnabled ? (
        <WelcomeTrialDialog
          billingOverview={billingOverview}
          menuReady={menuReady}
          mutateBillingOverview={mutateBillingOverview}
        />
      ) : null}
      <div className='flex h-screen bg-stone-50'>
        <div className='w-[280px] shrink-0'>
          <SidebarContent
            menuItems={menuItems}
            loading={!menuReady}
            footerRef={desktopFooterRef}
            userMenuOpen={desktopMenuOpen}
            onFooterClick={onDesktopFooterClick}
            onUserMenuClose={handleDesktopMenuClose}
            logoSrc={resolvedLogo}
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
