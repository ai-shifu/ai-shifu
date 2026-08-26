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
      className='min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain pe-1'
      data-testid='profile-assistant-answers'
    >
      <div className='space-y-1'>
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
      <div className='grid grid-cols-[minmax(0,1fr)_auto] items-start overflow-hidden rounded-xl border border-border bg-muted/25'>
        <Button
          type='button'
          variant='outline'
          size='sm'
          className='col-start-2 row-start-1 m-2 ms-1 min-w-20 rounded-lg bg-background shadow-sm'
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
          className='col-start-1 row-start-1 max-h-28 select-text overflow-y-auto whitespace-pre-wrap break-words p-3 pe-1 text-sm leading-6'
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
      <div className='space-y-2'>
        <label
          htmlFor='profile-assistant-answer'
          className='text-sm font-medium'
        >
          {t('module.profileOnboarding.assistant.resultLabel')}
        </label>
        <Textarea
          id='profile-assistant-answer'
          rows={4}
          className='min-h-28 resize-none'
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
      <div className='flex flex-wrap justify-between gap-2'>
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
