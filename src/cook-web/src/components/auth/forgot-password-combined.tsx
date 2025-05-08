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
import { setToken } from '@/local/local'
import { useTranslation } from 'react-i18next';

interface ForgotPasswordCombinedProps {
  onNext: (email: string, otp: string) => void
}

/**
 * React component for a combined email and OTP-based password recovery flow.
 *
 * Renders input fields for email and OTP, manages validation, handles sending and verifying OTP codes via API, and provides user feedback through loading states and toast notifications. Proceeds to the next step upon successful OTP verification.
 *
 * @param onNext - Callback invoked with the email and OTP after successful verification.
 */
export function ForgotPasswordCombined ({
  onNext
}: ForgotPasswordCombinedProps) {
  const { t } = useTranslation();
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [isSendingCode, setIsSendingCode] = useState(false)
  const [isVerifying, setIsVerifying] = useState(false)
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [emailError, setEmailError] = useState('')
  const [otpError, setOtpError] = useState('')
  const [countdown, setCountdown] = useState(0)
  const [codeSent, setCodeSent] = useState(false)

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

  const validateOtp = (otp: string) => {
    if (!otp) {
      setOtpError(t('login.otp-error'))
      return false
    }

    setOtpError('')
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
    setOtp(value)
    if (value) {
      validateOtp(value)
    } else {
      setOtpError('')
    }
  }

  const handleSendOtp = async () => {
    if (!validateEmail(email)) {
      return
    }

    try {
      setIsSendingCode(true)

      const response = await apiService.sendMailCode({
        mail: email
      })

      if (response.code == 0) {
        setCodeSent(true)
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
          title: t('login.code-sent'),
          description: t('login.please-check-your-email')
        })
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
      setIsSendingCode(false)
    }
  }

  const handleVerifyOtp = async () => {
    if (!validateEmail(email)) {
      return
    }

    if (!validateOtp(otp)) {
      return
    }

    try {
      setIsVerifying(true)
      setIsLoading(true)

      const response = await apiService.verifyMailCode({
        mail: email,
        mail_code: otp
      })

      if (response.code == 0) {
        setToken(response.data.token)
        toast({
          title: t('login.verification-success'),
          description: t('login.please-set-new-password')
        })
        onNext(email, otp)
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

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label htmlFor='email' className={emailError ? 'text-red-500' : ''}>
          {t('login.email')}
        </Label>
        <div className='flex space-x-2'>
          <Input
            id='email'
            type='email'
            placeholder={t('login.email-placeholder')}
            value={email}
            onChange={handleEmailChange}
            disabled={isLoading}
            className={`flex-1 ${
              emailError ? 'border-red-500 focus-visible:ring-red-500' : ''
            }`}
          />
          <Button
            onClick={handleSendOtp}
            disabled={isLoading || !email || !!emailError || countdown > 0}
            className='whitespace-nowrap h-8'
          >
            {isSendingCode ? (
              <Loader2 className='h-4 w-4 animate-spin mr-2' />
            ) : countdown > 0 ? (
              `${countdown}`+t('login.seconds-later')
            ) : (
              t('login.get-otp')
            )}
          </Button>
        </div>
        {emailError && <p className='text-xs text-red-500'>{emailError}</p>}
      </div>

      <div className='space-y-2'>
        <Label htmlFor='otp' className={otpError ? 'text-red-500' : ''}>
          {t('login.otp')}
        </Label>
        <Input
          id='otp'
          placeholder={t('login.otp-placeholder')}
          value={otp}
          onChange={handleOtpChange}
          disabled={isLoading || !codeSent}
          className={
            otpError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {otpError && <p className='text-xs text-red-500'>{otpError}</p>}
      </div>

      <Button
        className='w-full h-8'
        onClick={handleVerifyOtp}
        disabled={
          isLoading || !email || !!emailError || !otp || !!otpError || !codeSent
        }
      >
        {isVerifying ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
        {t('login.next')}
      </Button>
    </div>
  )
}
