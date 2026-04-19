'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Image, { type StaticImageData } from 'next/image';
import Link from 'next/link';
import { ChevronDown } from 'lucide-react';
import NavFooter from '@/app/c/[[...id]]/Components/NavDrawer/NavFooter';
import MainMenuModal from '@/app/c/[[...id]]/Components/NavDrawer/MainMenuModal';
import defaultLogo from '@/c-assets/logos/ai-shifu-logo-horizontal.png';
import { BillingSidebarCard } from '@/components/billing/BillingSidebarCard';
import { cn } from '@/lib/utils';
import { CreatorBillingOverview } from '@/types/billing';
import adminSidebarStyles from './AdminSidebar.module.scss';
import { AdminMenuItem } from './admin-menu';
import styles from './layout.module.scss';

export type SidebarContentProps = {
  menuItems: AdminMenuItem[];
  loading?: boolean;
  footerRef: React.MutableRefObject<any>;
  userMenuOpen: boolean;
  onFooterClick: () => void;
  onUserMenuClose: (e?: Event | React.MouseEvent) => void;
  userMenuClassName?: string;
  logoSrc: string | StaticImageData;
  activePath?: string;
  showBillingCard?: boolean;
  billingOverviewLoading?: boolean;
  billingOverview?: CreatorBillingOverview;
};

const normalizeRoutePath = (path?: string) => {
  if (!path) {
    return '';
  }
  const trimmed = path.replace(/\/+$/, '');
  return trimmed || '/';
};

const findBestMatchingHref = (
  menuItems: AdminMenuItem[],
  normalizedPath: string,
): string | undefined => {
  if (!normalizedPath) {
    return undefined;
  }

  let bestHref: string | undefined;
  let bestLength = -1;

  const visit = (items: AdminMenuItem[]) => {
    items.forEach(item => {
      if (item.href) {
        const normalizedHref = normalizeRoutePath(item.href);
        const matches =
          normalizedPath === normalizedHref ||
          normalizedPath.startsWith(`${normalizedHref}/`);

        if (matches && normalizedHref.length > bestLength) {
          bestHref = item.href;
          bestLength = normalizedHref.length;
        }
      }

      if (item.children?.length) {
        visit(item.children);
      }
    });
  };

  visit(menuItems);
  return bestHref;
};

const collectExpandedMenuIds = (
  menuItems: AdminMenuItem[],
  normalizedPath: string,
): string[] => {
  const expandedIds = new Set<string>();

  const visit = (item: AdminMenuItem): boolean => {
    if (!normalizedPath) {
      return false;
    }

    const isDirectMatch =
      Boolean(item.href) &&
      findBestMatchingHref([item], normalizedPath) === item.href;
    const hasMatchingChild =
      item.children?.some(child => visit(child)) ?? false;

    if (hasMatchingChild && item.id) {
      expandedIds.add(item.id);
    }

    return isDirectMatch || hasMatchingChild;
  };

  menuItems.forEach(item => visit(item));
  return Array.from(expandedIds);
};

