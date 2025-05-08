"use client"

import { useState } from "react"
import { ForgotPasswordCombined } from "@/components/auth/forgot-password-combined"
import { ForgotPasswordReset } from "@/components/auth/forgot-password-reset"
import { useToast } from "@/hooks/use-toast";
import { useTranslation } from 'react-i18next';
interface ForgotPasswordFormProps {
  onComplete: () => void
}

/**
 * Renders a two-step password reset form with internationalized notifications.
 *
 * Guides the user through verifying their email and resetting their password. Upon successful completion, displays a localized toast notification and invokes the provided completion callback.
 *
 * @param onComplete - Callback invoked after the password reset process finishes.
 */
export function ForgotPasswordForm({ onComplete }: ForgotPasswordFormProps) {
  const { t } = useTranslation();
   const { toast } = useToast()
  const [step, setStep] = useState<"verify" | "reset">("verify")
  const [email, setEmail] = useState("")

  const handleVerifyNext = (email: string) => {
    setEmail(email)
    setStep("reset")
  }

  const handleComplete = () => {
    toast({
      title: t('login.password-reset'),
      description: t('login.please-use-new-password'),
    })
    onComplete()
  }

  return (
    <div className="space-y-4">
      {step === "verify" && <ForgotPasswordCombined onNext={handleVerifyNext} />}

      {step === "reset" && (
        <ForgotPasswordReset email={email} onBack={() => setStep("verify")} onComplete={handleComplete} />
      )}
    </div>
  )
}
