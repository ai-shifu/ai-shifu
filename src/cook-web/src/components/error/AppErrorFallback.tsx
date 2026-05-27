'use client';

import { useEffect, useMemo, useState } from 'react';

type AppError = Error & {
  digest?: string;
};

type ErrorDetails = {
  cause?: string;
  digest?: string;
  message: string;
  name?: string;
  stack?: string;
};

type BrowserDetails = {
  browser: string;
  os: string;
};

type AppErrorFallbackProps = {
  error: AppError;
  reset?: () => void;
};

const ERROR_TITLE = '应用程序发生错误';
const ERROR_DESCRIPTION =
  '页面运行时捕获到以下错误信息，可直接截图或复制给开发同学排查。';
const ERROR_BADGE = 'Application Error';
const FALLBACK_MESSAGE = '未知客户端错误';
const REFRESH_TEXT = '刷新后重试';
const COPY_TEXT = '复制错误信息';
const COPIED_TEXT = '已复制';
const STACK_LINE_LIMIT = 30;
const ERROR_FIELD_LABELS = {
  cause: 'Cause',
  digest: 'Digest',
  browser: 'Browser Info',
  message: 'Message',
  name: 'Error Name',
  url: 'URL',
} as const;

const getBrowserName = (userAgent: string): string => {
  if (/Edg\//i.test(userAgent)) {
    return 'Edge';
  }

  if (/OPR\//i.test(userAgent) || /Opera/i.test(userAgent)) {
    return 'Opera';
  }

  if (/Firefox\//i.test(userAgent)) {
    return 'Firefox';
  }

  if (/Chrome\//i.test(userAgent) || /CriOS\//i.test(userAgent)) {
    return 'Chrome';
  }

  if (/Safari\//i.test(userAgent)) {
    return 'Safari';
  }

  return 'Other';
};

const getOperatingSystem = (userAgent: string, platform: string): string => {
  if (/Mac/i.test(platform) || /Mac OS X/i.test(userAgent)) {
    return 'macOS';
  }

  if (/Win/i.test(platform) || /Windows/i.test(userAgent)) {
    return 'Windows';
  }

  if (/iPhone|iPad|iPod/i.test(userAgent)) {
    return 'iOS';
  }

  if (/Android/i.test(userAgent)) {
    return 'Android';
  }

  if (/Linux/i.test(platform) || /Linux/i.test(userAgent)) {
    return 'Linux';
  }

  return 'Other';
};

const getBrowserDetails = (): BrowserDetails => {
  const userAgent = navigator.userAgent;
  const platform = navigator.platform;

  return {
    browser: getBrowserName(userAgent),
    os: getOperatingSystem(userAgent, platform),
  };
};

const formatDebugLines = (details?: object): string | undefined => {
  if (!details) {
    return undefined;
  }

  const lines = Object.entries(details)
    .filter(([, value]) => value !== undefined && value !== '')
    .map(([key, value]) => `${key}: ${String(value)}`);

  if (!lines.length) {
    return undefined;
  }

  return lines.join('\n');
};

const formatDebugObject = (
  title: string,
  details?: object,
): string | undefined => {
  const lines = formatDebugLines(details);

  return lines ? `${title}:\n${lines}` : undefined;
};

const getErrorMessage = (error: AppError): string => {
  if (typeof error.message === 'string' && error.message.trim()) {
    return error.message;
  }

  return FALLBACK_MESSAGE;
};

const stringifyCause = (cause: unknown): string | undefined => {
  if (!cause) {
    return undefined;
  }

  if (cause instanceof Error) {
    return cause.message || cause.name;
  }

  if (typeof cause === 'string') {
    return cause;
  }

  try {
    return JSON.stringify(cause);
  } catch {
    return String(cause);
  }
};

const getTrimmedStack = (stack?: string): string | undefined => {
  if (!stack) {
    return undefined;
  }

  return stack.split('\n').slice(0, STACK_LINE_LIMIT).join('\n');
};

const getErrorDetails = (error: AppError): ErrorDetails => ({
  cause: stringifyCause(error.cause),
  digest: error.digest,
  message: getErrorMessage(error),
  name: error.name,
  stack: getTrimmedStack(error.stack),
});

const getClipboardText = (
  details: ErrorDetails,
  pageUrl?: string,
  browserDetails?: BrowserDetails,
): string =>
  [
    `Title: ${ERROR_TITLE}`,
    details.name ? `Name: ${details.name}` : undefined,
    `Message: ${details.message}`,
    details.digest ? `Digest: ${details.digest}` : undefined,
    details.cause ? `Cause: ${details.cause}` : undefined,
    pageUrl ? `Current URL: ${pageUrl}` : undefined,
    typeof document !== 'undefined' && document.referrer
      ? `Referrer: ${document.referrer}`
      : undefined,
    formatDebugObject('Browser Info', browserDetails),
    details.stack ? `Stack:\n${details.stack}` : undefined,
  ]
    .filter(Boolean)
    .join('\n');

