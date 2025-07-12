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
import { isValidPhoneNumber } from '@/lib/validators'
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
interface PhoneRegisterProps {
  onRegisterSuccess: () => void
}

export function PhoneRegister ({ onRegisterSuccess }: PhoneRegisterProps) {
  const { t } = useTranslation();
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [phoneNumber, setPhoneNumber] = useState('')
  const [phoneOtp, setPhoneOtp] = useState('')
  const [showPhoneOtpInput, setShowPhoneOtpInput] = useState(false)
  const [phoneCountdown, setPhoneCountdown] = useState(0)
  // const [username, setUsername] = useState('')
  // const [name, setName] = useState('')
  const [phoneError, setPhoneError] = useState('')
  const [otpError, setOtpError] = useState('')

  const validatePhone = (phone: string) => {
    if (!phone) {
      setPhoneError(t('login.phone-error'))
      return false
    }

    if (!isValidPhoneNumber(phone)) {
      setPhoneError(t('login.phone-error'))
      return false
    }

    setPhoneError('')
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

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setPhoneNumber(value)
    if (value) {
      validatePhone(value)
    } else {
      setPhoneError('')
    }
  }

  const handleOtpChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setPhoneOtp(value)
    if (value) {
      validateOtp(value)
    } else {
      setOtpError('')
    }
  }

  const handleSendPhoneOtp = async () => {
    if (!validatePhone(phoneNumber)) {
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
      setIsLoading(true)

      const response = await apiService.sendSmsCode({
        mobile: phoneNumber,
        language: i18n.language
      })


      if (response.code==0) {
        setShowPhoneOtpInput(true)
        setPhoneCountdown(60)
        const timer = setInterval(() => {
          setPhoneCountdown(prevCountdown => {
            if (prevCountdown <= 1) {
              clearInterval(timer)
              return 0
            }
            return prevCountdown - 1
          })
        }, 1000)

        toast({
          title: t('login.otp-sent'),
          description: t('login.please-check-your-phone-sms')
        })
      } else {
        toast({
          title: t('login.send-otp-failed'),
          description: response.msg || t('login.network-error'),
          variant: 'destructive'
        })
      }
    } catch {
      toast({
        title: t('login.send-otp-failed'),
        description: t('login.network-error'),
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleVerifyPhoneOtp = async () => {
    if (!validateOtp(phoneOtp)) {
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
      setIsLoading(true)

      const response = await apiService.verifySmsCode({
        mobile: phoneNumber,
        sms_code: phoneOtp,
        language: i18n.language
      })

      if (response.code==0) {
        toast({
          title: t('login.register-success')
        })
        onRegisterSuccess()
        // Token handled via login flow, no need to set manually here
      } else {
        toast({
          title: t('login.verify-failed'),
          description: t('login.otp-error'),
          variant: 'destructive'
        })
      }
    } catch {
      toast({
        title: t('login.register-failed'),
        description: t('login.network-error'),
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label
          htmlFor='register-phone'
          className={phoneError ? 'text-red-500' : ''}
        >
          {t('login.phone')}
        </Label>
        <Input
          id='register-phone'
          placeholder={t('login.phone-placeholder')}
          value={phoneNumber}
          onChange={handlePhoneChange}
          disabled={isLoading}
          className={
            phoneError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {phoneError && <p className='text-xs text-red-500'>{phoneError}</p>}
      </div>

      <div className='flex space-x-2'>
        <div className='flex-1'>
          <Input
            id='register-phone-otp'
            placeholder={t('login.otp-placeholder')}
            value={phoneOtp}
            onChange={handleOtpChange}
            disabled={isLoading || !showPhoneOtpInput}
            className={
              otpError ? 'border-red-500 focus-visible:ring-red-500' : ''
            }
          />
          {otpError && <p className='text-xs text-red-500 mt-1'>{otpError}</p>}
        </div>
        <Button
          onClick={handleSendPhoneOtp}
          disabled={
            isLoading || phoneCountdown > 0 || !phoneNumber || !!phoneError
          }
          className='whitespace-nowrap h-8'
        >
          {isLoading && !showPhoneOtpInput ? (
            <Loader2 className='h-4 w-4 animate-spin mr-2' />
          ) : phoneCountdown > 0 ? (
            t('login.seconds-later', { count: phoneCountdown })
          ) : (
            t('login.get-otp')
          )}
        </Button>
      </div>

      <TermsCheckbox
        checked={termsAccepted}
        onCheckedChange={setTermsAccepted}
        disabled={isLoading}
      />

      {showPhoneOtpInput && (
        <div className='space-y-4'>
          {/* <div className="space-y-2">
            <Label htmlFor="register-username">用户名 (选填)</Label>
            <Input
              id="register-username"
              placeholder="请输入用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="register-name">姓名 (选填)</Label>
            <Input
              id="register-name"
              placeholder="请输入姓名"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isLoading}
            />
          </div> */}
          <Button
            className='w-full h-8'
            onClick={handleVerifyPhoneOtp}
            disabled={isLoading || !phoneOtp || !!otpError}
          >
            {isLoading ? (
              <Loader2 className='h-4 w-4 animate-spin mr-2' />
            ) : null}
            {t('login.register')}
          </Button>
        </div>
      )}
    </div>
  )
}
