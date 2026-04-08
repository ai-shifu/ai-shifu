'use client';
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Button } from '@/components/ui/Button';
import {
  BanknotesIcon,
  CreditCardIcon,
  DocumentIcon,
  PresentationChartLineIcon,
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
  billingTitle: string;
  billingDescription: string;
  billingCreditsLabel: string;
  billingCreditsValue: string;
  billingStatusLabel: string;
  billingStatusValue: string;
  billingCtaLabel: string;
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
  billingTitle,
  billingDescription,
  billingCreditsLabel,
  billingCreditsValue,
  billingStatusLabel,
  billingStatusValue,
  billingCtaLabel,
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
                data-testid={item.id ? `admin-nav-${item.id}` : undefined}
                className={cn(
                  'flex min-w-0 items-center space-x-2 px-2 py-2 rounded-lg hover:bg-gray-100',
                  isActive && 'bg-gray-200 text-gray-900 font-semibold',
                )}
                aria-current={isActive ? 'page' : undefined}
              >
                {item.icon}
                <span className='min-w-0 flex-1 truncate whitespace-nowrap'>
                  {item.label}
                </span>
              </Link>
            );
          })}
        </nav>
        <div
          className='mt-4 rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-[0_10px_24px_rgba(15,23,42,0.06)]'
          data-testid='admin-billing-sidebar-card'
        >
          <div className='flex items-start justify-between gap-3'>
            <div className='min-w-0'>
              <p className='text-sm font-semibold text-slate-900'>
                {billingTitle}
              </p>
              <p className='mt-1 text-xs leading-5 text-slate-500'>
                {billingDescription}
              </p>
            </div>
            <div className='flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-amber-600'>
              <CreditCardIcon className='h-5 w-5' />
            </div>
          </div>
          <div className='mt-4 grid gap-2 rounded-xl bg-slate-50 p-3'>
            <div className='flex items-center justify-between gap-3 text-sm'>
              <span className='text-slate-500'>{billingCreditsLabel}</span>
              <span className='font-semibold text-slate-900'>
                {billingCreditsValue}
              </span>
            </div>
            <div className='flex items-center justify-between gap-3 text-sm'>
              <span className='text-slate-500'>{billingStatusLabel}</span>
              <span className='font-semibold text-slate-900'>
                {billingStatusValue}
              </span>
            </div>
          </div>
          <Button
            asChild
            className='mt-4 w-full justify-between rounded-xl'
          >
            <Link href='/admin/billing'>{billingCtaLabel}</Link>
          </Button>
        </div>
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

  const menuItems: MenuItem[] = [
    {
      id: 'shifu',
      icon: <DocumentIcon className='w-4 h-4' />,
      label: t('common.core.shifu'),
      href: '/admin',
    },
    {
      id: 'orders',
      icon: <ShoppingCartIcon className='w-4 h-4' />,
      label: t('module.order.title'),
      href: '/admin/orders',
    },
    {
      id: 'dashboard',
      icon: <PresentationChartLineIcon className='w-4 h-4' />,
      label: t('module.dashboard.title'),
      href: '/admin/dashboard',
    },
    {
      id: 'billing',
      icon: <BanknotesIcon className='w-4 h-4' />,
      label: t('module.billing.navTitle'),
      href: '/admin/billing',
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
          billingTitle={t('module.billing.sidebar.title')}
          billingDescription={t('module.billing.sidebar.description')}
          billingCreditsLabel={t('module.billing.sidebar.totalCreditsLabel')}
          billingCreditsValue={t('module.billing.sidebar.placeholderValue')}
          billingStatusLabel={t(
            'module.billing.sidebar.subscriptionStatusLabel',
          )}
          billingStatusValue={t('module.billing.sidebar.subscriptionPending')}
          billingCtaLabel={t('module.billing.sidebar.cta')}
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
