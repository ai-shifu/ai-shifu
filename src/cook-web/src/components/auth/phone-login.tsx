'use client'

import type React from 'react'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2 } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'
import { TermsCheckbox } from '@/components/terms-checkbox'
import apiService from '@/api'
import { isValidPhoneNumber } from '@/lib/validators'
import { setToken } from '@/local/local'

interface PhoneLoginProps {
  onLoginSuccess: () => void
}

export function PhoneLogin ({ onLoginSuccess }: PhoneLoginProps) {
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [phoneNumber, setPhoneNumber] = useState('')
  const [phoneOtp, setPhoneOtp] = useState('')
  const [showOtpInput, setShowOtpInput] = useState(false)
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [phoneError, setPhoneError] = useState('')

  const validatePhone = (phone: string) => {
    if (!phone) {
      setPhoneError('请输入手机号')
      return false
    }

    if (!isValidPhoneNumber(phone)) {
      setPhoneError('请输入有效的手机号')
      return false
    }

    setPhoneError('')
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

  const handleSendOtp = async () => {
    if (!validatePhone(phoneNumber)) {
      return
    }

    if (!termsAccepted) {
      toast({
        title: '请阅读并同意服务协议和隐私政策',
        variant: 'destructive'
      })
      return
    }

    try {
      setIsLoading(true)

      const response = await apiService.sendSmsCode({
        mobile: phoneNumber
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
          title: '验证码已发送',
          description: '请查看您的手机短信'
        })
      } else {
        toast({
          title: '发送验证码失败',
          description: response.msg || '请稍后重试',
          variant: 'destructive'
        })
      }
    } catch (error: any) {
      toast({
        title: '发送验证码失败',
        description: error.message || '网络错误，请稍后重试',
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleVerifyOtp = async () => {
    if (!phoneOtp) {
      toast({
        title: '请输入验证码',
        variant: 'destructive'
      })
      return
    }

    if (!termsAccepted) {
      toast({
        title: '请阅读并同意服务协议和隐私政策',
        variant: 'destructive'
      })
      return
    }

    try {
      setIsLoading(true)

      const response = await apiService.verifySmsCode({
        mobile: phoneNumber,
        sms_code: phoneOtp
      })

      if (response.code == 0) {
        toast({
          title: '登录成功'
        })
        setToken(response.data.token)
        onLoginSuccess()
      } else if (response.code == 1003) {
        toast({
          title: '验证失败',
          description: '验证码已过期',
          variant: 'destructive'
        })
      } else {
        toast({
          title: '验证失败',
          description: '验证码错误',
          variant: 'destructive'
        })
      }

    } catch (error: any) {
      toast({
        title: '验证失败',
        description: error.message || '网络错误，请稍后重试',
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label htmlFor='phone' className={phoneError ? 'text-red-500' : ''}>
          手机号
        </Label>
        <Input
          id='phone'
          placeholder='请输入手机号'
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
            id='otp'
            placeholder='请输入验证码'
            value={phoneOtp}
            onChange={e => setPhoneOtp(e.target.value)}
            disabled={isLoading || !showOtpInput}
          />
        </div>
        <Button
          onClick={handleSendOtp}
          disabled={isLoading || countdown > 0 || !phoneNumber || !!phoneError}
          className='whitespace-nowrap h-8'
        >
          {isLoading && !showOtpInput ? (
            <Loader2 className='h-4 w-4 animate-spin mr-2' />
          ) : countdown > 0 ? (
            `${countdown}秒后重新获取`
          ) : (
            '获取验证码'
          )}
        </Button>
      </div>

      <div className='mt-2'>
        <TermsCheckbox
          checked={termsAccepted}
          onCheckedChange={setTermsAccepted}
          disabled={isLoading}
        />
      </div>

      {showOtpInput && (
        <Button
          className='w-full h-8'
          onClick={handleVerifyOtp}
          disabled={isLoading || !phoneOtp}
        >
          {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
          登录
        </Button>
      )}
    </div>
  )
}
