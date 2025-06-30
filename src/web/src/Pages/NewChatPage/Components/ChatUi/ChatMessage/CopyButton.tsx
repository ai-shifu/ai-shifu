import { Button } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { memo, useState, useRef } from 'react';
import styles from './CopyButton.module.scss';
import classNames from 'classnames';
import { copyText } from 'Utils/textutils';
import { useTranslation } from 'react-i18next';

const TIMEOUT = 5000;

interface CopyButtonProps {
  content: string;
}

export const CopyButton = ({ content }: CopyButtonProps) => {
  const [hasCopied, setHasCopied] = useState<boolean>(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { t } = useTranslation();

  const onCopyClick = async (): Promise<void> => {
    try {
      await copyText(content);
      setHasCopied(true);

      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => setHasCopied(false), TIMEOUT);
    } catch (error) {
      console.error('Failed to copy text:', error);
    }
  };

  return (
    <Button
      className={classNames(styles.copyButton, hasCopied ? styles.copied : '')}
      type="dashed"
      size="small"
      icon={<CopyOutlined />}
      onClick={onCopyClick}
    >
      {hasCopied ? t('chat.copySuccess') : t('chat.copyText')}
    </Button>
  );
};

export default memo(CopyButton);
