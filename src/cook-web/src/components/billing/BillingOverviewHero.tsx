import { useTranslation } from 'react-i18next';

export function BillingOverviewHero() {
  const { t } = useTranslation();

  return (
    <div className='space-y-4 text-center'>
      <div className='space-y-5'>
        <h1 className='text-[var(--base-foreground,#0A0A0A)] text-[length:var(--heading-lg-font-size,36px)] [font-weight:var(--heading-lg-font-weight,700)] leading-[var(--heading-lg-line-height,40px)]'>
          {t('module.billing.package.title')}
        </h1>
        <p className='mx-auto max-w-4xl text-[var(--base-muted-foreground,#737373)] text-[length:var(--text-base-font-size,16px)] font-normal leading-[var(--text-base-line-height,24px)]'>
          {t('module.billing.package.subtitle')}
        </p>
      </div>
    </div>
  );
}
