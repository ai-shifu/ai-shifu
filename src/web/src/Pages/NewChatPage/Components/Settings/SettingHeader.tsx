import { Breadcrumb } from 'antd';
import styles from './SettingHeader.module.scss';
import classNames from 'classnames';
import { memo } from 'react';
import { useTranslation } from 'react-i18next';

export const SettingHeader = ({ className, onHomeClick }) => {
  const { t } = useTranslation();
  return (
    <div className={classNames(styles.settingHeader, className)}>
      <Breadcrumb
        items={[
          {
            title: (
              <span className={styles.clickable} onClick={onHomeClick}>
                {t('settings.home')}
              </span>
            ),
          },
          { title: <span>{t('settings.settingTite')}</span> },
        ]}
      />
    </div>
  );
};

export default memo(SettingHeader);
