'use client';
import ZH_CN_Agreement from './Contents/zh_CN_agreement.mdx';
import EN_Agreement from './Contents/en_agreement.mdx';

import i18n from '@/i18n';

const agreements = {
  'zh-CN': ZH_CN_Agreement,
  'en-US': EN_Agreement,
  'en': EN_Agreement,
};


export default function AgreementPage () {

  const Agreement = agreements[i18n.language] || agreements['en-US'];
  return (
    <div className="h-screen flex flex-col">
      <div className='flex-1 overflow-y-auto p-4'>
        <Agreement />
      </div>
    </div>
  );
};
