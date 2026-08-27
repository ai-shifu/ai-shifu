'use client';

import React from 'react';
import { Check, Copy } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Textarea';

export function ProfileAssistantAnswersView({
  headingRef,
  prompt,
  value,
  disabled,
  processingDisabled = false,
  unresolved,
  onChange,
  onSubmit,
  onBack,
}: {
  headingRef?: React.Ref<HTMLHeadingElement>;
  prompt: string;
  value: string;
  disabled: boolean;
  processingDisabled?: boolean;
  unresolved: boolean;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = React.useState(false);
  const [copyError, setCopyError] = React.useState(false);
  const copyTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const submissionDisabled = disabled || processingDisabled || unresolved;
  const length = Array.from(value).length;
  const overLimit = length > 10_000;
  const copyLabel = t(
    copied
      ? 'module.profileOnboarding.assistant.copied'
      : 'module.profileOnboarding.assistant.copy',
  );

  React.useEffect(
    () => () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    },
    [],
  );

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopyError(false);
      setCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
      setCopyError(true);
    }
  };

  return (
    <section
      className='flex h-full min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain pe-1'
      data-testid='profile-assistant-answers'
    >
      <div className='shrink-0 space-y-1'>
        <h2
          ref={headingRef}
          tabIndex={-1}
          className='text-lg font-semibold outline-none'
        >
          {t('module.profileOnboarding.assistant.title')}
        </h2>
        <p className='text-sm leading-6 text-muted-foreground'>
          {t('module.profileOnboarding.assistant.instructions')}
        </p>
      </div>
      <div className='grid shrink-0 gap-4 md:min-h-0 md:flex-1 md:shrink md:grid-cols-2'>
        <div className='flex min-h-28 flex-col gap-2 md:min-h-0'>
          <div className='relative min-h-28 flex-1 overflow-hidden rounded-xl border border-border/80 bg-background/80 after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:h-16 after:bg-gradient-to-t after:from-background after:via-background/90 after:to-transparent after:content-[""]'>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='absolute bottom-2 end-2 z-10 min-w-20 rounded-lg bg-background shadow-md'
              disabled={disabled}
              aria-label={copyLabel}
              title={copyLabel}
              onClick={() => void copyPrompt()}
            >
              {copied ? (
                <Check
                  className='size-4'
                  aria-hidden='true'
                />
              ) : (
                <Copy
                  className='size-4'
                  aria-hidden='true'
                />
              )}
              {copied
                ? t('module.profileOnboarding.assistant.copied')
                : t('module.profileOnboarding.assistant.copyShort')}
            </Button>
            <div
              tabIndex={0}
              className='relative z-0 h-full max-h-32 select-text overflow-y-auto whitespace-pre-wrap break-words p-3 pb-14 text-sm leading-6 md:max-h-none'
            >
              <span
                dir='auto'
                className='block'
              >
                {prompt}
              </span>
            </div>
          </div>
          {copyError ? (
            <p
              role='alert'
              className='text-sm text-destructive'
            >
              {t('module.profileOnboarding.assistant.copyFailed')}
            </p>
          ) : null}
        </div>
        <div className='flex min-h-40 flex-col gap-2 md:min-h-0'>
          <label
            htmlFor='profile-assistant-answer'
            className='text-sm font-medium'
          >
            {t('module.profileOnboarding.assistant.resultLabel')}
          </label>
          <Textarea
            id='profile-assistant-answer'
            rows={4}
            className='min-h-32 flex-1 resize-none bg-background shadow-sm md:min-h-0'
            value={value}
            disabled={disabled || unresolved}
            aria-invalid={overLimit || undefined}
            aria-describedby='profile-assistant-answer-limit'
            placeholder={t(
              'module.profileOnboarding.assistant.resultPlaceholder',
            )}
            onChange={event => onChange(event.target.value)}
          />
          <p
            id='profile-assistant-answer-limit'
            className={
              overLimit
                ? 'text-xs text-destructive'
                : 'text-xs text-muted-foreground'
            }
            role={overLimit ? 'alert' : undefined}
          >
            {overLimit
              ? t('module.profileOnboarding.assistant.limitError')
              : t('module.profileOnboarding.characterCount', {
                  count: length,
                  max: 10_000,
                })}
          </p>
        </div>
      </div>
      <div className='flex shrink-0 flex-wrap justify-between gap-2'>
        <Button
          type='button'
          variant='ghost'
          disabled={disabled || unresolved}
          onClick={onBack}
        >
          {t('module.profileOnboarding.assistant.back')}
        </Button>
        <Button
          type='button'
          disabled={submissionDisabled || !value.trim() || overLimit}
          onClick={() => onSubmit(value)}
        >
          {t(
            disabled
              ? 'module.profileOnboarding.assistant.processing'
              : 'module.profileOnboarding.assistant.process',
          )}
        </Button>
      </div>
    </section>
  );
}