const reloadPage = () => {
  window.location.reload();
};

export default function AppErrorFallback({ error }: AppErrorFallbackProps) {
  const [canCopy, setCanCopy] = useState(false);
  const [browserDetails, setBrowserDetails] = useState<BrowserDetails>();
  const [copied, setCopied] = useState(false);
  const [pageUrl, setPageUrl] = useState('');
  const details = useMemo(() => getErrorDetails(error), [error]);
  const browserInfoText = useMemo(
    () => formatDebugLines(browserDetails),
    [browserDetails],
  );

  useEffect(() => {
    setBrowserDetails(getBrowserDetails());
    setCanCopy(Boolean(navigator.clipboard));
    setPageUrl(window.location.href);
  }, []);

  const handleCopy = async () => {
    if (!navigator.clipboard) {
      return;
    }

    await navigator.clipboard.writeText(
      getClipboardText(details, pageUrl, browserDetails),
    );
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <main className='flex min-h-dvh items-center justify-center bg-background px-4 py-10 text-foreground sm:px-6'>
      <section className='w-full max-w-3xl rounded-2xl border border-border bg-card p-6 shadow-lg sm:p-8'>
        <div className='space-y-2'>
          <p className='text-sm font-medium text-destructive'>{ERROR_BADGE}</p>
          <h1 className='text-2xl font-semibold tracking-tight text-card-foreground'>
            {ERROR_TITLE}
          </h1>
          <p className='text-sm leading-6 text-muted-foreground'>
            {ERROR_DESCRIPTION}
          </p>
        </div>

        <dl className='mt-6 space-y-3 rounded-xl border border-border bg-muted p-4'>
          {details.name ? (
            <div className='grid gap-1 sm:grid-cols-[120px_1fr]'>
              <dt className='text-sm font-medium text-muted-foreground'>
                {ERROR_FIELD_LABELS.name}
              </dt>
              <dd className='break-words text-sm text-foreground'>
                {details.name}
              </dd>
            </div>
          ) : null}
          <div className='grid gap-1 sm:grid-cols-[120px_1fr]'>
            <dt className='text-sm font-medium text-muted-foreground'>
              {ERROR_FIELD_LABELS.message}
            </dt>
            <dd className='break-words text-sm text-foreground'>
              {details.message}
            </dd>
          </div>
          {details.digest ? (
            <div className='grid gap-1 sm:grid-cols-[120px_1fr]'>
              <dt className='text-sm font-medium text-muted-foreground'>
                {ERROR_FIELD_LABELS.digest}
              </dt>
              <dd className='break-words font-mono text-xs text-foreground'>
                {details.digest}
              </dd>
            </div>
          ) : null}
          {details.cause ? (
            <div className='grid gap-1 sm:grid-cols-[120px_1fr]'>
              <dt className='text-sm font-medium text-muted-foreground'>
                {ERROR_FIELD_LABELS.cause}
              </dt>
              <dd className='break-words text-sm text-foreground'>
                {details.cause}
              </dd>
            </div>
          ) : null}
          {pageUrl ? (
            <div className='grid gap-1 sm:grid-cols-[120px_1fr]'>
              <dt className='text-sm font-medium text-muted-foreground'>
                {ERROR_FIELD_LABELS.url}
              </dt>
              <dd className='break-words font-mono text-xs text-foreground'>
                {pageUrl}
              </dd>
            </div>
          ) : null}
          {browserInfoText ? (
            <div className='grid gap-1 sm:grid-cols-[120px_1fr]'>
              <dt className='text-sm font-medium text-muted-foreground'>
                {ERROR_FIELD_LABELS.browser}
              </dt>
              <dd className='whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-foreground'>
                {browserInfoText}
              </dd>
            </div>
          ) : null}
        </dl>

        {details.stack ? (
          <pre className='mt-4 max-h-[420px] overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border bg-background p-4 font-mono text-xs leading-relaxed text-foreground'>
            {details.stack}
          </pre>
        ) : null}

        <div className='mt-6 flex flex-col gap-3 sm:flex-row sm:items-center'>
          <button
            className='inline-flex h-10 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground transition hover:opacity-90'
            type='button'
            onClick={reloadPage}
          >
            {REFRESH_TEXT}
          </button>
          {canCopy ? (
            <button
              className='inline-flex h-10 items-center justify-center rounded-lg border border-border bg-card px-4 text-sm font-medium text-card-foreground transition hover:bg-muted'
              type='button'
              onClick={() => {
                void handleCopy();
              }}
            >
              {copied ? COPIED_TEXT : COPY_TEXT}
            </button>
          ) : null}
        </div>
      </section>
    </main>
  );
}
