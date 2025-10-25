import { Checkbox } from '@/components/ui/Checkbox';
import { cn } from '@/lib/utils';
import { Trans, useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-2 text-center sm:flex-row sm:items-center sm:gap-2 sm:text-left',
        className,
      )}
    >
      <Checkbox
        id='terms'
        checked={checked}
        onCheckedChange={value => onCheckedChange(Boolean(value))}
        disabled={disabled}
      />
      <label
        htmlFor='terms'
        className='block text-center text-sm font-medium leading-snug peer-disabled:cursor-not-allowed peer-disabled:opacity-70 sm:text-left'
      >
        <Trans
          i18nKey='module.auth.readAndAgree'
          components={{
            serviceAgreement: (
              <a
                href='/agreement'
                target='_blank'
                rel='noopener noreferrer'
                className='text-primary hover:underline mx-1'
              />
            ),
            privacyPolicy: (
              <a
                href='/privacy'
                target='_blank'
                rel='noopener noreferrer'
                className='text-primary hover:underline mx-1'
              />
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
