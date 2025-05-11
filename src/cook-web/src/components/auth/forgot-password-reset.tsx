"use client"

import type React from "react"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useToast } from "@/hooks/use-toast";
import { Loader2 } from "lucide-react"
import apiService from "@/api"
import { checkPasswordStrength } from "@/lib/validators"
import { PasswordStrengthIndicator } from "./password-strength-indicator"
import { useTranslation } from 'react-i18next';
interface ForgotPasswordResetProps {
  email: string
  onBack: () => void
  onComplete: () => void
}

/**
 * React component for resetting a user's password with validation and internationalized UI.
 *
 * Renders input fields for a new password and its confirmation, validates password strength and matching, and submits the new password to the backend. Displays feedback and error messages using toast notifications and disables actions during loading.
 *
 * @param email - The user's email address for which the password is being reset.
 * @param onBack - Callback invoked when the user chooses to navigate back.
 * @param onComplete - Callback invoked after a successful password reset.
 */
export function ForgotPasswordReset({ email, onBack, onComplete }: ForgotPasswordResetProps) {
   const { toast } = useToast()
   const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false)
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [passwordError, setPasswordError] = useState("")
  const [confirmPasswordError, setConfirmPasswordError] = useState("")
  const [passwordStrength, setPasswordStrength] = useState({
    score: 0,
    feedback: [] as string[],
    isValid: false,
  })

  const validatePassword = (password: string) => {
    if (!password) {
      // setPasswordError("请输入密码")
      return false
    }

    const strength = checkPasswordStrength(password)
    setPasswordStrength(strength)

    if (!strength.isValid) {
      // setPasswordError("密码强度不足")
      return false
    }

    setPasswordError("")
    return true
  }

  const validateConfirmPassword = (confirmPassword: string) => {
    if (!confirmPassword) {
      setConfirmPasswordError(t('login.please-confirm-password'))
      return false
    }

    if (confirmPassword !== password) {
      setConfirmPasswordError(t('login.password-not-match'))
      return false
    }

    setConfirmPasswordError("")
    return true
  }

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setPassword(value)
    validatePassword(value)

    if (confirmPassword) {
      validateConfirmPassword(confirmPassword)
    }
  }

  const handleConfirmPasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setConfirmPassword(value)
    if (value) {
      validateConfirmPassword(value)
    } else {
      setConfirmPasswordError("")
    }
  }

  const handleResetPassword = async () => {
    const isPasswordValid = validatePassword(password)
    const isConfirmPasswordValid = validateConfirmPassword(confirmPassword)

    if (!isPasswordValid || !isConfirmPasswordValid) {
      return
    }

    try {
      setIsLoading(true)

      const response = await apiService.setPassword({
        mail: email,
        raw_password: password,
      })


      if (response.code == 0) {
        toast({
          title: t('login.password-reset'),
          description: t('login.please-use-new-password'),
        })
        onComplete()
      } else {
        toast({
          title: t('login.reset-password-failed'),
          description: t('login.please-try-again-later'),
          variant: "destructive",
        })
      }
    } catch (error: any) {
      toast({
        title: t('login.reset-password-failed'),
        description: error.message || t('login.network-error'),
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="new-password" className={passwordError ? "text-red-500" : ""}>
          {t('login.new-password')}
        </Label>
        <Input
          id="new-password"
          type="password"
          placeholder={t('login.new-password-placeholder')}
          value={password}
          onChange={handlePasswordChange}
          disabled={isLoading}
          className={passwordError ? "border-red-500 focus-visible:ring-red-500" : ""}
        />
        <PasswordStrengthIndicator score={passwordStrength.score} feedback={passwordStrength.feedback} />
        {passwordError && <p className="text-xs text-red-500">{passwordError}</p>}
      </div>
      <div className="space-y-2">
        <Label htmlFor="confirm-new-password" className={confirmPasswordError ? "text-red-500" : ""}>
          {t('login.confirm-new-password')}
        </Label>
        <Input
          id="confirm-new-password"
          type="password"
          placeholder={t('login.confirm-new-password-placeholder')}
          value={confirmPassword}
          onChange={handleConfirmPasswordChange}
          disabled={isLoading}
          className={confirmPasswordError ? "border-red-500 focus-visible:ring-red-500" : ""}
        />
        {confirmPasswordError && <p className="text-xs text-red-500">{confirmPasswordError}</p>}
      </div>
      <div className="flex justify-between">
        <Button className="h-8" variant="outline" onClick={onBack} disabled={isLoading}>
          {t('login.back')}
        </Button>
        <Button
          onClick={handleResetPassword}
          className="h-8"
          disabled={
            isLoading ||
            !password ||
            !confirmPassword ||
            !!passwordError ||
            !!confirmPasswordError ||
            !passwordStrength.isValid
          }
        >
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
          {t('login.reset-password')}
        </Button>
      </div>
    </div>
  )
}
