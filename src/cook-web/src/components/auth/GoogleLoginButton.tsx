'use client';

import { Button } from '@/components/ui/Button';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

interface GoogleLoginButtonProps {
  onClick: () => void | Promise<void>;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
}

const GoogleIcon = () => (
  <svg
    aria-hidden='true'
    className='h-5 w-5'
    viewBox='0 0 24 24'
    focusable='false'
  >
    <path
      fill='#EA4335'
      d='M12 10.2v3.6h5.05c-.22 1.15-.9 2.13-1.92 2.78l3.1 2.42c1.81-1.67 2.85-4.12 2.85-6.96 0-.67-.06-1.32-.18-1.94H12Z'
    />
    <path
      fill='#34A853'
      d='M6.62 14.32 5.7 15.04l-2.48 1.92C5.02 20.3 8.27 22 12 22c2.7 0 4.97-.89 6.62-2.42l-3.1-2.42c-.86.58-1.95.93-3.52.93-2.71 0-5.01-1.83-5.83-4.3Z'
    />
    <path
      fill='#4A90E2'
      d='M3.23 7.88 0.7 5.94C2.45 2.68 6 1 9.86 1c2.26 0 4.23.75 5.8 2.23l-2.47 2.42c-.91-.9-2.15-1.38-3.33-1.38-2.73 0-5.03 1.82-5.83 4.36Z'
    />
    <path
      fill='#FBBC05'
      d='M12 1c3.24 0 5.5 1.33 6.76 2.44L15.3 5.86C14.75 5.34 13.76 4.72 12 4.72c-2.07 0-3.92 1.19-4.78 2.91L3.23 7.88C4.73 3.94 8.07 1 12 1Z'
    />
  </svg>
);

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
      {loading ? <Loader2 className='h-5 w-5 animate-spin' /> : <GoogleIcon />}
      <span>{t('auth.googleLogin')}</span>
    </Button>
  );
}
