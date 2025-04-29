'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { Loader2 } from 'lucide-react'
import apiService from '@/api'
import { setToken } from '@/local/local'

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
          title: '验证码已重新发送',
          description: '请查看您的邮箱'
        })
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

  const handleVerifyOtp = async () => {
    if (!otp) {
      toast({
        title: '请输入验证码',
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
          title: '验证成功',
          description: '请设置新密码'
        })
        onNext(otp)
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
        <Label htmlFor='otp'>验证码</Label>
        <Input
          id='otp'
          placeholder='请输入验证码'
          value={otp}
          onChange={e => setOtp(e.target.value)}
          disabled={isLoading}
        />
        {countdown > 0 ? (
          <p className='text-sm text-muted-foreground mt-1'>
            {countdown}秒后可重新获取验证码
          </p>
        ) : (
          <Button
            variant='link'
            className='p-0 h-auto text-sm h-8'
            onClick={handleResendOtp}
            disabled={isLoading}
          >
            重新获取验证码
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
          返回
        </Button>
        <Button onClick={handleVerifyOtp} disabled={isLoading} className='h-8'>
          {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
          验证
        </Button>
      </div>
    </div>
  )
}
