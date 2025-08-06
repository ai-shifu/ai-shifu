import styles from './SettingHeader.module.scss';

import { memo } from 'react';

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@/components/ui/Breadcrumb';

import { cn } from '@/lib/utils';

import { useTranslation } from 'react-i18next';

export const SettingHeader = ({ className, onHomeClick }) => {
  const { t } = useTranslation('translation', { keyPrefix: 'c' });
  return (
    <div className={cn(styles.settingHeader, className)}>
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <span
              className={styles.clickable}
              onClick={onHomeClick}
            >
              {t('settings.home')}
            </span>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <span>{t('settings.settingTitle')}</span>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
    </div>
  );
};

export default memo(SettingHeader);
