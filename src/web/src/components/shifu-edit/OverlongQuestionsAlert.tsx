'use client';

import React from 'react';
import { AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { QUESTION_NAME_MAX_LENGTH } from '@/constants/ui-constants';
import { type OverlongQuestion, previewQuestion } from './question-length';

export function OverlongQuestionsAlert({
  questions,
}: {
  questions: OverlongQuestion[];
}) {
  const { t } = useTranslation();
  if (!questions.length) {
    return null;
  }

  return (
    <div
      role='alert'
      data-testid='overlong-questions-alert'
      className='mb-3 flex gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive'
    >
      <AlertCircle className='mt-0.5 h-4 w-4 shrink-0' />
      <div className='min-w-0'>
        <p className='font-medium'>
          {t('module.shifu.creationArea.questionTooLongTitle', {
            count: questions.length,
            max: QUESTION_NAME_MAX_LENGTH,
          })}
        </p>
        <ul className='mt-1 list-disc pl-4'>
          {questions.map(question => (
            <li
              key={question.name}
              className='break-all'
            >
              {t('module.shifu.creationArea.questionTooLongItem', {
                preview: previewQuestion(question.name),
                length: question.length,
                max: QUESTION_NAME_MAX_LENGTH,
              })}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
