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
import { isValidEmail, checkPasswordStrength } from '@/lib/validators'
import { PasswordStrengthIndicator } from './password-strength-indicator'
import { setToken } from '@/local/local'

interface EmailRegisterProps {
  onRegisterSuccess: () => void
}

export function EmailRegister ({ onRegisterSuccess }: EmailRegisterProps) {
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [isSendingCode, setIsSendingCode] = useState(false)
  const [isVerifying, setIsVerifying] = useState(false)
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [email, setEmail] = useState('')
  const [emailOtp, setEmailOtp] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [step, setStep] = useState<'verify' | 'password'>('verify')
  const [countdown, setCountdown] = useState(0)
  const [showOtpInput, setShowOtpInput] = useState(false)

  const [emailError, setEmailError] = useState('')
  const [otpError, setOtpError] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [confirmPasswordError, setConfirmPasswordError] = useState('')

  const [passwordStrength, setPasswordStrength] = useState({
    score: 0,
    feedback: [] as string[],
    isValid: false
  })

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

  const validateOtp = (otp: string) => {
    if (!otp) {
      setOtpError('请输入验证码')
      return false
    }

    setOtpError('')
    return true
  }

  const validatePassword = (password: string) => {
    if (!password) {
      setPasswordError('请输入密码')
      return false
    }

    const strength = checkPasswordStrength(password)
    setPasswordStrength(strength)

    if (!strength.isValid) {
      // setPasswordError('密码强度不足')
      return false
    }

    setPasswordError('')
    return true
  }

  const validateConfirmPassword = (confirmPassword: string) => {
    if (!confirmPassword) {
      setConfirmPasswordError('请确认密码')
      return false
    }

    if (confirmPassword !== password) {
      setConfirmPasswordError('两次输入的密码不一致')
      return false
    }

    setConfirmPasswordError('')
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
    setEmailOtp(value)
    if (value) {
      validateOtp(value)
    } else {
      setOtpError('')
    }
  }

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setPassword(value)
    validatePassword(value)

    if (confirmPassword) {
      validateConfirmPassword(confirmPassword)
    }
  }

  const handleConfirmPasswordChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const value = e.target.value
    setConfirmPassword(value)
    if (value) {
      validateConfirmPassword(value)
    } else {
      setConfirmPasswordError('')
    }
  }

  const handleSendEmailOtp = async () => {
    if (!validateEmail(email)) {
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
      setIsSendingCode(true)
      setIsLoading(true)

      const response = await apiService.sendMailCode({
        mail: email
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
          description: '请查看您的邮箱'
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
      setIsSendingCode(false)
      setIsLoading(false)
    }
  }

  const handleVerifyEmailOtp = async () => {
    if (!validateEmail(email)) {
      return
    }

    if (!validateOtp(emailOtp)) {
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
      setIsVerifying(true)
      setIsLoading(true)

      const response = await apiService.verifyMailCode({
        mail: email,
        mail_code: emailOtp
      })
      if (response.code==0) {
        setToken(response.data.token)
        setStep('password')
        setPassword('')
        setConfirmPassword('')
        setPasswordError('')
        setConfirmPasswordError('')
        setPasswordStrength({
          score: 0,
          feedback: [],
          isValid: false
        })
        toast({
          title: '邮箱验证成功',
          description: '请设置您的密码'
        })
      } else {
        toast({
          title: '验证失败',
          description:  '验证码错误',
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
      setIsVerifying(false)
      setIsLoading(false)
    }
  }

  const handleCompleteEmailRegistration = async () => {
    const isPasswordValid = validatePassword(password)
    const isConfirmPasswordValid = validateConfirmPassword(confirmPassword)

    if (!isPasswordValid || !isConfirmPasswordValid) {
      return
    }

    try {
      setIsLoading(true)

      const response = await apiService.setPassword({
        mail: email,
        raw_password: password,
      })

      if (response.code==0) {
        toast({
          title: '注册成功'
        })
        onRegisterSuccess()
      } else {
        toast({
          title: '注册失败',
          description:  '请稍后重试',
          variant: 'destructive'
        })
      }
    } catch (error: any) {
      toast({
        title: '注册失败',
        description: error.message || '网络错误，请稍后重试',
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className='space-y-4'>
      {step === 'verify' && (
        <div className='space-y-4'>
          <div className='space-y-2'>
            <Label htmlFor='register-email'>邮箱</Label>
            <Input
              id='register-email'
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

          <div className='space-y-2'>
            <div className='flex space-x-2'>
              <Input
                id='register-email-otp'
                placeholder='请输入验证码'
                value={emailOtp}
                onChange={handleOtpChange}
                disabled={isLoading || !email || !!emailError ||  !showOtpInput}
                className={`flex-1 ${
                  otpError ? 'border-red-500 focus-visible:ring-red-500' : ''
                }`}
              />
              <Button
                onClick={handleSendEmailOtp}
                disabled={
                  isLoading ||
                  !email ||
                  !!emailError ||
                  countdown > 0
                }
                className='whitespace-nowrap h-8'
              >
                {isSendingCode && !showOtpInput ? (
                  <Loader2 className='h-4 w-4 animate-spin mr-2' />
                ) : countdown > 0 ? (
                  `${countdown}秒后重新获取`
                ) : (
                  '获取验证码'
                )}
              </Button>
            </div>
            {otpError && <p className='text-xs text-red-500'>{otpError}</p>}
          </div>

          <TermsCheckbox
            checked={termsAccepted}
            onCheckedChange={setTermsAccepted}
            disabled={isLoading}
          />

          <Button
            className='w-full h-8'
            onClick={handleVerifyEmailOtp}
            disabled={
              isLoading ||
              !email ||
              !!emailError ||
              !emailOtp ||
              !!otpError ||
              !termsAccepted
            }
          >
            {isVerifying ? (
              <Loader2 className='h-4 w-4 animate-spin mr-2' />
            ) : null}
            下一步
          </Button>
        </div>
      )}

      {step === 'password' && (
        <div className='space-y-4'>
          <div className='space-y-2'>
            <Label
              htmlFor='register-password'
              className={passwordError ? 'text-red-500' : ''}
            >
              密码
            </Label>
            <Input
              id='register-password'
              type='password'
              placeholder='请输入密码'
              value={password}
              onChange={handlePasswordChange}
              disabled={isLoading}
              className={
                passwordError ? 'border-red-500 focus-visible:ring-red-500' : ''
              }
            />
            <PasswordStrengthIndicator
              score={passwordStrength.score}
              feedback={passwordStrength.feedback}
            />
            {passwordError && (
              <p className='text-xs text-red-500'>{passwordError}</p>
            )}
          </div>
          <div className='space-y-2'>
            <Label
              htmlFor='confirm-password'
              className={confirmPasswordError ? 'text-red-500' : ''}
            >
              确认密码
            </Label>
            <Input
              id='confirm-password'
              type='password'
              placeholder='请再次输入密码'
              value={confirmPassword}
              onChange={handleConfirmPasswordChange}
              disabled={isLoading}
              className={
                confirmPasswordError
                  ? 'border-red-500 focus-visible:ring-red-500'
                  : ''
              }
            />
            {confirmPasswordError && (
              <p className='text-xs text-red-500'>{confirmPasswordError}</p>
            )}
          </div>
          <div className='flex justify-between'>
            <Button
              variant='outline'
              className='h-8'
              onClick={() => setStep('verify')}
              disabled={isLoading}
            >
              返回
            </Button>
            <Button
              className='h-8'
              onClick={handleCompleteEmailRegistration}
              disabled={
                isLoading ||
                !password ||
                !confirmPassword ||
                !!passwordError ||
                !!confirmPasswordError ||
                !passwordStrength.isValid
              }
            >
              {isLoading ? (
                <Loader2 className='h-4 w-4 animate-spin mr-2' />
              ) : null}
              完成注册
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
