import { Checkbox } from "@/components/ui/checkbox"

interface TermsCheckboxProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
}

export function TermsCheckbox({ checked, onCheckedChange, disabled = false }: TermsCheckboxProps) {
  return (
    <div className="flex items-center space-x-2">
      <Checkbox id="terms" checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
      <label
        htmlFor="terms"
        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
      >
        我已阅读并同意
        <a href="https://ai-shifu.com/useragreement" className="text-primary hover:underline mx-1" target="_blank">
          服务协议
        </a>
        &
        <a href="https://ai-shifu.com/privacypolicy" className="text-primary hover:underline mx-1" target="_blank">
          隐私政策
        </a>
      </label>
    </div>
  )
}
