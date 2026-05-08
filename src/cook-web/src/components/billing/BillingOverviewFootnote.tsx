import { useTranslation } from 'react-i18next';

// Language-neutral typographic enumerators that anchor the footnote items to
// the matching table rows. Not user-facing copy, so they stay out of i18n.
const FOOTNOTE_ENUM_LEARNER = '①';
const FOOTNOTE_ENUM_VALIDITY = '②';

export function BillingOverviewFootnote() {
  const { t } = useTranslation();

  return (
    <div
      className='text-[length:var(--text-sm-font-size,14px)] leading-[var(--text-sm-line-height,20px)] text-[var(--base-muted-foreground,#737373)]'
      data-testid='billing-overview-footnote'
    >
      <ul className='space-y-3'>
        <li className='flex gap-2'>
          <span className='shrink-0 font-medium text-blue-600'>
            {FOOTNOTE_ENUM_LEARNER}
          </span>
          <div className='flex-1'>
            {t('module.billing.package.footnote.learnerEstimateIntro')}
            <ol className='mt-1 list-decimal space-y-1 pl-5'>
              <li>
                {t('module.billing.package.footnote.learnerEstimateScale')}
              </li>
              <li>
                {t('module.billing.package.footnote.learnerEstimateMode')}
              </li>
              <li>
                {t('module.billing.package.footnote.learnerEstimateModel')}
              </li>
            </ol>
          </div>
        </li>
        <li className='flex gap-2'>
          <span className='shrink-0 font-medium text-blue-600'>
            {FOOTNOTE_ENUM_VALIDITY}
          </span>
          <div className='flex-1'>
            {t('module.billing.package.footnote.validity')}
          </div>
        </li>
      </ul>
    </div>
  );
}
