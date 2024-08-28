import { Button } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { memo } from 'react';
import { useState } from 'react';
import styles from './CopyButton.module.scss';
import { useRef } from 'react';
import classNames from 'classnames';
import { copyText } from 'Utils/textutils.js';

const TIMEOUT = 5000;

export const CopyButton = ({ content }) => {
  const [hasCopy, setHasCopy] = useState(false);
  const timeoutRef = useRef();

  const onCopyClick = () => {
    copyText(content);
    setHasCopy(true);

    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = setTimeout(() => setHasCopy(false), TIMEOUT);
  };

  return (
    <Button
      className={classNames(styles.copyButton, hasCopy ? styles.copyed : '')}
      type="dashed"
      size="small"
      icon={<CopyOutlined></CopyOutlined>}
      onClick={onCopyClick}
    >
      {hasCopy ? '已复制到剪切板' : '复制'}
    </Button>
  );
};

export default memo(CopyButton);