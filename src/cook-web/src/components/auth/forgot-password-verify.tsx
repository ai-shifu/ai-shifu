'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { Loader2 } from 'lucide-react'
import apiService from '@/api'
import { setToken } from '@/local/local'
import { useTranslation } from 'react-i18next';

interface ForgotPasswordVerifyProps {
  email: string
  onBack: () => void
  onNext: (otp: string) => void
}

/**
 * React component for verifying a one-time password (OTP) during the password reset process.
 *
 * Displays an input for entering the OTP sent to the user's email, manages a countdown timer for resending the OTP, and provides feedback on verification and resend attempts. All user-facing text is internationalized.
 *
 * @param email - The user's email address to which the OTP was sent.
 * @param onBack - Callback invoked when the user chooses to go back.
 * @param onNext - Callback invoked with the OTP upon successful verification.
 *
 * @returns The OTP verification UI for the password reset flow.
 *
 * @remark The countdown timer for resending the OTP is implemented using a state hook, which may not be the intended usage; a side effect hook is typically preferred for timers.
 */
export function ForgotPasswordVerify ({
  email,
  onBack,
  onNext
}: ForgotPasswordVerifyProps) {
  const { toast } = useToast()
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false)
  const [otp, setOtp] = useState('')
  const [countdown, setCountdown] = useState(60)

  useState(() => {
    const timer = setInterval(() => {
      setCountdown(prevCountdown => {
        if (prevCountdown <= 1) {
          clearInterval(timer)
          return 0
        }
        return prevCountdown - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  })

  const handleResendOtp = async () => {
    try {
      setIsLoading(true)

      const response = await apiService.sendMailCode({
        mail: email
      })

      if (response.code == 0) {
        setCountdown(60)
        toast({
          title: t('login.code-resent'),
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
      setIsLoading(false)
    }
  }

  const handleVerifyOtp = async () => {
    if (!otp) {
      toast({
        title: t('login.please-input-otp'),
        variant: 'destructive'
      })
      return
    }

    try {
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
        onNext(otp)
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
      setIsLoading(false)
    }
  }

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label htmlFor='otp'>{t('login.otp')}</Label>
        <Input
          id='otp'
          placeholder={t('login.please-input-otp')}
          value={otp}
          onChange={e => setOtp(e.target.value)}
          disabled={isLoading}
        />
        {countdown > 0 ? (
          <p className='text-sm text-muted-foreground mt-1'>
            {countdown} {t('login.seconds-later')}
          </p>
        ) : (
          <Button
            variant='link'
            className='p-0 h-auto text-sm h-8'
            onClick={handleResendOtp}
            disabled={isLoading}
          >
            {t('login.resend-otp')}
          </Button>
        )}
      </div>
      <div className='flex justify-between'>
        <Button
          variant='outline'
          onClick={onBack}
          disabled={isLoading}
          className='h-8'
        >
          {t('login.back')}
        </Button>
        <Button onClick={handleVerifyOtp} disabled={isLoading} className='h-8'>
          {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
          {t('login.verify')}
        </Button>
      </div>
    </div>
  )
}
