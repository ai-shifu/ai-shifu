'use client';
import React, { useCallback, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/Button';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/Sheet';
import { Bars3Icon, DocumentIcon } from '@heroicons/react/24/outline';
import Image from 'next/image';
import Link from 'next/link';
import NavFooter from '@/app/c/[[...id]]/Components/NavDrawer/NavFooter';
import MainMenuModal from '@/app/c/[[...id]]/Components/NavDrawer/MainMenuModal';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { useTranslation } from 'react-i18next';
import logo from '@/c-assets/logos/ai-shifu-logo-horizontal.png';
import adminSidebarStyles from './AdminSidebar.module.scss';
import styles from './layout.module.scss';
import { cn } from '@/lib/utils';

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
};

const SidebarContent = ({
  menuItems,
  footerRef,
  userMenuOpen,
  onFooterClick,
  onUserMenuClose,
  userMenuClassName,
}: SidebarContentProps) => {
  return (
    <div className={cn('flex flex-col h-full relative', styles.adminLayout)}>
      <h1 className={cn('text-xl font-bold p-4', styles.adminLogo)}>
        <Image
          className='dark:invert'
          src={logo}
          alt='AI-Shifu'
          width={117}
          height={32}
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
            return (
              <Link
                key={index}
                href={item.href || '#'}
                className='flex items-center space-x-2 px-2 py-2 rounded-lg hover:bg-gray-100'
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
  ];

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
        />
      </div>
      <div className='flex-1 p-5  overflow-hidden bg-background'>
        <div className='max-w-6xl mx-auto h-full overflow-hidden'>
          {children}
        </div>
      </div>
      <div className='md:hidden w-full border-b p-4'>
        <div className='flex items-center justify-between'>
          <Sheet>
            <SheetTrigger asChild>
              <Button
                variant='ghost'
                size='icon'
              >
                <Bars3Icon className='h-6 w-6' />
              </Button>
            </SheetTrigger>
            <SheetContent
              side='left'
              className='w-64 p-0'
            >
              <SidebarContent
                menuItems={menuItems}
                footerRef={mobileFooterRef}
                userMenuOpen={mobileMenuOpen}
                onFooterClick={onMobileFooterClick}
                onUserMenuClose={handleMobileMenuClose}
                userMenuClassName={adminSidebarStyles.navMenuPopup}
              />
            </SheetContent>
          </Sheet>
          <h1 className='text-xl font-bold'>{t('common.core.home')}</h1>
          <div className='w-6' /> {/* Spacer for centering */}
        </div>
      </div>
    </div>
  );
};

export default MainInterface;
