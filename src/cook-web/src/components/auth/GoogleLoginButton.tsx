'use client';

import { Button } from '@/components/ui/Button';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import Image from 'next/image';
import { useTranslation } from 'react-i18next';
import googleLogo from '@/c-assets/icons/google-logo.png';

interface GoogleLoginButtonProps {
  onClick: () => void | Promise<void>;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
}

export function GoogleLoginButton({
  onClick,
  loading = false,
  disabled = false,
  className,
}: GoogleLoginButtonProps) {
  const { t } = useTranslation();
  return (
    <Button
      type='button'
      variant='outline'
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(
        'w-full flex items-center justify-center space-x-3',
        className,
      )}
      aria-label={t('auth.googleLogin')}
    >
      {loading ? (
        <Loader2 className='h-5 w-5 animate-spin' />
      ) : (
        <Image
          src={googleLogo}
          alt='Google logo'
          width={20}
          height={20}
          className='h-5 w-5'
        />
      )}
      <span>{t('auth.googleLogin')}</span>
    </Button>
  );
}
