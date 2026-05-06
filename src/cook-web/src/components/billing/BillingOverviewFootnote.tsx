import { useTranslation } from 'react-i18next';

export function BillingOverviewFootnote() {
  const { t } = useTranslation();

  return (
    <div
      className='text-[length:var(--text-sm-font-size,14px)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'
      data-testid='billing-overview-footnote'
    >
      <ul className='list-disc space-y-2 pl-5'>
        <li>{t('module.billing.package.footnote.contactUs')}</li>
        <li>{t('module.billing.package.footnote.learnerEstimate')}</li>
      </ul>
    </div>
  );
}
