'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { Loader2 } from 'lucide-react';
import { TermsCheckbox } from '@/components/terms-checkbox';
import apiService from '@/api';
import { isValidPhoneNumber } from '@/lib/validators';
import { setToken } from '@/local/local';

interface PhoneRegisterProps {
  onRegisterSuccess: () => void;
}

export function PhoneRegister({ onRegisterSuccess }: PhoneRegisterProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [phoneOtp, setPhoneOtp] = useState('');
  const [showPhoneOtpInput, setShowPhoneOtpInput] = useState(false);
  const [phoneCountdown, setPhoneCountdown] = useState(0);
  // const [username, setUsername] = useState('')
  // const [name, setName] = useState('')
  const [phoneError, setPhoneError] = useState('');
  const [otpError, setOtpError] = useState('');

  const validatePhone = (phone: string) => {
    if (!phone) {
      setPhoneError('请输入手机号');
      return false;
    }

    if (!isValidPhoneNumber(phone)) {
      setPhoneError('请输入有效的手机号');
      return false;
    }

    setPhoneError('');
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

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setPhoneNumber(value);
    if (value) {
      validatePhone(value);
    } else {
      setPhoneError('');
    }
  };

  const handleOtpChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setPhoneOtp(value);
    if (value) {
      validateOtp(value);
    } else {
      setOtpError('');
    }
  };

  const handleSendPhoneOtp = async () => {
    if (!validatePhone(phoneNumber)) {
      return;
    }

    if (!termsAccepted) {
      toast({
        title: '请阅读并同意服务协议和隐私政策',
        variant: 'destructive',
      });
      return;
    }

    try {
      setIsLoading(true);

      const response = await apiService.sendSmsCode({
        mobile: phoneNumber,
      });

      if (response.code == 0) {
        setShowPhoneOtpInput(true);
        setPhoneCountdown(60);
        const timer = setInterval(() => {
          setPhoneCountdown((prevCountdown) => {
            if (prevCountdown <= 1) {
              clearInterval(timer);
              return 0;
            }
            return prevCountdown - 1;
          });
        }, 1000);

        toast({
          title: '验证码已发送',
          description: '请查看您的手机短信',
        });
      } else {
        toast({
          title: '发送验证码失败',
          description: response.msg || '请稍后重试',
          variant: 'destructive',
        });
      }
    } catch {
      toast({
        title: '发送验证码失败',
        description: '网络错误，请稍后重试',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyPhoneOtp = async () => {
    if (!validateOtp(phoneOtp)) {
      return;
    }

    if (!termsAccepted) {
      toast({
        title: '请阅读并同意服务协议和隐私政策',
        variant: 'destructive',
      });
      return;
    }

    try {
      setIsLoading(true);

      const response = await apiService.verifySmsCode({
        mobile: phoneNumber,
        sms_code: phoneOtp,
      });

      if (response.code == 0) {
        toast({
          title: '注册成功',
        });
        onRegisterSuccess();
        setToken(response.data.token);
      } else {
        toast({
          title: '验证失败',
          description: '验证码错误',
          variant: 'destructive',
        });
      }
    } catch {
      toast({
        title: '注册失败',
        description: '网络错误，请稍后重试',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label
          htmlFor="register-phone"
          className={phoneError ? 'text-red-500' : ''}
        >
          手机号
        </Label>
        <Input
          id="register-phone"
          placeholder="请输入手机号"
          value={phoneNumber}
          onChange={handlePhoneChange}
          disabled={isLoading}
          className={
            phoneError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {phoneError && <p className="text-xs text-red-500">{phoneError}</p>}
      </div>

      <div className="flex space-x-2">
        <div className="flex-1">
          <Input
            id="register-phone-otp"
            placeholder="请输入验证码"
            value={phoneOtp}
            onChange={handleOtpChange}
            disabled={isLoading || !showPhoneOtpInput}
            className={
              otpError ? 'border-red-500 focus-visible:ring-red-500' : ''
            }
          />
          {otpError && <p className="text-xs text-red-500 mt-1">{otpError}</p>}
        </div>
        <Button
          onClick={handleSendPhoneOtp}
          disabled={
            isLoading || phoneCountdown > 0 || !phoneNumber || !!phoneError
          }
          className="whitespace-nowrap h-8"
        >
          {isLoading && !showPhoneOtpInput ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : phoneCountdown > 0 ? (
            `${phoneCountdown}秒后重新获取`
          ) : (
            '获取验证码'
          )}
        </Button>
      </div>

      <TermsCheckbox
        checked={termsAccepted}
        onCheckedChange={setTermsAccepted}
        disabled={isLoading}
      />

      {showPhoneOtpInput && (
        <div className="space-y-4">
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
            className="w-full h-8"
            onClick={handleVerifyPhoneOtp}
            disabled={isLoading || !phoneOtp || !!otpError}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : null}
            注册
          </Button>
        </div>
      )}
    </div>
  );
}
