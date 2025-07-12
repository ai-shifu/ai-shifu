'use client'

import type React from 'react'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { Loader2 } from 'lucide-react'
import { TermsCheckbox } from '@/components/terms-checkbox'
import apiService from '@/api'
import { isValidEmail, checkPasswordStrength } from '@/lib/validators'
import { PasswordStrengthIndicator } from './password-strength-indicator'
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
interface EmailRegisterProps {
  onRegisterSuccess: () => void
}

export function EmailRegister ({ onRegisterSuccess }: EmailRegisterProps) {
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [isSendingCode, setIsSendingCode] = useState(false)
  const [isVerifying, setIsVerifying] = useState(false)
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [email, setEmail] = useState('')
  const [emailOtp, setEmailOtp] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [step, setStep] = useState<'verify' | 'password'>('verify')
  const [countdown, setCountdown] = useState(0)
  const [showOtpInput, setShowOtpInput] = useState(false)

  const [emailError, setEmailError] = useState('')
  const [otpError, setOtpError] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [confirmPasswordError, setConfirmPasswordError] = useState('')
  const { t } = useTranslation();
  const [passwordStrength, setPasswordStrength] = useState({
    score: 0,
    feedback: [] as string[],
    isValid: false
  })

  const validateEmail = (email: string) => {
    if (!email) {
      setEmailError(t('login.email-empty'))
      return false
    }

    if (!isValidEmail(email)) {
      setEmailError(t('login.email-error'))
      return false
    }

    setEmailError('')
    return true
  }

  const validateOtp = (otp: string) => {
    if (!otp) {
      setOtpError(t('login.otp-error'))
      return false
    }

    setOtpError('')
    return true
  }

  const validatePassword = (password: string) => {
    if (!password) {
      setPasswordError(t('login.password-error'))
      return false
    }

    const strength = checkPasswordStrength(password)
    setPasswordStrength(strength)

    if (!strength.isValid) {
      return false
    }

    setPasswordError('')
    return true
  }

  const validateConfirmPassword = (confirmPassword: string) => {
    if (!confirmPassword) {
      setConfirmPasswordError(t('login.confirm-password-error'))
      return false
    }

    if (confirmPassword !== password) {
      setConfirmPasswordError(t('login.confirm-password-error'))
      return false
    }

    setConfirmPasswordError('')
    return true
  }

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setEmail(value)
    if (value) {
      validateEmail(value)
    } else {
      setEmailError('')
    }
  }

  const handleOtpChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setEmailOtp(value)
    if (value) {
      validateOtp(value)
    } else {
      setOtpError('')
    }
  }

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setPassword(value)
    validatePassword(value)

    if (confirmPassword) {
      validateConfirmPassword(confirmPassword)
    }
  }

  const handleConfirmPasswordChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const value = e.target.value
    setConfirmPassword(value)
    if (value) {
      validateConfirmPassword(value)
    } else {
      setConfirmPasswordError('')
    }
  }

  const handleSendEmailOtp = async () => {
    if (!validateEmail(email)) {
      return
    }

    if (!termsAccepted) {
      toast({
        title: t('login.terms-error'),
        variant: 'destructive'
      })
      return
    }

    try {
      setIsSendingCode(true)
      setIsLoading(true)

      const response = await apiService.sendMailCode({
        mail: email
      })

      if (response.code==0) {
        setShowOtpInput(true)
        setCountdown(60)
        const timer = setInterval(() => {
          setCountdown(prevCountdown => {
            if (prevCountdown <= 1) {
              clearInterval(timer)
              return 0
            }
            return prevCountdown - 1
          })
        }, 1000)

        toast({
          title: t('login.otp-sent'),
          description: t('login.please-check-your-email')
        })
      } else {
        toast({
          title: t('login.send-otp-failed'),
          description: response.msg || t('login.please-try-again-later'),
          variant: 'destructive'
        })
      }
    } catch (error: any) {
      toast({
        title: t('login.send-otp-failed'),
        description: error.message || t('login.network-error'),
        variant: 'destructive'
      })
    } finally {
      setIsSendingCode(false)
      setIsLoading(false)
    }
  }

  const handleVerifyEmailOtp = async () => {
    if (!validateEmail(email)) {
      return
    }

    if (!validateOtp(emailOtp)) {
      return
    }

    if (!termsAccepted) {
      toast({
        title: t('login.terms-error'),
        variant: 'destructive'
      })
      return
    }

    try {
      setIsVerifying(true)
      setIsLoading(true)

      const response = await apiService.verifyMailCode({
        mail: email,
        mail_code: emailOtp,
        language: i18n.language
      })
      if (response.code==0) {
        // Token handled via login flow, no need to set manually here
        setStep('password')
        setPassword('')
        setConfirmPassword('')
        setPasswordError('')
        setConfirmPasswordError('')
        setPasswordStrength({
          score: 0,
          feedback: [],
          isValid: false
        })
        toast({
          title: t('login.email-verified'),
          description: t('login.please-set-your-password')
        })
      } else {
        toast({
          title: t('login.verification-failed'),
          description: t('login.otp-error'),
          variant: 'destructive'
        })
      }
    } catch (error: any) {
      toast({
        title: t('login.verification-failed'),
        description: error.message || t('login.network-error'),
        variant: 'destructive'
      })
    } finally {
      setIsVerifying(false)
      setIsLoading(false)
    }
  }

  const handleCompleteEmailRegistration = async () => {
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

      if (response.code==0) {
        toast({
          title: t('login.register-success')
        })
        onRegisterSuccess()
      } else {
        toast({
          title: t('login.register-failed'),
          description: t('login.please-try-again-later'),
          variant: 'destructive'
        })
      }
    } catch (error: any) {
      toast({
        title: t('login.register-failed'),
        description: error.message || t('login.network-error'),
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className='space-y-4'>
      {step === 'verify' && (
        <div className='space-y-4'>
          <div className='space-y-2'>
            <Label htmlFor='register-email'>{t('login.email')}</Label>
            <Input
              id='register-email'
              type='email'
              placeholder={t('login.email-placeholder')}
              value={email}
              onChange={handleEmailChange}
              disabled={isLoading}
              className={
                emailError ? 'border-red-500 focus-visible:ring-red-500' : ''
              }
            />
            {emailError && <p className='text-xs text-red-500'>{emailError}</p>}
          </div>

          <div className='space-y-2'>
            <div className='flex space-x-2'>
              <Input
                id='register-email-otp'
                placeholder={t('login.otp-placeholder')}
                value={emailOtp}
                onChange={handleOtpChange}
                disabled={isLoading || !email || !!emailError ||  !showOtpInput}
                className={`flex-1 ${
                  otpError ? 'border-red-500 focus-visible:ring-red-500' : ''
                }`}
              />
              <Button
                onClick={handleSendEmailOtp}
                disabled={
                  isLoading ||
                  !email ||
                  !!emailError ||
                  countdown > 0
                }
                className='whitespace-nowrap h-8'
              >
                {isSendingCode && !showOtpInput ? (
                  <Loader2 className='h-4 w-4 animate-spin mr-2' />
                ) : countdown > 0 ? (
                  t('login.seconds-later', { count: countdown })
                ) : (
                  t('login.get-otp')
                )}
              </Button>
            </div>
            {otpError && <p className='text-xs text-red-500'>{otpError}</p>}
          </div>

          <TermsCheckbox
            checked={termsAccepted}
            onCheckedChange={setTermsAccepted}
            disabled={isLoading}
          />

          <Button
            className='w-full h-8'
            onClick={handleVerifyEmailOtp}
            disabled={
              isLoading ||
              !email ||
              !!emailError ||
              !emailOtp ||
              !!otpError ||
              !termsAccepted
            }
          >
            {isVerifying ? (
              <Loader2 className='h-4 w-4 animate-spin mr-2' />
            ) : null}
            {t('login.next')}
          </Button>
        </div>
      )}

      {step === 'password' && (
        <div className='space-y-4'>
          <div className='space-y-2'>
            <Label
              htmlFor='register-password'
              className={passwordError ? 'text-red-500' : ''}
            >
              {t('login.password')}
            </Label>
            <Input
              id='register-password'
              type='password'
              placeholder={t('login.password-placeholder')}
              value={password}
              onChange={handlePasswordChange}
              disabled={isLoading}
              className={
                passwordError ? 'border-red-500 focus-visible:ring-red-500' : ''
              }
            />
            <PasswordStrengthIndicator
              feedback={passwordStrength.feedback}
            />
            {passwordError && (
              <p className='text-xs text-red-500'>{passwordError}</p>
            )}
          </div>
          <div className='space-y-2'>
            <Label
              htmlFor='confirm-password'
              className={confirmPasswordError ? 'text-red-500' : ''}
            >
              {t('login.confirm-password')}
            </Label>
            <Input
              id='confirm-password'
              type='password'
              placeholder={t('login.confirm-password-placeholder')}
              value={confirmPassword}
              onChange={handleConfirmPasswordChange}
              disabled={isLoading}
              className={
                confirmPasswordError
                  ? 'border-red-500 focus-visible:ring-red-500'
                  : ''
              }
            />
            {confirmPasswordError && (
              <p className='text-xs text-red-500'>{confirmPasswordError}</p>
            )}
          </div>
          <div className='flex justify-between'>
            <Button
              variant='outline'
              className='h-8'
              onClick={() => setStep('verify')}
              disabled={isLoading}
            >
              {t('login.back')}
            </Button>
            <Button
              className='h-8'
              onClick={handleCompleteEmailRegistration}
              disabled={
                isLoading ||
                !password ||
                !confirmPassword ||
                !!passwordError ||
                !!confirmPasswordError ||
                !passwordStrength.isValid
              }
            >
              {isLoading ? (
                <Loader2 className='h-4 w-4 animate-spin mr-2' />
              ) : null}
              {t('login.complete-registration')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
