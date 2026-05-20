'use client';
import { useTranslation } from 'react-i18next';

import ZH_CN_PrivacyPolicy from '@/components/legals/ZhCnPrivacy.mdx';
import EN_PrivacyPolicy from '@/components/legals/EnPrivacy.mdx';

import i18n, { normalizeLanguage } from '@/i18n';

const privacyPolicies = {
  'zh-CN': ZH_CN_PrivacyPolicy,
  'en-US': EN_PrivacyPolicy,
  'fr-FR': EN_PrivacyPolicy,
  en: EN_PrivacyPolicy,
};

export default function PrivacyPage() {
  const { t } = useTranslation();
  const language = normalizeLanguage(i18n.language);
  const PrivacyPolicy = privacyPolicies[language] || privacyPolicies['en-US'];
  const showEnglishFallbackNotice = language === 'fr-FR';

  return (
    <div className='h-screen flex flex-col'>
      <div className='flex-1 overflow-y-auto p-4'>
        {showEnglishFallbackNotice ? (
          <p className='mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900'>
            {t('common.core.legalFallbackEnglishNotice')}
          </p>
        ) : null}
        <PrivacyPolicy />
      </div>
    </div>
  );
}
