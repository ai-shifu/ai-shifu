'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import { getBrowserTimeZone } from '@/lib/browser-timezone';
import { cn } from '@/lib/utils';

type AdminTimezoneHintProps = {
  namespace: string;
  textKey: string;
  as?: 'div' | 'p' | 'span';
  className?: string;
};

/*
 * Translation usage markers for scripts/check_translation_usage.py:
 * t('module.operationsCourse.timezoneHint')
 * t('module.operationsOrder.timezoneHint')
 * t('module.operationsPromotion.timezoneHint')
 * t('module.operationsUser.timezoneHint')
 * t('module.operationsUser.detail.timezoneHint')
 */

export default function AdminTimezoneHint({
  namespace,
  textKey,
  as = 'p',
  className,
}: AdminTimezoneHintProps) {
  const { t } = useTranslation(namespace);
  const [viewerTimeZone, setViewerTimeZone] = React.useState('UTC');

  React.useEffect(() => {
    const nextTimeZone = getBrowserTimeZone();
    if (nextTimeZone) {
      setViewerTimeZone(nextTimeZone);
    }
  }, []);

  const Component = as;

  return (
    <Component className={cn('text-sm text-muted-foreground', className)}>
      {t(textKey, {
        timezone: viewerTimeZone,
      })}
    </Component>
  );
}
