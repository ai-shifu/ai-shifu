'use client';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import ZH_CN_Agreement from '@/components/legals/ZhCnAgreement.mdx';
import EN_Agreement from '@/components/legals/EnAgreement.mdx';

import i18n, { normalizeLanguage } from '@/i18n';

const agreements = {
  'zh-CN': ZH_CN_Agreement,
  'en-US': EN_Agreement,
  'fr-FR': EN_Agreement,
  en: EN_Agreement,
};

const MOCK_ERROR_QUERY_KEY = 'mock_error';
const MOCK_ERROR_QUERY_VALUE = '1';
const MOCK_ERROR_MESSAGE =
  'Simulated cook-web client render failure: agreement page crashed while rendering legal content.';

function MockClientErrorTrigger() {
  const [shouldThrow, setShouldThrow] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setShouldThrow(params.get(MOCK_ERROR_QUERY_KEY) === MOCK_ERROR_QUERY_VALUE);
  }, []);

  if (shouldThrow) {
    throw new Error(MOCK_ERROR_MESSAGE);
  }

  return null;
}

export default function AgreementPage() {
  const { t } = useTranslation();
  const language = normalizeLanguage(i18n.language);
  const Agreement = agreements[language] || agreements['en-US'];
  const showEnglishFallbackNotice = language === 'fr-FR';

  return (
    <div className='flex h-dvh flex-col'>
      <MockClientErrorTrigger />
      <div className='flex-1 overflow-y-auto p-4'>
        {showEnglishFallbackNotice ? (
          <p className='mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900'>
            {t('common.core.legalFallbackEnglishNotice')}
          </p>
        ) : null}
        <Agreement />
      </div>
    </div>
  );
}
