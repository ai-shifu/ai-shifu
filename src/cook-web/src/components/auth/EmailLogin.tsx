'use client';

import type React from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { useTranslation } from 'react-i18next';
import { Mail, ExternalLink } from 'lucide-react';

import type { UserInfo } from '@/c-types';

interface EmailLoginProps {
  onLoginSuccess: (userInfo: UserInfo) => void;
}

export function EmailLogin({}: EmailLoginProps) {
  const { t } = useTranslation();

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label
          htmlFor='email'
          className='text-muted-foreground'
        >
          {t('auth.email')}
        </Label>
        <Input
          id='email'
          type='email'
          placeholder={t('auth.emailPlaceholder')}
          disabled
          className='bg-muted'
        />
      </div>

      <div className='text-center py-8 px-4'>
        <div className='flex justify-center mb-4'>
          <div className='rounded-full bg-muted p-3'>
            <Mail className='h-8 w-8 text-muted-foreground' />
          </div>
        </div>
        <h3 className='text-lg font-medium mb-2'>{t('auth.comingSoon')}</h3>
        <p className='text-sm text-muted-foreground mb-4'>
          {t('auth.moreLoginMethodsComingSoon')}
        </p>
        <div className='space-y-2'>
          <div className='flex items-center justify-center space-x-2 text-sm text-muted-foreground'>
            <ExternalLink className='h-4 w-4' />
            <span>{t('auth.googleLoginSoon')}</span>
          </div>
        </div>
      </div>

      <Button
        className='w-full'
        disabled
        variant='outline'
      >
        {t('auth.moreOptionsComingSoon')}
      </Button>
    </div>
  );
}
