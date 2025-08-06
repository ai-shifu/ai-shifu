'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { useToast } from '@/hooks/useToast';
import { Loader2 } from 'lucide-react';
import apiService from '@/api';
import { checkPasswordStrength } from '@/lib/validators';
import { PasswordStrengthIndicator } from './PasswordStrengthIndicator';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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
      setConfirmPasswordError(t('auth.pleaseConfirmPassword'));
      return false;
    }

    if (confirmPassword !== password) {
      setConfirmPasswordError(t('auth.passwordNotMatch'));
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
          title: t('auth.passwordReset'),
          description: t('auth.pleaseUseNewPassword'),
        });
        onComplete();
      } else {
        toast({
          title: t('auth.failed'),
          description: t('common.pleaseTryAgainLater'),
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: t('auth.failed'),
        description: error.message || t('common.networkError'),
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label
          htmlFor='new-password'
          className={passwordError ? 'text-red-500' : ''}
        >
          {t('auth.newPassword')}
        </Label>
        <Input
          id='new-password'
          type='password'
          placeholder={t('auth.newPasswordPlaceholder')}
          value={password}
          onChange={handlePasswordChange}
          disabled={isLoading}
          className={
            passwordError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        <PasswordStrengthIndicator feedback={passwordStrength.feedback} />
        {passwordError && (
          <p className='text-xs text-red-500'>{passwordError}</p>
        )}
      </div>
      <div className='space-y-2'>
        <Label
          htmlFor='confirm-new-password'
          className={confirmPasswordError ? 'text-red-500' : ''}
        >
          {t('auth.confirmNewPassword')}
        </Label>
        <Input
          id='confirm-new-password'
          type='password'
          placeholder={t('auth.confirmNewPasswordPlaceholder')}
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
          className='h-8'
          variant='outline'
          onClick={onBack}
          disabled={isLoading}
        >
          {t('auth.back')}
        </Button>
        <Button
          onClick={handleResetPassword}
          className='h-8'
          disabled={
            isLoading ||
            !password ||
            !confirmPassword ||
            !!passwordError ||
            !!confirmPasswordError ||
            !passwordStrength.isValid
          }
        >
          {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
          {t('auth.resetPassword')}
        </Button>
      </div>
    </div>
  );
}
