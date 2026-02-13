'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Loader2, Eye, EyeOff } from 'lucide-react';
import { useToast } from '@/hooks/useToast';
import { TermsCheckbox } from '@/components/TermsCheckbox';
import { TermsConfirmDialog } from '@/components/auth/TermsConfirmDialog';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/store';
import apiService from '@/api';
import { cn } from '@/lib/utils';

import type { UserInfo } from '@/c-types';

interface PasswordLoginProps {
  onLoginSuccess: () => void;
  loginContext: string;
}

export function PasswordLogin({
  onLoginSuccess,
  loginContext,
}: PasswordLoginProps) {
  const { toast } = useToast();
  const { login } = useUserStore();
  const { t } = useTranslation();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [showTermsDialog, setShowTermsDialog] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [identifierError, setIdentifierError] = useState('');
  const [passwordError, setPasswordError] = useState('');

  const validateIdentifier = (value: string) => {
    if (!value) {
      setIdentifierError(t('module.auth.identifierEmpty'));
      return false;
    }
    setIdentifierError('');
    return true;
  };

  const validatePassword = (value: string) => {
    if (!value) {
      setPasswordError(t('module.auth.passwordEmpty'));
      return false;
    }
    if (value.length < 8) {
      setPasswordError(t('module.auth.passwordTooShort'));
      return false;
    }
    if (!/[a-zA-Z]/.test(value)) {
      setPasswordError(t('module.auth.passwordNeedsLetter'));
      return false;
    }
    if (!/[0-9]/.test(value)) {
      setPasswordError(t('module.auth.passwordNeedsDigit'));
      return false;
    }
    setPasswordError('');
    return true;
  };

  const handleIdentifierChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setIdentifier(value);
    if (value) validateIdentifier(value);
    else setIdentifierError('');
  };

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setPassword(value);
    if (value) validatePassword(value);
    else setPasswordError('');
  };

  const doLogin = async (skipTermsCheck?: boolean) => {
    if (!validateIdentifier(identifier) || !validatePassword(password)) {
      return;
    }

    if (!skipTermsCheck && !termsAccepted) {
      setShowTermsDialog(true);
      return;
    }

    try {
      setIsLoading(true);
      const response = await apiService.loginPassword({
        identifier: identifier.trim(),
        password,
      });

      if (response.code === 0 && response.data) {
        toast({ title: t('module.auth.success') });
        await login(response.data.userInfo, response.data.token);
        onLoginSuccess();
      } else {
        toast({
          title: t('module.auth.failed'),
          description:
            response.message ||
            response.msg ||
            t('module.auth.credentialError'),
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: t('module.auth.failed'),
        description: error.message || t('common.core.networkError'),
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !isLoading) {
      e.preventDefault();
      doLogin();
    }
  };

  const handleTermsConfirm = async () => {
    setTermsAccepted(true);
    setShowTermsDialog(false);
    await doLogin(true);
  };

  const handleTermsCancel = () => {
    setShowTermsDialog(false);
  };

  return (
    <>
      <TermsConfirmDialog
        open={showTermsDialog}
        onOpenChange={setShowTermsDialog}
        onConfirm={handleTermsConfirm}
        onCancel={handleTermsCancel}
      />
      <div className='space-y-4'>
        <div className='space-y-2'>
          <Label
            htmlFor='identifier'
            className={identifierError ? 'text-red-500' : ''}
          >
            {t('module.auth.identifier')}
          </Label>
          <Input
            id='identifier'
            placeholder={t('module.auth.identifierPlaceholder')}
            value={identifier}
            onChange={handleIdentifierChange}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            className={cn(
              'text-base sm:text-sm',
              identifierError &&
                'border-red-500 focus-visible:ring-red-500 placeholder:text-muted-foreground',
            )}
          />
          {identifierError && (
            <p className='text-xs text-red-500'>{identifierError}</p>
          )}
        </div>

        <div className='space-y-2'>
          <Label
            htmlFor='password'
            className={passwordError ? 'text-red-500' : ''}
          >
            {t('module.auth.password')}
          </Label>
          <div className='relative'>
            <Input
              id='password'
              type={showPassword ? 'text' : 'password'}
              placeholder={t('module.auth.passwordPlaceholder')}
              value={password}
              onChange={handlePasswordChange}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              className={cn(
                'text-base sm:text-sm pr-10',
                passwordError &&
                  'border-red-500 focus-visible:ring-red-500 placeholder:text-muted-foreground',
              )}
            />
            <button
              type='button'
              className='absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground'
              onClick={() => setShowPassword(!showPassword)}
              tabIndex={-1}
            >
              {showPassword ? (
                <EyeOff className='h-4 w-4' />
              ) : (
                <Eye className='h-4 w-4' />
              )}
            </button>
          </div>
          {passwordError && (
            <p className='text-xs text-red-500'>{passwordError}</p>
          )}
        </div>

        <div className='mt-2'>
          <TermsCheckbox
            checked={termsAccepted}
            onCheckedChange={setTermsAccepted}
            disabled={isLoading}
          />
        </div>

        <Button
          className='w-full h-8'
          onClick={() => doLogin()}
          disabled={isLoading || !identifier || !password}
        >
          {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
          {t('module.auth.login')}
        </Button>
      </div>
    </>
  );
}
