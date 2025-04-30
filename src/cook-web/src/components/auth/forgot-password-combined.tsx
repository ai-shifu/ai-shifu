'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { Loader2 } from 'lucide-react';
import apiService from '@/api';
import { isValidEmail } from '@/lib/validators';
import { setToken } from '@/local/local';

interface ForgotPasswordCombinedProps {
  onNext: (email: string, otp: string) => void;
}

export function ForgotPasswordCombined({
  onNext,
}: ForgotPasswordCombinedProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [emailError, setEmailError] = useState('');
  const [otpError, setOtpError] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [codeSent, setCodeSent] = useState(false);

  const validateEmail = (email: string) => {
    if (!email) {
      setEmailError('请输入邮箱');
      return false;
    }

    if (!isValidEmail(email)) {
      setEmailError('请输入有效的邮箱地址');
      return false;
    }

    setEmailError('');
    return true;
  };

  const validateOtp = (otp: string) => {
    if (!otp) {
      setOtpError('请输入验证码');
      return false;
    }

    setOtpError('');
    return true;
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setEmail(value);
    if (value) {
      validateEmail(value);
    } else {
      setEmailError('');
    }
  };

  const handleOtpChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setOtp(value);
    if (value) {
      validateOtp(value);
    } else {
      setOtpError('');
    }
  };

  const handleSendOtp = async () => {
    if (!validateEmail(email)) {
      return;
    }

    try {
      setIsSendingCode(true);

      const response = await apiService.sendMailCode({
        mail: email,
      });

      if (response.code == 0) {
        setCodeSent(true);
        setCountdown(60);
        const timer = setInterval(() => {
          setCountdown((prevCountdown) => {
            if (prevCountdown <= 1) {
              clearInterval(timer);
              return 0;
            }
            return prevCountdown - 1;
          });
        }, 1000);

        toast({
          title: '验证码已发送',
          description: '请查看您的邮箱',
        });
      } else {
        toast({
          title: '发送验证码失败',
          description: '请稍后重试',
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: '发送验证码失败',
        description: error.message || '网络错误，请稍后重试',
        variant: 'destructive',
      });
    } finally {
      setIsSendingCode(false);
    }
  };

  const handleVerifyOtp = async () => {
    if (!validateEmail(email)) {
      return;
    }

    if (!validateOtp(otp)) {
      return;
    }

    try {
      setIsVerifying(true);
      setIsLoading(true);

      const response = await apiService.verifyMailCode({
        mail: email,
        mail_code: otp,
      });

      if (response.code == 0) {
        setToken(response.data.token);
        toast({
          title: '验证成功',
          description: '请设置新密码',
        });
        onNext(email, otp);
      } else {
        toast({
          title: '验证失败',
          description: '验证码错误',
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: '验证失败',
        description: error.message || '网络错误，请稍后重试',
        variant: 'destructive',
      });
    } finally {
      setIsVerifying(false);
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="email" className={emailError ? 'text-red-500' : ''}>
          邮箱
        </Label>
        <div className="flex space-x-2">
          <Input
            id="email"
            type="email"
            placeholder="请输入邮箱"
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
            className="whitespace-nowrap h-8"
          >
            {isSendingCode ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : countdown > 0 ? (
              `${countdown}秒后重新获取`
            ) : (
              '获取验证码'
            )}
          </Button>
        </div>
        {emailError && <p className="text-xs text-red-500">{emailError}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="otp" className={otpError ? 'text-red-500' : ''}>
          验证码
        </Label>
        <Input
          id="otp"
          placeholder="请输入验证码"
          value={otp}
          onChange={handleOtpChange}
          disabled={isLoading || !codeSent}
          className={
            otpError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {otpError && <p className="text-xs text-red-500">{otpError}</p>}
      </div>

      <Button
        className="w-full h-8"
        onClick={handleVerifyOtp}
        disabled={
          isLoading || !email || !!emailError || !otp || !!otpError || !codeSent
        }
      >
        {isVerifying ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
        下一步
      </Button>
    </div>
  );
}
