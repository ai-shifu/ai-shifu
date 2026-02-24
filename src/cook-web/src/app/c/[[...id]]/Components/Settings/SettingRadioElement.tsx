import styles from './SettingRadioElement.module.scss';

import { useEffect, memo, useState } from 'react';

import { RadioGroup, RadioGroupItem } from '@/components/ui/RadioGroup';

import { cn } from '@/lib/utils';

export const SettingRadioElement = ({
  title = '',
  className = '',
  options = [],
  value = '',
}) => {
  const [curr, setCurr] = useState(value);

  useEffect(() => {
    setCurr(value);
  }, [value]);

  return (
    <div className={cn(styles.settingRadio, className)}>
      <div className={styles.title}>{title}</div>
      <div className={styles.inputWrapper}>
        <RadioGroup value={curr}>
          {options.map(opt => {
            const { label, value } = opt;
            return (
              <RadioGroupItem
                key={value}
                value={value}
                className={styles.inputElement}
              >
                {label}
              </RadioGroupItem>
            );
          })}
        </RadioGroup>
      </div>
    </div>
  );
};

export default memo(SettingRadioElement);
