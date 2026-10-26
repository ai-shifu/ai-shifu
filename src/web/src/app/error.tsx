'use client';

import AppErrorFallback from '@/components/error/AppErrorFallback';

type AppErrorPageProps = {
  error: Error & {
    digest?: string;
  };
  reset: () => void;
};

export default function AppErrorPage({ error, reset }: AppErrorPageProps) {
  return (
    <AppErrorFallback
      error={error}
      reset={reset}
    />
  );
}