export const SidebarContent = ({
  menuItems,
  loading = false,
  footerRef,
  userMenuOpen,
  onFooterClick,
  onUserMenuClose,
  userMenuClassName,
  logoSrc,
  activePath,
  showBillingCard = true,
  billingOverviewLoading = false,
  billingOverview,
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

  const normalizedPath = useMemo(
    () => normalizeRoutePath(activePath),
    [activePath],
  );

  const activeHref = useMemo(() => {
    return findBestMatchingHref(menuItems, normalizedPath);
  }, [menuItems, normalizedPath]);

  const defaultExpandedMenuIds = useMemo(
    () => collectExpandedMenuIds(menuItems, normalizedPath),
    [menuItems, normalizedPath],
  );
  const [expandedMenuIds, setExpandedMenuIds] = useState<string[]>(
    defaultExpandedMenuIds,
  );

  useEffect(() => {
    setExpandedMenuIds(prevExpandedIds => {
      const nextExpandedIds = new Set(prevExpandedIds);
      defaultExpandedMenuIds.forEach(id => nextExpandedIds.add(id));
      return Array.from(nextExpandedIds);
    });
  }, [defaultExpandedMenuIds]);

  const toggleMenuItem = useCallback((itemId: string) => {
    setExpandedMenuIds(prevExpandedIds =>
      prevExpandedIds.includes(itemId)
        ? prevExpandedIds.filter(id => id !== itemId)
        : [...prevExpandedIds, itemId],
    );
  }, []);

  const renderMenuItems = useCallback(
    (items: AdminMenuItem[], level = 0) =>
      items.map((item, index) => {
        if (item.type == 'divider') {
          return (
            <div
              key={item.id || `divider-${level}-${index}`}
              className='h-px bg-gray-200'
            ></div>
          );
        }

        const key = item.id || item.href || `item-${level}-${index}`;
        const hasChildren = Boolean(item.children?.length);
        const isExpanded = item.id ? expandedMenuIds.includes(item.id) : false;
        const isActive = Boolean(activeHref) && item.href === activeHref;
        const itemId = item.id;

        if (hasChildren && itemId) {
          return (
            <div
              key={key}
              className='space-y-1'
            >
              <button
                type='button'
                className={cn(
                  'flex w-full min-w-0 items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-gray-100',
                )}
                aria-expanded={isExpanded}
                onClick={() => toggleMenuItem(itemId)}
              >
                {item.icon}
                <span className='min-w-0 flex-1 truncate whitespace-nowrap'>
                  {item.label}
                </span>
                <ChevronDown
                  className={cn(
                    'h-4 w-4 shrink-0 text-gray-500 transition-transform duration-200',
                    isExpanded && 'rotate-180',
                  )}
                />
              </button>
              {isExpanded ? (
                <div className='space-y-1'>
                  {renderMenuItems(item.children || [], level + 1)}
                </div>
              ) : null}
            </div>
          );
        }

        return (
          <Link
            key={key}
            href={item.href || '#'}
            data-testid={item.id ? `admin-nav-${item.id}` : undefined}
            className={cn(
              'flex min-w-0 items-center gap-2 rounded-lg px-2 py-2 hover:bg-gray-100',
              isActive && 'bg-gray-200 text-gray-900',
              level > 0 && 'ml-6 text-[0.95rem]',
            )}
            aria-current={isActive ? 'page' : undefined}
          >
            {item.icon ? item.icon : null}
            <span className='min-w-0 flex-1 truncate whitespace-nowrap'>
              {item.label}
            </span>
          </Link>
        );
      }),
    [activeHref, expandedMenuIds, toggleMenuItem],
  );

  return (
    <div
      className={cn(
        'relative flex h-full min-h-0 flex-col',
        styles.adminLayout,
      )}
    >
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
      <div className='flex min-h-0 flex-1 flex-col p-2'>
        {loading ? (
          <div
            className='space-y-3 px-2 pt-2 animate-pulse'
            aria-label='admin-sidebar-loading'
          >
            <div className='h-10 rounded-lg bg-gray-200' />
            <div className='h-10 rounded-lg bg-gray-200' />
            <div className='h-10 rounded-lg bg-gray-200' />
            <div className='h-10 rounded-lg bg-gray-200' />
          </div>
        ) : (
          <>
            {/* Keep the menu list flexible so the billing card stays pinned to the bottom. */}
            <nav
              className='min-h-0 flex-1 space-y-1 overflow-y-auto'
              data-testid='admin-sidebar-nav'
            >
              {renderMenuItems(menuItems)}
            </nav>
            {showBillingCard && !userMenuOpen ? (
              <BillingSidebarCard
                overview={billingOverview}
                isLoading={billingOverviewLoading}
              />
            ) : null}
          </>
        )}
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
        className={userMenuClassName || adminSidebarStyles.navMenuPopup}
        isAdmin
      />
    </div>
  );
};
