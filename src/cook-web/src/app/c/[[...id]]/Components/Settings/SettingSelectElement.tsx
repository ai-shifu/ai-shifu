import styles from './SettingSelectElement.module.scss';

import { memo } from 'react';
import { ChevronDownIcon } from 'lucide-react'
import clsx from 'clsx';

export const SettingSelectElement = ({
  className = '',
  title = '',
  value = '',
  placeholder = '',
  onClick = (e) => {},
}) => {
  return (
    <div
      className={clsx(styles.settingSelect, className)}
      onClick={onClick}
    >
      <div className={styles.title}>{value && title}</div>
      <div className={styles.inputWrapper}>
        <input
          type="text"
          className={styles.inputElement}
          placeholder={placeholder}
          readOnly={true}
          value={value}
        />
        <ChevronDownIcon className={styles.icon} />
      </div>
    </div>
  );
};

export default memo(SettingSelectElement);
