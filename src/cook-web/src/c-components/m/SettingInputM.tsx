import styles from './SettingInputM.module.scss';
import { useState, useEffect } from 'react';

import { Input } from '@/components/ui/input';

export const SettingInputM = ({
  title,
  placeholder,
  value,
  onChange,
  rules = [],
}) => {
  const [_value, setValue] = useState(value);
  const [isError, setIsError] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    setValue(value);
  }, [value]);

  const _onChange = (val) => {
    setIsError(false);
    setValue(val);
    onChange?.(val);
  };

  const _onBlur = () => {
    if (!rules || !rules.length) {
      setIsError(false);
    }

    rules.some((r) => {
      const ret = r.validator(_value);

      if (!ret) {
        setIsError(true);
        setErrorMessage(r.message);
        return true
      }
      return false
    });
  };

  return (
    <div className={styles.settingInputM}>
      <div className={styles.title} style={{visibility: _value ? 'visible' : 'hidden'}}>{title}</div>
      <div className={styles.inputWrapper}>
        <Input
          className={styles.inputElement}
          value={value}
          onChange={_onChange}
          onBlur={_onBlur}
          placeholder={placeholder || title}
          clearable={true}
        />
      </div>
      <div className={styles.errorMessage} style={{visibility: isError ? 'visible' : 'hidden'}} >{errorMessage}</div>
    </div>
  );
};
