import { useTranslation } from 'react-i18next';

export function BillingOverviewHero() {
  const { t } = useTranslation();

  return (
    <div className='space-y-4 text-center'>
      <div>
        <h1 className='text-[var(--base-foreground,#0A0A0A)] text-[length:var(--heading-lg-font-size,36px)] [font-weight:var(--heading-lg-font-weight,700)] leading-[var(--heading-lg-line-height,40px)]'>
          {t('module.billing.package.title')}
        </h1>
      </div>
    </div>
  );
}
