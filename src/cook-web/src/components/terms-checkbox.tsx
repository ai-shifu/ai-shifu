import { Checkbox } from "@/components/ui/checkbox"
import { useTranslation } from 'react-i18next';
interface TermsCheckboxProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
}

export function TermsCheckbox({ checked, onCheckedChange, disabled = false }: TermsCheckboxProps) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center space-x-2">
      <Checkbox id="terms" checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
      <label
        htmlFor="terms"
        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
      >
        {t('login.i-have-read-and-agree-to-the')}
        <a href="https://ai-shifu.com/useragreement" className="text-primary hover:underline mx-1" target="_blank">
          {t('login.service-agreement')}
        </a>
        &
        <a href="https://ai-shifu.com/privacypolicy" className="text-primary hover:underline mx-1" target="_blank">
          {t('login.privacy-policy')}
        </a>
      </label>
    </div>
  )
}
