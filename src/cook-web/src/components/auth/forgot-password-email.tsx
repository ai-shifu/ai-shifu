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

interface ForgotPasswordEmailProps {
  onNext: (email: string) => void
}

export function ForgotPasswordEmail ({ onNext }: ForgotPasswordEmailProps) {
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState('')

  const validateEmail = (email: string) => {
    if (!email) {
      setEmailError('请输入邮箱')
      return false
    }

    if (!isValidEmail(email)) {
      setEmailError('请输入有效的邮箱地址')
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
          title: '验证码已发送',
          description: '请查看您的邮箱'
        })
        onNext(email)
      } else {
        toast({
          title: '发送验证码失败',
          description:  '请稍后重试',
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

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label htmlFor='email' className={emailError ? 'text-red-500' : ''}>
          邮箱
        </Label>
        <Input
          id='email'
          type='email'
          placeholder='请输入邮箱'
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
        获取验证码
      </Button>
    </div>
  )
}
