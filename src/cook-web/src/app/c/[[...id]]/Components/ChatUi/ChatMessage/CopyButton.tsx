import styles from './CopyButton.module.scss';

import { memo, useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { CopyIcon } from 'lucide-react';

import clsx from 'clsx';
import { copyText } from '@/c-utils/textutils';
import { useTranslation } from 'react-i18next';

const TIMEOUT = 5000;

export const CopyButton = ({ content }) => {
  const [hasCopy, setHasCopy] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout>(undefined);
  const { t } = useTranslation('translation', { keyPrefix: 'c' });

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
      className={clsx(styles.copyButton, hasCopy ? styles.copyed : '', 'border-dashed')}
      variant="outline"
      onClick={onCopyClick}
    >
      <CopyIcon />
      {hasCopy ? t('chat.copySuccess') : t('chat.copyText')}
    </Button>
  );
};

export default memo(CopyButton);
