import { memo } from 'react';
import styles from './SettingSelectElement.module.scss';
import arrow from '@Assets/newchat/light/icon16-arrow-down.png';
import classNames from 'classnames';

export const SettingSelectElement = ({
  className = '',
  title = '',
  value = '',
  placeholder = '',
  onClick = (e) => {},
}) => {
  return (
    <div
      className={classNames(styles.settingSelect, className)}
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
        <img className={styles.icon} src={arrow} alt="icon" />
      </div>
    </div>
  );
};

export default memo(SettingSelectElement);
