import { Checkbox } from "@/components/ui/checkbox"
import { useTranslation } from 'react-i18next';
interface TermsCheckboxProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
}

/****
 * Renders a checkbox with a localized label for agreeing to the service agreement and privacy policy.
 *
 * The label includes translated text and links to the service agreement and privacy policy, both opening in a new tab. The checkbox state and disabled status are controlled via props.
 *
 * @param checked - Whether the checkbox is checked.
 * @param onCheckedChange - Callback invoked with the new checked state when the checkbox is toggled.
 * @param disabled - If true, disables the checkbox and label interaction.
 */
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
