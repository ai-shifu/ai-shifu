'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/hooks/use-toast'
import { Loader2 } from 'lucide-react'
import { mockAuth } from '@/lib/mock-auth'
import { TermsCheckbox } from './terms-checkbox'
import api from '@/api'
import type { LoginResponse } from './type'
import { setToken } from '@/local/local'

interface LoginFormProps {
  onSuccess?: () => void
  onRegisterClick?: () => void
  onForgotPasswordClick?: () => void
  onFeedbackClick?: () => void
  isDialog?: boolean
}

export function LoginForm ({
  onSuccess,
  onRegisterClick,
  onForgotPasswordClick,
  onFeedbackClick,
  isDialog = false
}: LoginFormProps) {
  const router = useRouter()
  const [isLoading, setIsLoading] = useState(false)
  const [phoneNumber, setPhoneNumber] = useState('')
  const [phoneOtp, setPhoneOtp] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showOtpInput, setShowOtpInput] = useState(false)
  const [termsAccepted, setTermsAccepted] = useState(false)

  // 手机号登录 - 发送验证码
  const handleSendOtp = async () => {
    if (!phoneNumber) {
      toast({
        title: '请输入手机号',
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
      const { error } = await mockAuth.signInWithOtp({
        phone: phoneNumber
      })

      if (error) throw error

      setShowOtpInput(true)
      toast({
        title: '验证码已发送',
        description: '请查看您的手机短信（模拟：使用123456作为验证码）'
      })
    } catch (error: any) {
      toast({
        title: '发送验证码失败',
        description: error.message,
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  // 手机号登录 - 验证OTP
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
      const { error } = await mockAuth.verifyOtp({
        phone: phoneNumber,
        token: phoneOtp,
        type: 'sms'
      })

      if (error) throw error

      toast({
        title: '登录成功'
      })

      if (onSuccess) {
        onSuccess()
      } else {
        router.push('/dashboard')
      }
    } catch (error: any) {
      toast({
        title: '验证失败',
        description: error.message,
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const validatePassword = (password: string) => {
    if (password.length < 8) {
      return '密码长度至少8位'
    }
    if (!/[A-Za-z]/.test(password)) {
      return '密码必须包含字母'
    }
    if (!/[0-9]/.test(password)) {
      return '密码必须包含数字'
    }
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
      return '密码必须包含特殊字符'
    }
    return ''
  }

  // 邮箱登录
  const handlePasswordLogin = async () => {
    if (!email || !password) {
      toast({
        title: '请输入邮箱和密码',
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

    if(validatePassword(password)) {
      toast({
        title: validatePassword(password),
        variant: 'destructive'
      })
      return
    }

    try {
      setIsLoading(true)
      // const { error } = await mockAuth.signInWithPassword({
      //   email,
      //   password,
      // })

      const result: LoginResponse = await api.login({
        username: email,
        password
      })
      console.log(result)
      toast({
        title: '登录成功'
      })
      setToken(result.token)
      router.push('/main')
    } catch (error: any) {
      toast({
        title: '登录失败',
        description: error.message,
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleForgotPassword = () => {
    if (onForgotPasswordClick) {
      onForgotPasswordClick()
    } else if (!isDialog) {
      router.push('/auth/forgot-password')
    }
  }

  const handleRegister = () => {
    if (onRegisterClick) {
      onRegisterClick()
    } else if (!isDialog) {
      router.push('/auth/register')
    }
  }

  const handleFeedback = () => {
    if (onFeedbackClick) {
      onFeedbackClick()
    } else if (!isDialog) {
      router.push('/feedback')
    }
  }

  return (
    <Card className={isDialog ? 'border-0 shadow-none' : ''}>
      <CardHeader>
        <CardTitle className='text-2xl text-center'>用户登录</CardTitle>
        <CardDescription className='text-center'>
          请选择登录方式
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue='phone' className='w-full'>
          <TabsList className='grid w-full grid-cols-2'>
            <TabsTrigger value='phone'>手机号登录</TabsTrigger>
            <TabsTrigger value='password'>邮箱登录</TabsTrigger>
          </TabsList>

          <TabsContent value='phone' className='space-y-4'>
            <div className='space-y-2'>
              <Label htmlFor='phone'>手机号</Label>
              <div className='flex space-x-2'>
                <Input
                  id='phone'
                  placeholder='请输入手机号'
                  value={phoneNumber}
                  onChange={e => setPhoneNumber(e.target.value)}
                  disabled={isLoading || showOtpInput}
                />
                <Button
                  onClick={handleSendOtp}
                  disabled={isLoading || showOtpInput}
                >
                  {isLoading ? (
                    <Loader2 className='h-4 w-4 animate-spin' />
                  ) : (
                    '获取验证码'
                  )}
                </Button>
              </div>
            </div>

            <div className='mt-2'>
              <TermsCheckbox
                checked={termsAccepted}
                onCheckedChange={setTermsAccepted}
                disabled={isLoading}
              />
            </div>

            {showOtpInput && (
              <div className='space-y-2'>
                <Label htmlFor='otp'>验证码</Label>
                <Input
                  id='otp'
                  placeholder='请输入验证码'
                  value={phoneOtp}
                  onChange={e => setPhoneOtp(e.target.value)}
                  disabled={isLoading}
                />
                <Button
                  className='w-full'
                  onClick={handleVerifyOtp}
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <Loader2 className='h-4 w-4 animate-spin mr-2' />
                  ) : null}
                  登录
                </Button>
              </div>
            )}
          </TabsContent>

          <TabsContent value='password' className='space-y-4'>
            <div className='space-y-2'>
              <Label htmlFor='email'>邮箱</Label>
              <Input
                id='email'
                type='email'
                placeholder='请输入邮箱 (test@example.com)'
                value={email}
                onChange={e => setEmail(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <div className='space-y-2'>
              <div className='flex items-center justify-between'>
                <Label htmlFor='password'>密码</Label>
                <Button
                  variant='link'
                  className='p-0 h-auto text-primary text-sm'
                  onClick={handleForgotPassword}
                >
                  忘记密码?
                </Button>
              </div>
              <Input
                id='password'
                type='password'
                placeholder='请输入密码 (password123)'
                value={password}
                onChange={e => setPassword(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <TermsCheckbox
              checked={termsAccepted}
              onCheckedChange={setTermsAccepted}
              disabled={isLoading}
            />
            <Button
              className='w-full'
              onClick={handlePasswordLogin}
              disabled={isLoading}
            >
              {isLoading ? (
                <Loader2 className='h-4 w-4 animate-spin mr-2' />
              ) : null}
              登录
            </Button>
          </TabsContent>
        </Tabs>
      </CardContent>
      <CardFooter className='flex flex-col items-center space-y-2'>
        <p className='text-sm text-muted-foreground'>
          还没有账号?{' '}
          <Button
            variant='link'
            className='p-0 h-auto text-primary'
            onClick={handleRegister}
          >
            立即注册
          </Button>
        </p>
        <p className='text-sm text-muted-foreground'>
          登录遇到问题?{' '}
          <Button
            variant='link'
            className='p-0 h-auto text-primary'
            onClick={handleFeedback}
          >
            提交反馈
          </Button>
        </p>
      </CardFooter>
    </Card>
  )
}
