import React from 'react';
import {
  BriefcaseIcon,
  DocumentIcon,
  PresentationChartLineIcon,
  ShoppingCartIcon,
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
};

export const buildAdminMenuItems = ({
  t,
  isOperator,
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
      ],
    });
  }

  return items;
};
