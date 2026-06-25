import React from 'react';
import {
  BriefcaseIcon,
  DocumentIcon,
  PresentationChartLineIcon,
  ShoppingCartIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline';

export type AdminMenuItem = {
  type?: string;
  icon?: React.ReactNode;
  label?: string;
  href?: string;
  id?: string;
  children?: AdminMenuItem[];
};

type BuildAdminMenuItemsOptions = {
  t: (key: string) => string;
  isOperator: boolean;
  showReferralInvite?: boolean;
};

export const buildAdminMenuItems = ({
  t,
  isOperator,
  showReferralInvite = true,
}: BuildAdminMenuItemsOptions): AdminMenuItem[] => {
  const items: AdminMenuItem[] = [
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
  ];

  if (showReferralInvite) {
    items.push({
      id: 'referral',
      icon: <UserPlusIcon className='w-4 h-4' />,
      label: t('common.core.referralInvitation'),
      href: '/admin/referral',
    });
  }

  if (isOperator) {
    items.push({
      id: 'operations',
      icon: <BriefcaseIcon className='w-4 h-4' />,
      label: t('common.core.operations'),
      children: [
        {
          id: 'operations-course',
          label: t('common.core.courseManagement'),
          href: '/admin/operations',
        },
        {
          id: 'operations-user',
          label: t('common.core.userManagement'),
          href: '/admin/operations/users',
        },
        {
          id: 'operations-order',
          label: t('common.core.orderManagement'),
          href: '/admin/operations/orders',
        },
        {
          id: 'operations-promotion',
          label: t('common.core.promotionManagement'),
          href: '/admin/operations/promotions',
        },
        {
          id: 'operations-credit-notification',
          label: t('common.core.creditNotificationManagement'),
          href: '/admin/operations/credit-notifications',
        },
        {
          id: 'operations-voice-clone',
          label: t('common.core.voiceCloneManagement'),
          href: '/admin/operations/voice-clones',
        },
        {
          id: 'operations-profile-onboarding',
          label: t('common.core.profileOnboardingManagement'),
          href: '/admin/operations/profile-onboarding',
        },
      ],
    });
  }

  return items;
};
