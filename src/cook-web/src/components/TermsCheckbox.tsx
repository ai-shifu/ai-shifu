import { Checkbox } from '@/components/ui/Checkbox';
import { useTranslation } from 'react-i18next';

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
        {t('auth.readAndAgree')}
        <a
          href='/agreement'
          target='_blank'
          rel='noopener noreferrer'
          className='text-primary hover:underline mx-1'
        >
          {t('auth.serviceAgreement')}
        </a>
        &
        <a
          href='/privacy'
          target='_blank'
          rel='noopener noreferrer'
          className='text-primary hover:underline mx-1'
        >
          {t('auth.privacyPolicy')}
        </a>
      </label>
    </div>
  );
}
