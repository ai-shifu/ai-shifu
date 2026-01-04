'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Loading from '@/components/loading';
import { useI18nLoadingStore } from '@/store/useI18nLoadingStore';

const isUnsupportedIOSVersion = () => {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  const isIOSDevice =
    /iP(hone|od|ad)/i.test(ua) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (!isIOSDevice) return false;
  const versionMatch = ua.match(/OS (\d+)[._]/i);
  const majorVersion = versionMatch ? Number.parseInt(versionMatch[1], 10) : 0;
  return majorVersion > 0 && majorVersion <= 15;
};

const UnsupportedIOSNotice = () => {
  const { t } = useTranslation();
  const isI18nLoading = useI18nLoadingStore(state => state.isLoading);
  const [visible, setVisible] = useState(false);
  const line1 = t('common.core.unsupportedIOSMessageLine1', {
    defaultValue: 'Your iOS version is not supported.',
  });
  const line2 = t('common.core.unsupportedIOSMessageLine2', {
    defaultValue:
      'Please upgrade to the latest version (>=16) before accessing.',
  });

  useEffect(() => {
    if (isUnsupportedIOSVersion()) {
      setVisible(true);
    }
  }, []);

  if (!visible) return null;

  if (isI18nLoading) {
    return (
      <div className='fixed inset-0 z-[11000] flex items-center justify-center bg-white'>
        <Loading />
      </div>
    );
  }

  return (
    <div className='fixed inset-0 z-[11000] flex items-center justify-center bg-white/95 px-6 py-8 backdrop-blur'>
      <div className='mx-auto max-w-lg rounded-2xl bg-white p-6 text-center'>
        <p className='text-lg font-semibold text-neutral-900'>
          {t('common.core.unsupportedIOSTitle', {
            defaultValue: 'System update required',
          })}
        </p>
        <p className='mt-3 text-sm text-neutral-700 leading-relaxed'>
          {line1}
          <br />
          {line2}
        </p>
      </div>
    </div>
  );
};

export default UnsupportedIOSNotice;
