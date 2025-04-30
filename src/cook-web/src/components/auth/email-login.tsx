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
import { isValidEmail } from '@/lib/validators';
import { setToken } from '@/local/local';

interface EmailLoginProps {
  onLoginSuccess: () => void;
  onForgotPassword: () => void;
}

export function EmailLogin({
  onLoginSuccess,
  onForgotPassword,
}: EmailLoginProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [emailError, setEmailError] = useState('');
  const [passwordError, setPasswordError] = useState('');

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

  const validatePassword = (password: string) => {
    if (!password) {
      setPasswordError('请输入密码');
      return false;
    }

    setPasswordError('');
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

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setPassword(value);
    if (value) {
      validatePassword(value);
    } else {
      setPasswordError('');
    }
  };

  const handlePasswordLogin = async () => {
    const isEmailValid = validateEmail(email);
    const isPasswordValid = validatePassword(password);

    if (!isEmailValid || !isPasswordValid) {
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

      const username = email;

      const response = await apiService.login({
        username,
        password,
      });
      if (response.code == 0) {
        toast({
          title: '登录成功',
        });
        setToken(response.data.token);
        onLoginSuccess();
      }

      if (
        response.code == 1001 ||
        response.code == 1005 ||
        response.code === 1003
      ) {
        toast({
          title: '登录失败',
          description: '用户名或密码错误',
          // description: response.msg || '用户名或密码错误',
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: '登录失败',
        description: error.message || '网络错误，请稍后重试',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="email" className={emailError ? 'text-red-500' : ''}>
          邮箱
        </Label>
        <Input
          id="email"
          type="email"
          placeholder="请输入邮箱"
          value={email}
          onChange={handleEmailChange}
          disabled={isLoading}
          className={
            emailError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {emailError && <p className="text-xs text-red-500">{emailError}</p>}
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label
            htmlFor="password"
            className={passwordError ? 'text-red-500' : ''}
          >
            密码
          </Label>
          <button
            type="button"
            onClick={onForgotPassword}
            className="text-primary text-sm hover:underline"
          >
            忘记密码?
          </button>
        </div>
        <Input
          id="password"
          type="password"
          placeholder="请输入密码"
          value={password}
          onChange={handlePasswordChange}
          disabled={isLoading}
          className={
            passwordError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {passwordError && (
          <p className="text-xs text-red-500">{passwordError}</p>
        )}
      </div>
      <TermsCheckbox
        checked={termsAccepted}
        onCheckedChange={setTermsAccepted}
        disabled={isLoading}
      />
      <Button
        className="w-full h-8"
        onClick={handlePasswordLogin}
        disabled={
          isLoading || !email || !password || !!emailError || !!passwordError
        }
      >
        {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
        登录
      </Button>
    </div>
  );
}
