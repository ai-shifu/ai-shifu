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
  value: string;
  maxLength: number;
  disabled: boolean;
  label?: string;
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
      <label
        htmlFor={inputId}
        className='text-sm font-medium'
      >
        {label ?? t('module.profileOnboarding.profileLabel')}
      </label>
      <Textarea
        ref={textareaRef}
        id={inputId}
        className={textareaClassName}
        value={value}
        minRows={8}
        maxRows={14}
        disabled={disabled}
        placeholder={
          placeholder ?? t('module.profileOnboarding.profilePlaceholder')
        }
        aria-describedby={`${inputId}-character-count`}
        onChange={event => onChange(event.target.value)}
      />
      <div
        id={`${inputId}-character-count`}
        className={cn(
          'text-right text-xs text-muted-foreground',
          length > maxLength && 'font-medium text-destructive',
        )}
        aria-live='polite'
      >
        {characterCountText}
      </div>
    </div>
  );
}
