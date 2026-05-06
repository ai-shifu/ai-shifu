import { InformationCircleIcon } from '@heroicons/react/24/outline';
import { useTranslation } from 'react-i18next';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { BillingNoticeCallout } from './BillingNoticeCallout';

export function BillingOverviewFootnote() {
  const { t } = useTranslation();

  return (
    <BillingNoticeCallout testId='billing-overview-footnote'>
      <li>{t('module.billing.package.footnote.contactUs')}</li>
      <li>
        {t('module.billing.package.footnote.learnerEstimate')}
        <TooltipProvider delayDuration={0}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type='button'
                className='ml-1 inline-flex h-4 w-4 cursor-help items-center justify-center align-middle text-[var(--base-muted-foreground,#737373)] transition-colors hover:text-[var(--base-foreground,#0A0A0A)] focus-visible:text-[var(--base-foreground,#0A0A0A)] focus-visible:outline-none'
                data-testid='billing-overview-footnote-learner-estimate-tip'
              >
                <InformationCircleIcon className='h-4 w-4' />
              </button>
            </TooltipTrigger>
            <TooltipContent className='max-w-xs leading-5'>
              {t('module.billing.package.footnote.learnerEstimateTip')}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </li>
    </BillingNoticeCallout>
  );
}
