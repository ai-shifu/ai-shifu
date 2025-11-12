import styles from './SettingInputM.module.scss';
import { useState, useEffect, type ChangeEvent } from 'react';

import { Input } from '@/components/ui/Input';

interface SettingInputRule {
  validator: (value: string) => boolean;
  message: string;
}

interface SettingInputMProps {
  title: string;
  placeholder?: string;
  value?: string;
  onChange?: (value: string) => void;
  rules?: SettingInputRule[];
}

export const SettingInputM = ({
  title,
  placeholder = '',
  value = '',
  onChange,
  rules = [],
}: SettingInputMProps) => {
  const [_value, setValue] = useState(value);
  const [isError, setIsError] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    setValue(value);
  }, [value]);

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const val = event.target.value;
    setIsError(false);
    setValue(val);
    onChange?.(val);
  };

  const _onBlur = () => {
    if (!rules || !rules.length) {
      setIsError(false);
    }

    rules.some(rule => {
      const ret = rule.validator(_value);

      if (!ret) {
        setIsError(true);
        setErrorMessage(rule.message);
        return true;
      }
      return false;
    });
  };

  return (
    <div className={styles.settingInputM}>
      <div
        className={styles.title}
        style={{ visibility: _value ? 'visible' : 'hidden' }}
      >
        {title}
      </div>
      <div className={styles.inputWrapper}>
        <Input
          className={styles.inputElement}
          value={_value}
          onChange={handleChange}
          onBlur={_onBlur}
          placeholder={placeholder || title}
        />
      </div>
      <div
        className={styles.errorMessage}
        style={{ visibility: isError ? 'visible' : 'hidden' }}
      >
        {errorMessage}
      </div>
    </div>
  );
};
