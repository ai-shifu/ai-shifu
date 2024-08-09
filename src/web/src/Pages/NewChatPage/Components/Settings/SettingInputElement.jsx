import { useState } from 'react';
import styles from './SettingInputElement.module.scss';
import classNames from 'classnames';
import { useCallback } from 'react';
import { useEffect } from 'react';

export const SettingInputElement = ({
  value = '',
  onChange = (e) => {},
  placeholder = '',
  title = '',
  className = '',
}) => {
  const [_value, _setValue] = useState(value);

  const onInputChanged = useCallback(
    (e) => {
      _setValue(e.target.value);
      onChange?.(e);
    },
    [onChange]
  );

  useEffect(() => {
    _setValue(value);
  }, [value]);

  return (
    <div className={classNames(styles.settingInputElement, className)}>
      <div className={styles.title}>{_value && title}</div>
      <div className={styles.inputWrapper}>
        <input
          className={styles.inputElement}
          placeholder={placeholder}
          value={_value}
          onChange={onInputChanged}
        />
      </div>
    </div>
  );
};