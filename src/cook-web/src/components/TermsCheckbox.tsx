import { Checkbox } from '@/components/ui/Checkbox';
import { Trans, useTranslation } from 'react-i18next';

interface TermsCheckboxProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function TermsCheckbox({
  checked,
  onCheckedChange,
  disabled = false,
}: TermsCheckboxProps) {
  const { t } = useTranslation();
  return (
    <div className='flex items-center space-x-2'>
      <Checkbox
        id='terms'
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
      />
      <label
        htmlFor='terms'
        className='text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70'
      >
        <Trans
          i18nKey='auth.readAndAgree'
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
            serviceLabel: t('auth.serviceAgreement'),
            privacyLabel: t('auth.privacyPolicy'),
          }}
        />
      </label>
    </div>
  );
}
