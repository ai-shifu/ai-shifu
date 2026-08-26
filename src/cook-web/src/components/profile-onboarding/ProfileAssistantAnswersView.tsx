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
  waitingForQuestion = false,
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
  waitingForQuestion?: boolean;
  unresolved: boolean;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = React.useState(false);
  const [copyError, setCopyError] = React.useState(false);
  const pasteTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const copyTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const composingRef = React.useRef(false);
  const pastePendingRef = React.useRef(false);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const submissionDisabled = disabled || processingDisabled || unresolved;
  const latestRef = React.useRef({
    value,
    disabled: submissionDisabled,
    onSubmit,
  });
  latestRef.current = { value, disabled: submissionDisabled, onSubmit };
  const length = Array.from(value).length;
  const overLimit = length > 10_000;

  const cancelPaste = React.useCallback(() => {
    pastePendingRef.current = false;
    if (pasteTimerRef.current) clearTimeout(pasteTimerRef.current);
  }, []);
  React.useEffect(
    () => () => {
      cancelPaste();
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    },
    [cancelPaste],
  );
  React.useEffect(() => {
    if (submissionDisabled) cancelPaste();
  }, [cancelPaste, submissionDisabled]);

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopyError(false);
      setCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(false), 1800);
    } catch {
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
      <div className='overflow-hidden rounded-xl border border-border bg-muted/25'>
        <div className='flex flex-wrap items-center justify-between gap-2 border-b border-border/70 px-3 py-2'>
          <p className='text-sm font-medium'>
            {t('module.profileOnboarding.assistant.promptLabel')}
          </p>
          <Button
            type='button'
            variant='outline'
            size='sm'
            disabled={disabled}
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
            {t(
              copied
                ? 'module.profileOnboarding.assistant.copied'
                : 'module.profileOnboarding.assistant.copy',
            )}
          </Button>
        </div>
        <div
          tabIndex={0}
          className='max-h-28 select-text overflow-y-auto whitespace-pre-wrap break-words px-3 py-2 text-sm leading-6'
        >
          {prompt}
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
          ref={inputRef}
          rows={4}
          className='min-h-28 resize-none'
          value={value}
          disabled={disabled || unresolved}
          aria-invalid={overLimit || undefined}
          aria-describedby='profile-assistant-answer-limit'
          placeholder={t(
            'module.profileOnboarding.assistant.resultPlaceholder',
          )}
          onCompositionStart={() => {
            composingRef.current = true;
            cancelPaste();
          }}
          onCompositionEnd={() => {
            composingRef.current = false;
            cancelPaste();
          }}
          onPaste={() => {
            cancelPaste();
            pastePendingRef.current = !composingRef.current;
            // A paste that does not change the input must not arm later typing.
            pasteTimerRef.current = setTimeout(() => {
              pastePendingRef.current = false;
            }, 0);
          }}
          onChange={event => {
            const next = event.target.value;
            const shouldProcess =
              pastePendingRef.current && !composingRef.current;
            cancelPaste();
            onChange(next);
            if (
              shouldProcess &&
              !submissionDisabled &&
              next.trim() &&
              Array.from(next).length <= 10_000
            ) {
              pasteTimerRef.current = setTimeout(() => {
                const current = latestRef.current;
                if (
                  !current.disabled &&
                  !composingRef.current &&
                  current.value === next &&
                  inputRef.current?.value === next
                ) {
                  current.onSubmit(next);
                }
              }, 600);
            }
          }}
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
      {waitingForQuestion ? (
        <p
          role='status'
          className='text-sm text-muted-foreground'
        >
          {t('module.profileOnboarding.assistant.waitingForQuestion')}
        </p>
      ) : null}
      <div className='flex flex-wrap justify-between gap-2'>
        <Button
          type='button'
          variant='ghost'
          disabled={disabled || unresolved}
          onClick={() => {
            cancelPaste();
            onBack();
          }}
        >
          {t('module.profileOnboarding.assistant.back')}
        </Button>
        <Button
          type='button'
          disabled={submissionDisabled || !value.trim() || overLimit}
          onClick={() => {
            cancelPaste();
            onSubmit(value);
          }}
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
