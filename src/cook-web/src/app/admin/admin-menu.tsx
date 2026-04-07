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
      icon: <PresentationChartLineIcon className='w-4 h-4' />,
      label: t('module.dashboard.title'),
      href: '/admin/dashboard',
    },
  ];

  if (isOperator) {
    items.push({
      icon: <BriefcaseIcon className='w-4 h-4' />,
      label: t('common.core.operations'),
      href: '/admin/operations',
    });
  }

  return items;
};
