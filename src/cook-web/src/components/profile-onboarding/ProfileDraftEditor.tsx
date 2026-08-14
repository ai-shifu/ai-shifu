'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Textarea } from '@/components/ui/Textarea';
import { cn } from '@/lib/utils';

export const countUnicodeCodePoints = (value: string) =>
  Array.from(value).length;

export function ProfileDraftEditor({
  inputId = 'learner-profile-draft',
  textareaRef,
  textareaClassName,
  minRows = 8,
  maxRows = 14,
  autoResize = true,
  descriptionId,
  value,
  maxLength,
  disabled,
  label,
  placeholder,
  onChange,
}: {
  inputId?: string;
  textareaRef?: React.Ref<HTMLTextAreaElement>;
  textareaClassName?: string;
  minRows?: number;
  maxRows?: number;
  autoResize?: boolean;
  descriptionId?: string;
  value: string;
  maxLength: number;
  disabled: boolean;
  label?: string | null;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const length = countUnicodeCodePoints(value.trim());
  const characterCountText =
    length > maxLength
      ? t('module.profileOnboarding.characterCountOverLimit', {
          count: length,
          max: maxLength,
        })
      : t('module.profileOnboarding.characterCount', {
          count: length,
          max: maxLength,
        });

  return (
    <div className='space-y-2'>
      {label !== null ? (
        <label
          htmlFor={inputId}
          className='text-sm font-medium'
        >
          {label ?? t('module.profileOnboarding.profileLabel')}
        </label>
      ) : null}
      <Textarea
        ref={textareaRef}
        id={inputId}
        className={textareaClassName}
        value={value}
        rows={minRows}
        minRows={autoResize ? minRows : undefined}
        maxRows={autoResize ? maxRows : undefined}
        disabled={disabled}
        placeholder={
          placeholder ?? t('module.profileOnboarding.profilePlaceholder')
        }
        aria-describedby={[descriptionId, `${inputId}-character-count`]
          .filter(Boolean)
          .join(' ')}
        onChange={event => onChange(event.target.value)}
      />
      <div className='flex justify-end'>
        <div
          id={`${inputId}-character-count`}
          className={cn(
            'shrink-0 text-right text-xs text-muted-foreground',
            length > maxLength && 'font-medium text-destructive',
          )}
          aria-live='polite'
        >
          {characterCountText}
        </div>
      </div>
    </div>
  );
}
