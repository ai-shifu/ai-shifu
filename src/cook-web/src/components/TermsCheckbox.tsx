import type { MouseEvent, TouchEvent } from 'react';
import { Checkbox } from '@/components/ui/Checkbox';
import { cn } from '@/lib/utils';
import { Trans, useTranslation } from 'react-i18next';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';

interface TermsCheckboxProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export function TermsCheckbox({
  checked,
  onCheckedChange,
  disabled = false,
  className,
}: TermsCheckboxProps) {
  const { t, i18n } = useTranslation();
  const legalUrls = useEnvStore((state: EnvStoreState) => state.legalUrls);
  const stopLabelInteraction = (
    event: MouseEvent<HTMLAnchorElement> | TouchEvent<HTMLAnchorElement>,
  ) => {
    // Prevent the label from swallowing anchor clicks so the links remain clickable
    event.stopPropagation();
  };

  // Get current language URL
  const currentLang = (i18n.language || 'en-US') as 'zh-CN' | 'en-US';
  const agreementUrl = legalUrls?.agreement?.[currentLang] || '';
  const privacyUrl = legalUrls?.privacy?.[currentLang] || '';
  return (
    <div className={cn('flex flex-row items-start gap-2 text-left', className)}>
      <Checkbox
        id='terms'
        checked={checked}
        onCheckedChange={value => onCheckedChange(Boolean(value))}
        disabled={disabled}
        className='mt-[1px]'
      />
      <label
        htmlFor='terms'
        className='block text-left text-sm font-medium leading-snug peer-disabled:cursor-not-allowed peer-disabled:opacity-70'
      >
        <Trans
          i18nKey='module.auth.readAndAgree'
          components={{
            serviceAgreement: agreementUrl ? (
              <a
                href={agreementUrl}
                target='_blank'
                rel='noopener noreferrer'
                className='text-primary hover:underline mx-1'
                onClick={stopLabelInteraction}
                onTouchStart={stopLabelInteraction}
              />
            ) : (
              <span className='mx-1' />
            ),
            privacyPolicy: privacyUrl ? (
              <a
                href={privacyUrl}
                target='_blank'
                rel='noopener noreferrer'
                className='text-primary hover:underline mx-1'
                onClick={stopLabelInteraction}
                onTouchStart={stopLabelInteraction}
              />
            ) : (
              <span className='mx-1' />
            ),
          }}
          values={{
            serviceLabel: t('module.auth.serviceAgreement'),
            privacyLabel: t('module.auth.privacyPolicy'),
          }}
        />
      </label>
    </div>
  );
}
