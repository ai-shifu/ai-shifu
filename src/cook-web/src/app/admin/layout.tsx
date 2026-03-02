'use client';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Button } from '@/components/ui/Button';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/Sheet';
import {
  ChartBarIcon,
  DocumentIcon,
  ShoppingCartIcon,
} from '@heroicons/react/24/outline';
import Image, { type StaticImageData } from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import NavFooter from '@/app/c/[[...id]]/Components/NavDrawer/NavFooter';
import MainMenuModal from '@/app/c/[[...id]]/Components/NavDrawer/MainMenuModal';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { useTranslation } from 'react-i18next';
import { environment } from '@/config/environment';
import defaultLogo from '@/c-assets/logos/ai-shifu-logo-horizontal.png';
import adminSidebarStyles from './AdminSidebar.module.scss';
import styles from './layout.module.scss';
import { cn } from '@/lib/utils';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';

type MenuItem = {
  type?: string;
  icon?: React.ReactNode;
  label?: string;
  href?: string;
  id?: string;
};

type SidebarContentProps = {
  menuItems: MenuItem[];
  footerRef: React.MutableRefObject<any>;
  userMenuOpen: boolean;
  onFooterClick: () => void;
  onUserMenuClose: (e?: Event | React.MouseEvent) => void;
  userMenuClassName?: string;
  logoSrc: string | StaticImageData;
  activePath?: string;
};

const SidebarContent = ({
  menuItems,
  footerRef,
  userMenuOpen,
  onFooterClick,
  onUserMenuClose,
  userMenuClassName,
  logoSrc,
  activePath,
}: SidebarContentProps) => {
  const logoHeight = 32;
  const logoWidth = useMemo(() => {
    if (
      typeof logoSrc === 'object' &&
      'width' in logoSrc &&
      logoSrc.width &&
      logoSrc.height
    ) {
      return Math.round((logoHeight * logoSrc.width) / logoSrc.height);
    }
    return Math.round(logoHeight * (defaultLogo.width / defaultLogo.height));
  }, [logoSrc]);

  const normalizedPath = useMemo(() => {
    if (!activePath) {
      return '';
    }
    const trimmed = activePath.replace(/\/+$/, '');
    return trimmed || '/';
  }, [activePath]);

  const activeHref = useMemo(() => {
    if (!normalizedPath) {
      return undefined;
    }
    let bestHref: string | undefined;
    let bestLength = -1;
    menuItems.forEach(item => {
      if (!item.href) {
        return;
      }
      const normalizedHref =
        item.href === '/' ? '/' : item.href.replace(/\/+$/, '');
      if (!normalizedHref) {
        return;
      }
      const matches =
        normalizedPath === normalizedHref ||
        normalizedPath.startsWith(`${normalizedHref}/`);
      if (matches && normalizedHref.length > bestLength) {
        bestHref = item.href;
        bestLength = normalizedHref.length;
      }
    });
    return bestHref;
  }, [menuItems, normalizedPath]);

  return (
    <div className={cn('flex flex-col h-full relative', styles.adminLayout)}>
      <h1 className={cn('text-xl font-bold p-4', styles.adminLogo)}>
        <Image
          className='dark:invert'
          src={logoSrc}
          alt='logo'
          height={logoHeight}
          width={logoWidth}
          style={{
            width: 'auto',
            height: logoHeight,
          }}
          priority
        />
      </h1>
      <div className='p-2 flex-1'>
        <nav className='space-y-1'>
          {menuItems.map((item, index) => {
            if (item.type == 'divider') {
              return (
                <div
                  key={index}
                  className='h-px bg-gray-200'
                ></div>
              );
            }
            const isActive = Boolean(activeHref) && item.href === activeHref;
            return (
              <Link
                key={index}
                href={item.href || '#'}
                className={cn(
                  'flex items-center space-x-2 px-2 py-2 rounded-lg hover:bg-gray-100',
                  isActive && 'bg-gray-200 text-gray-900 font-semibold',
                )}
                aria-current={isActive ? 'page' : undefined}
              >
                {item.icon}
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
      <NavFooter
        ref={footerRef}
        // @ts-expect-error EXPECT
        onClick={onFooterClick}
        isMenuOpen={userMenuOpen}
      />
      {/* @ts-expect-error EXPECT */}
      <MainMenuModal
        open={userMenuOpen}
        onClose={onUserMenuClose}
        className={userMenuClassName}
        isAdmin
      />
    </div>
  );
};

const MainInterface = ({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) => {
  const { t, i18n } = useTranslation();
  const pathname = usePathname();
  useEffect(() => {
    document.title = t('common.core.adminTitle');
  }, [t, i18n.language]);

  const desktopFooterRef = useRef<any>(null);
  const {
    open: desktopMenuOpen,
    onToggle: toggleDesktopMenu,
    onClose: closeDesktopMenu,
  } = useDisclosure();

  const mobileFooterRef = useRef<any>(null);
  const {
    open: mobileMenuOpen,
    onToggle: toggleMobileMenu,
    onClose: closeMobileMenu,
  } = useDisclosure();

  const onDesktopFooterClick = useCallback(() => {
    toggleDesktopMenu();
  }, [toggleDesktopMenu]);

  const onMobileFooterClick = useCallback(() => {
    toggleMobileMenu();
  }, [toggleMobileMenu]);

  const handleDesktopMenuClose = useCallback(
    (e?: Event | React.MouseEvent) => {
      if (desktopFooterRef.current?.containElement?.(e?.target)) {
        return;
      }
      closeDesktopMenu();
    },
    [closeDesktopMenu],
  );

  const handleMobileMenuClose = useCallback(
    (e?: Event | React.MouseEvent) => {
      if (mobileFooterRef.current?.containElement?.(e?.target)) {
        return;
      }
      closeMobileMenu();
    },
    [closeMobileMenu],
  );

  const menuItems: MenuItem[] = [
    {
      icon: <DocumentIcon className='w-4 h-4' />,
      label: t('common.core.shifu'),
      href: '/admin',
    },
    {
      icon: <ShoppingCartIcon className='w-4 h-4' />,
      label: t('module.order.title'),
      href: '/admin/orders',
    },
    {
      icon: <ChartBarIcon className='w-4 h-4' />,
      label: t('module.dashboard.title'),
      href: '/admin/dashboard',
    },
  ];

  const [logoSrc, setLogoSrc] = useState<string | StaticImageData>(
    environment.logoWideUrl,
  );

  const logoWideUrl = useEnvStore((state: EnvStoreState) => state.logoWideUrl);

  useEffect(() => {
    setLogoSrc(logoWideUrl || environment.logoWideUrl || defaultLogo);
  }, [logoWideUrl]);

  const resolvedLogo = logoSrc || defaultLogo;

  return (
    <div className='h-screen flex bg-stone-50'>
      <div className='w-[280px]'>
        <SidebarContent
          menuItems={menuItems}
          footerRef={desktopFooterRef}
          userMenuOpen={desktopMenuOpen}
          onFooterClick={onDesktopFooterClick}
          onUserMenuClose={handleDesktopMenuClose}
          userMenuClassName={adminSidebarStyles.navMenuPopup}
          logoSrc={resolvedLogo}
          activePath={pathname}
        />
      </div>
      <div className='flex-1 p-5  overflow-hidden bg-background'>
        <div className='max-w-6xl mx-auto h-full overflow-hidden'>
          {children}
        </div>
      </div>
    </div>
  );
};

export default MainInterface;
