import { Checkbox } from "@/components/ui/checkbox"
import { useTranslation } from 'react-i18next';
import { useRouter } from 'next/navigation';

interface TermsCheckboxProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
}

export function TermsCheckbox({ checked, onCheckedChange, disabled = false }: TermsCheckboxProps) {
  const { t } = useTranslation();
  const router = useRouter();
  return (
    <div className="flex items-center space-x-2">
      <Checkbox id="terms" checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
      <label
        htmlFor="terms"
        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
      >
        {t('login.i-have-read-and-agree-to-the')}
        <a onClick={() => {
          router.push('/agreement');
        }} className="text-primary hover:underline mx-1" >
          {t('login.service-agreement')}
        </a>
        &
        <a onClick={() => {
          router.push('/privacy');
        }}
         className="text-primary hover:underline mx-1" >
          {t('login.privacy-policy')}
        </a>
      </label>
    </div>
  )
}
