'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { Loader2 } from 'lucide-react'
import apiService from '@/api'
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
interface ForgotPasswordVerifyProps {
  email: string
  onBack: () => void
  onNext: (otp: string) => void
}

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
        mail: email,
        language: i18n.language
      })

      if (response.code == 0) {
        setCountdown(60)
        toast({
          title: t('login.otp-resent'),
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
        mail_code: otp,
        language: i18n.language
      })

      if (response.code == 0) {
        // Token handled via login flow, no need to set manually here

        toast({
          title: t('login.verification-success'),
          description: t('login.verification-success-description')
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
          placeholder={t('login.otp-placeholder')}
          value={otp}
          onChange={e => setOtp(e.target.value)}
          disabled={isLoading}
        />
        {countdown > 0 ? (
          <p className='text-sm text-muted-foreground mt-1'>
            {t('login.seconds-later', { count: countdown })}
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
