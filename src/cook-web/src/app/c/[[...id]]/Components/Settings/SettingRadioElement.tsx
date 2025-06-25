import styles from './SettingRadioElement.module.scss';

import { useEffect, memo, useState  } from 'react';

import { Label } from "@/components/ui/label"
import {
  RadioGroup,
  RadioGroupItem,
} from "@/components/ui/radio-group"

import { cn } from '@/lib/utils';

export const SettingRadioElement = ({
  title = '',
  className = '',
  options = [],
  value = '',
  // onChange = (e) => {},
}) => {
  const [curr, setCurr] = useState(value);

  useEffect(() => {
    setCurr(value);
  }, [value]);

  // const _onChange = useCallback(
  //   (e) => {
  //     setCurr(e.target.value);
  //     onChange(e.target.value);
  //   },
  //   [setCurr, onChange]
  // );

  return (
    <div className={cn(styles.settingRadio, className)}>
      <div className={styles.title}>
        {title}
      </div>
      <div className={styles.inputWrapper}>
        <RadioGroup  value={curr}>
          {options.map((opt) => {
            const { label, value } = opt;
            <div className="flex items-center gap-3">
              <Label>
                <RadioGroupItem value={value} />
                {label}
              </Label>
            </div>
            return (
              <RadioGroupItem key={value} value={value} className={styles.inputElement}>
                {label}
              </RadioGroupItem>
            )
          })}
        </RadioGroup>
      </div>
    </div>
  );
};

export default memo(SettingRadioElement);
