'use client';

import { Loader2, RefreshCcw } from 'lucide-react';
import Image from 'next/image';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { cn } from '@/lib/utils';

interface ImageCaptchaInputProps {
  value: string;
  image: string;
  isLoading?: boolean;
  disabled?: boolean;
  error?: string;
  id?: string;
  onChange: (value: string) => void;
  onRefresh: () => void;
}

export function ImageCaptchaInput({
  value,
  image,
  isLoading = false,
  disabled = false,
  error,
  id = 'captcha',
  onChange,
  onRefresh,
}: ImageCaptchaInputProps) {
  const { t } = useTranslation();
  const refreshLabel = t('module.auth.captchaRefresh');

  return (
    <div className='space-y-2'>
      <Label htmlFor={id}>{t('module.auth.captcha')}</Label>
      <div className='flex gap-2'>
        <Input
          id={id}
          data-testid='captcha-input'
          value={value}
          onChange={event => onChange(event.target.value)}
          placeholder={t('module.auth.captchaPlaceholder')}
          autoComplete='off'
          disabled={disabled || isLoading}
          className={cn(
            'text-base sm:text-sm uppercase',
            error && 'border-red-500',
          )}
        />
        <button
          type='button'
          aria-label={refreshLabel}
          title={refreshLabel}
          className='h-8 w-28 shrink-0 overflow-hidden rounded-md border border-input bg-background disabled:cursor-not-allowed disabled:opacity-50'
          onClick={onRefresh}
          disabled={disabled || isLoading}
        >
          {image ? (
            <Image
              data-testid='captcha-image'
              src={image}
              alt={t('module.auth.captcha')}
              width={112}
              height={32}
              unoptimized
              className='h-full w-full object-cover'
            />
          ) : null}
        </button>
        <Button
          type='button'
          variant='outline'
          size='icon'
          className='h-8 w-8 shrink-0'
          aria-label={refreshLabel}
          title={refreshLabel}
          onClick={onRefresh}
          disabled={disabled || isLoading}
        >
          {isLoading ? (
            <Loader2 className='h-4 w-4 animate-spin' />
          ) : (
            <RefreshCcw className='h-4 w-4' />
          )}
        </Button>
      </div>
      {error ? <p className='text-xs text-red-500'>{error}</p> : null}
    </div>
  );
}
