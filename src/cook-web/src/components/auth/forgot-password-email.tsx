'use client'

import type React from 'react'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { Loader2 } from 'lucide-react'
import apiService from '@/api'
import { isValidEmail } from '@/lib/validators'
import { useTranslation } from 'react-i18next';

interface ForgotPasswordEmailProps {
  onNext: (email: string) => void
}

/**
 * React component for handling the email input and OTP sending process in a "forgot password" workflow.
 *
 * Renders an email input field with validation and a button to send a verification code (OTP) to the provided email address. Displays error messages and loading indicators as appropriate. On successful OTP sending, invokes the {@link onNext} callback with the entered email.
 *
 * @param onNext - Callback invoked with the email address after a successful OTP send.
 */
export function ForgotPasswordEmail ({ onNext }: ForgotPasswordEmailProps) {
  const { toast } = useToast()
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState('')

  const validateEmail = (email: string) => {
    if (!email) {
      setEmailError(t('login.email-error'))
      return false
    }

    if (!isValidEmail(email)) {
      setEmailError(t('login.email-error'))
      return false
    }

    setEmailError('')
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

  const handleSendOtp = async () => {
    if (!validateEmail(email)) {
      return
    }

    try {
      setIsLoading(true)

      const response = await apiService.sendMailCode({
        mail: email
      })

      if (response.code==0) {
        toast({
          title: t('login.code-sent'),
          description: t('login.please-check-your-email')
        })
        onNext(email)
      } else {
        toast({
          title: t('login.send-otp-failed'),
          description: t('login.please-try-again-later'),
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
      setIsLoading(false)
    }
  }

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label htmlFor='email' className={emailError ? 'text-red-500' : ''}>
          {t('login.email')}
        </Label>
        <Input
          id='email'
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

      <Button
        className='w-full h-8'
        onClick={handleSendOtp}
        disabled={isLoading || !email || !!emailError}
      >
        {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
        {t('login.get-otp')}
      </Button>
    </div>
  )
}
