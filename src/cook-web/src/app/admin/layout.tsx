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
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { useTranslation } from 'react-i18next';
import { environment } from '@/config/environment';
import defaultLogo from '@/c-assets/logos/ai-shifu-logo-horizontal.png';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';
import { useUserStore } from '@/store';
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
    environment.logoWideUrl,
  );

  const logoWideUrl = useEnvStore((state: EnvStoreState) => state.logoWideUrl);

  useEffect(() => {
    setLogoSrc(logoWideUrl || environment.logoWideUrl || defaultLogo);
  }, [logoWideUrl]);

  const resolvedLogo = logoSrc || defaultLogo;

  return (
    <div className='flex h-screen overflow-hidden bg-stone-50'>
      <div className='h-full w-[280px] shrink-0'>
        <SidebarContent
          menuItems={menuItems}
          loading={!menuReady}
          footerRef={desktopFooterRef}
          userMenuOpen={desktopMenuOpen}
          onFooterClick={onDesktopFooterClick}
          onUserMenuClose={handleDesktopMenuClose}
          logoSrc={resolvedLogo}
          activePath={pathname}
        />
      </div>
      <div className='min-h-0 flex-1 overflow-hidden bg-stone-50 p-5'>
        <div className='mx-auto h-full min-h-0 max-w-6xl overflow-hidden'>
          {children}
        </div>
      </div>
    </div>
  );
};

export default MainInterface;
