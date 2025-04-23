'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { mockAuth } from '@/lib/mock-auth'
import { TermsCheckbox } from './terms-checkbox'
import api from '@/api'
import { getToken, setToken } from '@/local/local'

export const genUuid = () => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const  v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

interface RegisterFormProps {
  onSuccess?: () => void
  onLoginClick?: () => void
  onFeedbackClick?: () => void
  isDialog?: boolean
}

export function RegisterForm ({
  onSuccess,
  onLoginClick,
  onFeedbackClick,
  isDialog = false
}: RegisterFormProps) {
  const router = useRouter()
  const [isLoading, setIsLoading] = useState(false)
  const [termsAccepted, setTermsAccepted] = useState(false)

  // 手机号注册状态
  const [phoneNumber, setPhoneNumber] = useState('')
  const [phoneOtp, setPhoneOtp] = useState('')
  const [showPhoneOtpInput, setShowPhoneOtpInput] = useState(false)

  // 邮箱注册状态
  const [email, setEmail] = useState('')
  const [emailOtp, setEmailOtp] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [emailStep, setEmailStep] = useState<'email' | 'verify' | 'password'>(
    'email'
  )

  const [userCaptchaInput, setUserCaptchaInput] = useState('')
  const [captchaImg, setCaptchaImg] = useState('')

  // 手机号注册 - 发送验证码
  const handleSendPhoneOtp = async () => {
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
      // const { error } = await mockAuth.signInWithOtp({
      //   phone: phoneNumber,
      // })

      const response = await api.sendSmsCode({
        mobile: phoneNumber,
        check_code: 'register'
      })
      console.log(response)
      setShowPhoneOtpInput(true)
      // toast({
      //   title: "验证码已发送",
      //   description: "请查看您的手机短信（模拟：使用123456作为验证码）",
      // })
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

  // 手机号注册 - 验证OTP
  const handleVerifyPhoneOtp = async () => {
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
        title: '注册成功'
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

  // 邮箱注册 - 发送验证码
  const handleSendEmailOtp = async () => {
    if (!email) {
      toast({
        title: '请输入邮箱',
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
        email: email
      })

      if (error) throw error

      setEmailStep('verify')
      toast({
        title: '验证码已发送',
        description: '请查看您的邮箱（模拟：使用123456作为验证码）'
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

  // 邮箱注册 - 验证OTP
  const handleVerifyEmailOtp = async () => {
    if (!emailOtp) {
      toast({
        title: '请输入验证码',
        variant: 'destructive'
      })
      return
    }

    try {
      setIsLoading(true)
      const { error, data } = await mockAuth.verifyOtp({
        email: email,
        token: emailOtp,
        type: 'email'
      })

      if (error) throw error

      if (data?.verified) {
        setEmailStep('password')
        toast({
          title: '邮箱验证成功',
          description: '请设置您的密码'
        })
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

  // 邮箱注册 - 设置密码
  const handleCompleteEmailRegistration = async () => {
    if (!password || !confirmPassword) {
      toast({
        title: '请填写所有字段',
        variant: 'destructive'
      })
      return
    }

    if (password !== confirmPassword) {
      toast({
        title: '两次输入的密码不一致',
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
      const { error } = await mockAuth.signUp({
        email,
        password
      })

      if (error) throw error

      toast({
        title: '注册成功'
      })

      if (onSuccess) {
        onSuccess()
      } else {
        router.push('/dashboard')
      }
    } catch (error: any) {
      toast({
        title: '注册失败',
        description: error.message,
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleGeneCaptcha = async () => {
    const response = await api.geneCaptcha({
      mobile: phoneNumber,
      mail: null
    })
    console.log(response)
    setCaptchaImg(response.data.img)
  }

  const getTmp = async () => {
    const response = await api.requireTmp({
      temp_id: genUuid()
    })
    console.log(response)
    if (response.token) {
      setToken(response.token)
    }
  }

  useEffect(() => {
    debugger
    const token = getToken();
    console.log('token',token)
    if (!getToken()) {
      getTmp()
    }
  }, [])

  const handleLogin = () => {
    if (onLoginClick) {
      onLoginClick()
    } else if (!isDialog) {
      router.push('/auth/login')
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
        <CardTitle className='text-2xl text-center'>用户注册</CardTitle>
        <CardDescription className='text-center'>
          请选择注册方式
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue='phone' className='w-full'>
          <TabsList className='grid w-full grid-cols-2'>
            <TabsTrigger value='phone'>手机号注册</TabsTrigger>
            <TabsTrigger value='email'>邮箱注册</TabsTrigger>
          </TabsList>

          <TabsContent value='phone' className='space-y-4'>
            <div className='space-y-2'>
              <Label htmlFor='register-phone'>手机号</Label>
              <div className='flex space-x-2'>
                <Input
                  id='register-phone'
                  placeholder='请输入手机号'
                  value={phoneNumber}
                  onChange={e => setPhoneNumber(e.target.value)}
                  disabled={isLoading || showPhoneOtpInput}
                />
                <Button
                  className='h-8'
                  onClick={handleSendPhoneOtp}
                  disabled={isLoading || showPhoneOtpInput}
                >
                  {isLoading ? (
                    <Loader2 className='h-4 w-4 animate-spin' />
                  ) : (
                    '获取验证码'
                  )}
                </Button>
              </div>
            </div>
            <div className='space-y-2'>
              <Label htmlFor='captcha'>图片验证码</Label>
              <div className='flex space-x-2'>
                <Input
                  id='captcha'
                  placeholder='请输入图片验证码'
                  value={userCaptchaInput}
                  onChange={e => setUserCaptchaInput(e.target.value)}
                  disabled={isLoading || showPhoneOtpInput}
                />
                <div className='flex items-center' onClick={handleGeneCaptcha}>
                  {captchaImg ? (
                    <img src={captchaImg} alt='验证码' className='h-8 w-24' />
                  ) : (
                    <a>点击获取</a>
                  )}
                </div>
              </div>
            </div>

            <TermsCheckbox
              checked={termsAccepted}
              onCheckedChange={setTermsAccepted}
              disabled={isLoading}
            />

            {showPhoneOtpInput && (
              <div className='space-y-2'>
                <Label htmlFor='register-phone-otp'>验证码</Label>
                <Input
                  id='register-phone-otp'
                  placeholder='请输入验证码'
                  value={phoneOtp}
                  onChange={e => setPhoneOtp(e.target.value)}
                  disabled={isLoading}
                />
                <Button
                  className='w-full'
                  onClick={handleVerifyPhoneOtp}
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <Loader2 className='h-4 w-4 animate-spin mr-2' />
                  ) : null}
                  注册
                </Button>
              </div>
            )}
          </TabsContent>

          <TabsContent value='email' className='space-y-4'>
            {emailStep === 'email' && (
              <div className='space-y-4'>
                <div className='space-y-2'>
                  <Label htmlFor='register-email'>邮箱</Label>
                  <Input
                    id='register-email'
                    type='email'
                    placeholder='请输入邮箱'
                    value={email}
                    onChange={e => setEmail(e.target.value)}
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
                  onClick={handleSendEmailOtp}
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <Loader2 className='h-4 w-4 animate-spin mr-2' />
                  ) : null}
                  获取验证码
                </Button>
              </div>
            )}

            {emailStep === 'verify' && (
              <div className='space-y-4'>
                <div className='space-y-2'>
                  <Label htmlFor='register-email-otp'>验证码</Label>
                  <Input
                    id='register-email-otp'
                    placeholder='请输入邮箱验证码'
                    value={emailOtp}
                    onChange={e => setEmailOtp(e.target.value)}
                    disabled={isLoading}
                  />
                </div>
                <div className='flex justify-between'>
                  <Button
                    variant='outline'
                    onClick={() => setEmailStep('email')}
                    disabled={isLoading}
                  >
                    返回
                  </Button>
                  <Button onClick={handleVerifyEmailOtp} disabled={isLoading}>
                    {isLoading ? (
                      <Loader2 className='h-4 w-4 animate-spin mr-2' />
                    ) : null}
                    验证
                  </Button>
                </div>
              </div>
            )}

            {emailStep === 'password' && (
              <div className='space-y-4'>
                <div className='space-y-2'>
                  <Label htmlFor='register-password'>密码</Label>
                  <Input
                    id='register-password'
                    type='password'
                    placeholder='请输入密码'
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    disabled={isLoading}
                  />
                </div>
                <div className='space-y-2'>
                  <Label htmlFor='confirm-password'>确认密码</Label>
                  <Input
                    id='confirm-password'
                    type='password'
                    placeholder='请再次输入密码'
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    disabled={isLoading}
                  />
                </div>
                <div className='flex justify-between'>
                  <Button
                    variant='outline'
                    onClick={() => setEmailStep('verify')}
                    disabled={isLoading}
                  >
                    返回
                  </Button>
                  <Button
                    onClick={handleCompleteEmailRegistration}
                    disabled={isLoading}
                  >
                    {isLoading ? (
                      <Loader2 className='h-4 w-4 animate-spin mr-2' />
                    ) : null}
                    完成注册
                  </Button>
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
      <CardFooter className='flex flex-col items-center space-y-2'>
        <p className='text-sm text-muted-foreground'>
          已有账号?{' '}
          <Button
            variant='link'
            className='p-0 h-auto text-primary'
            onClick={handleLogin}
          >
            立即登录
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
