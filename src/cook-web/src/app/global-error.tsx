'use client';

import AppErrorFallback from '@/components/error/AppErrorFallback';

type GlobalErrorPageProps = {
  error: Error & {
    digest?: string;
  };
  reset: () => void;
};

export default function GlobalErrorPage({
  error,
  reset,
}: GlobalErrorPageProps) {
  return (
    <html lang='zh-CN'>
      <body>
        <AppErrorFallback
          error={error}
          reset={reset}
        />
      </body>
    </html>
  );
}
