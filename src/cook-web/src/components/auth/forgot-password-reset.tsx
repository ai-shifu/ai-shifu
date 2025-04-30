'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { Loader2 } from 'lucide-react';
import apiService from '@/api';
import { checkPasswordStrength } from '@/lib/validators';
import { PasswordStrengthIndicator } from './password-strength-indicator';

interface ForgotPasswordResetProps {
  email: string;
  onBack: () => void;
  onComplete: () => void;
}

export function ForgotPasswordReset({
  email,
  onBack,
  onComplete,
}: ForgotPasswordResetProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [confirmPasswordError, setConfirmPasswordError] = useState('');
  const [passwordStrength, setPasswordStrength] = useState({
    score: 0,
    feedback: [] as string[],
    isValid: false,
  });

  const validatePassword = (password: string) => {
    if (!password) {
      // setPasswordError("请输入密码")
      return false;
    }

    const strength = checkPasswordStrength(password);
    setPasswordStrength(strength);

    if (!strength.isValid) {
      // setPasswordError("密码强度不足")
      return false;
    }

    setPasswordError('');
    return true;
  };

  const validateConfirmPassword = (confirmPassword: string) => {
    if (!confirmPassword) {
      setConfirmPasswordError('请确认密码');
      return false;
    }

    if (confirmPassword !== password) {
      setConfirmPasswordError('两次输入的密码不一致');
      return false;
    }

    setConfirmPasswordError('');
    return true;
  };

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setPassword(value);
    validatePassword(value);

    if (confirmPassword) {
      validateConfirmPassword(confirmPassword);
    }
  };

  const handleConfirmPasswordChange = (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const value = e.target.value;
    setConfirmPassword(value);
    if (value) {
      validateConfirmPassword(value);
    } else {
      setConfirmPasswordError('');
    }
  };

  const handleResetPassword = async () => {
    const isPasswordValid = validatePassword(password);
    const isConfirmPasswordValid = validateConfirmPassword(confirmPassword);

    if (!isPasswordValid || !isConfirmPasswordValid) {
      return;
    }

    try {
      setIsLoading(true);

      const response = await apiService.setPassword({
        mail: email,
        raw_password: password,
      });

      if (response.code == 0) {
        toast({
          title: '密码已重置',
          description: '请使用新密码登录',
        });
        onComplete();
      } else {
        toast({
          title: '重置密码失败',
          description: '请稍后重试',
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: '重置密码失败',
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
        <Label
          htmlFor="new-password"
          className={passwordError ? 'text-red-500' : ''}
        >
          新密码
        </Label>
        <Input
          id="new-password"
          type="password"
          placeholder="请输入新密码"
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
          <p className="text-xs text-red-500">{passwordError}</p>
        )}
      </div>
      <div className="space-y-2">
        <Label
          htmlFor="confirm-new-password"
          className={confirmPasswordError ? 'text-red-500' : ''}
        >
          确认新密码
        </Label>
        <Input
          id="confirm-new-password"
          type="password"
          placeholder="请再次输入新密码"
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
          <p className="text-xs text-red-500">{confirmPasswordError}</p>
        )}
      </div>
      <div className="flex justify-between">
        <Button
          className="h-8"
          variant="outline"
          onClick={onBack}
          disabled={isLoading}
        >
          返回
        </Button>
        <Button
          onClick={handleResetPassword}
          className="h-8"
          disabled={
            isLoading ||
            !password ||
            !confirmPassword ||
            !!passwordError ||
            !!confirmPasswordError ||
            !passwordStrength.isValid
          }
        >
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
          重置密码
        </Button>
      </div>
    </div>
  );
}
