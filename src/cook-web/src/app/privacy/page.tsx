'use client';
import ZH_CN_PrivacyPolicy from './components/zh-cn-privacy.mdx';
import EN_PrivacyPolicy from './components/en-privacy.mdx';

import i18n from '@/i18n';

const privacyPolicies = {
  'zh-CN': ZH_CN_PrivacyPolicy,
  'en-US': EN_PrivacyPolicy,
  en: EN_PrivacyPolicy,
};

export default function PrivacyPage() {
  const PrivacyPolicy =
    privacyPolicies[i18n.language] || privacyPolicies['en-US'];
  return (
    <div className='h-screen flex flex-col'>
      <div className='flex-1 overflow-y-auto p-4'>
        <PrivacyPolicy />
      </div>
    </div>
  );
}
