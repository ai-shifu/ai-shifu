import { Radio, Space } from 'antd';
import { useEffect, memo, useState, useCallback } from 'react';
import styles from './SettingRadioElement.module.scss';
import classNames from 'classnames';

export const SettingRadioElement = ({
  title = '',
  className = '',
  options = [],
  value = '',
  onChange = (e) => {},
}) => {
  const [curr, setCurr] = useState(value);

  useEffect(() => {
    setCurr(value);
  }, [value]);

  const _onChange = useCallback(
    (e) => {
      setCurr(e.target.value);
      onChange(e.target.value);
    },
    [setCurr, onChange],
  );

  return (
    <div className={classNames(styles.settingRadio, className)}>
      <div className={styles.title}>{title}</div>
      <div className={styles.inputWrapper}>
        <Radio.Group onChange={_onChange} value={curr}>
          <Space direction="vertical">
            {options.map((v) => {
              const { label, value } = v;
              return (
                <Radio
                  key={value}
                  value={value}
                  checked={value === curr}
                  className={styles.inputElement}
                >
                  {label}
                </Radio>
              );
            })}
          </Space>
        </Radio.Group>
      </div>
    </div>
  );
};

export default memo(SettingRadioElement);
