import { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LessonFeedbackInteractionProps {
  defaultScoreText?: string;
  defaultCommentText?: string;
  placeholder: string;
  submitLabel: string;
  skipLabel: string;
  clearLabel: string;
  readonly?: boolean;
  onSubmit: (score: number, comment: string) => void;
  onSkip: (score: number | null, comment: string) => void;
}

const SCORE_OPTIONS = [1, 2, 3, 4, 5];

const normalizeScore = (raw?: string): number | null => {
  const score = Number(raw || '');
  if (!Number.isInteger(score) || score < 1 || score > 5) {
    return null;
  }
  return score;
};

export default function LessonFeedbackInteraction({
  defaultScoreText,
  defaultCommentText,
  placeholder,
  submitLabel,
  skipLabel,
  clearLabel,
  readonly = false,
  onSubmit,
  onSkip,
}: LessonFeedbackInteractionProps) {
  const initialScore = useMemo(
    () => normalizeScore(defaultScoreText),
    [defaultScoreText],
  );
  const [selectedScore, setSelectedScore] = useState<number | null>(
    initialScore,
  );
  const [comment, setComment] = useState(defaultCommentText || '');
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const resizeTextarea = (element: HTMLTextAreaElement | null) => {
    if (!element) {
      return;
    }
    element.style.height = 'auto';
    const nextHeight = Math.min(Math.max(element.scrollHeight, 36), 120);
    element.style.height = `${nextHeight}px`;
  };

  useEffect(() => {
    setSelectedScore(normalizeScore(defaultScoreText));
  }, [defaultScoreText]);

  useEffect(() => {
    setComment(defaultCommentText || '');
  }, [defaultCommentText]);

  useEffect(() => {
    resizeTextarea(textareaRef.current);
  }, [comment]);

  return (
    <div className='rounded-xl border border-[var(--border)] bg-[var(--card)] p-3'>
      <div className='flex flex-wrap items-center gap-x-2 gap-y-[9px]'>
        {SCORE_OPTIONS.map(score => {
          const selected = selectedScore === score;
          return (
            <button
              key={score}
              type='button'
              disabled={readonly}
              onClick={() => setSelectedScore(score)}
              className={cn(
                'h-8 min-w-8 rounded-md border px-3 text-sm leading-none transition-colors',
                selected
                  ? 'border-primary bg-primary text-white'
                  : 'border-[var(--border)] bg-[var(--background)] text-[var(--foreground)]',
                readonly ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
              )}
            >
              {score}
            </button>
          );
        })}
      </div>
      <div className='mt-[9px] flex flex-wrap items-start gap-2'>
        <div className='relative min-w-[220px] flex-1'>
          <textarea
            ref={textareaRef}
            value={comment}
            disabled={readonly}
            rows={1}
            onChange={event => setComment(event.target.value)}
            placeholder={placeholder}
            className={cn(
              'min-h-9 max-h-[120px] w-full resize-none overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-1.5 pr-8 text-sm leading-5 text-[var(--foreground)] outline-none',
              'placeholder:text-foreground/45 focus:border-primary',
              readonly ? 'cursor-not-allowed opacity-60' : '',
            )}
          />
          {!readonly && comment ? (
            <button
              type='button'
              aria-label={clearLabel}
              onClick={() => {
                setComment('');
                textareaRef.current?.focus();
              }}
              className='absolute inset-y-0 right-2 my-auto inline-flex h-5 w-5 items-center justify-center rounded text-foreground/45 transition-colors hover:text-foreground/65'
            >
              <X className='h-3.5 w-3.5' />
            </button>
          ) : null}
        </div>
        <button
          type='button'
          disabled={readonly || !selectedScore}
          onClick={() => {
            if (!selectedScore) {
              return;
            }
            onSubmit(selectedScore, comment.trim());
          }}
          className={cn(
            'h-9 min-w-[72px] self-start rounded-md px-3 text-sm font-medium text-white transition-colors',
            readonly || !selectedScore
              ? 'cursor-not-allowed bg-primary/50'
              : 'bg-primary hover:bg-primary/90',
          )}
        >
          {submitLabel}
        </button>
        <button
          type='button'
          disabled={readonly}
          onClick={() => onSkip(selectedScore, comment.trim())}
          className={cn(
            'h-9 min-w-[84px] self-start rounded-md border border-[var(--border)] bg-[var(--background)] px-3 text-sm font-medium text-[var(--foreground)] transition-colors',
            readonly
              ? 'cursor-not-allowed opacity-60'
              : 'cursor-pointer hover:bg-[var(--card)]',
          )}
        >
          {skipLabel}
        </button>
      </div>
    </div>
  );
}
