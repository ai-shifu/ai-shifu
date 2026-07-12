import { useCallback, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { stopActiveLessonStream } from '@/app/c/[[...id]]/events';
import { shifu } from '@/c-service/Shifu';
import { useCourseStore } from '@/c-store/useCourseStore';
import { fail } from '@/hooks/useToast';
import { useSingleFlight } from '@/hooks/useSingleFlight';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';

interface LessonUpdateNoticeProps {
  chapterId: string;
  lessonId?: string;
  lessonTitle?: string;
  className?: string;
  compact?: boolean;
}

export const LessonUpdateNotice = ({
  chapterId,
  lessonId,
  lessonTitle = '',
  className,
  compact = false,
}: LessonUpdateNoticeProps) => {
  const { t } = useTranslation();
  const { resetChapter, resettingLessonId, updateLessonId } = useCourseStore(
    useShallow(state => ({
      resetChapter: state.resetChapter,
      resettingLessonId: state.resettingLessonId,
      updateLessonId: state.updateLessonId,
    })),
  );
  const resolvedLessonId = lessonId || '';
  const isRetakingCurrentLesson =
    Boolean(resolvedLessonId) && resettingLessonId === resolvedLessonId;
  const [showRetakeConfirm, setShowRetakeConfirm] = useState(false);

  const handleRetakeCurrentLesson = useSingleFlight(async () => {
    if (!resolvedLessonId) {
      return false;
    }

    try {
      stopActiveLessonStream(resolvedLessonId);
      await resetChapter(resolvedLessonId);
      updateLessonId(resolvedLessonId);
      shifu.resetTools.resetChapter({
        chapter_id: chapterId,
        lesson_id: resolvedLessonId,
        chapter_name: lessonTitle,
      });
      return true;
    } catch (error) {
      fail(
        (error as Error).message || t('module.backend.common.operationFailed'),
      );
      return false;
    }
  });

  const handleRetakeButtonClick = useCallback(() => {
    if (!resolvedLessonId || isRetakingCurrentLesson) {
      return;
    }

    setShowRetakeConfirm(true);
  }, [isRetakingCurrentLesson, resolvedLessonId]);

  const handleRetakeConfirmOpenChange = useCallback(
    (open: boolean) => {
      if (!open && isRetakingCurrentLesson) {
        return;
      }

      setShowRetakeConfirm(open);
    },
    [isRetakingCurrentLesson],
  );

  return (
    <div
      role='status'
      aria-live='polite'
      className={cn(
        'lesson-update-notice inline-flex max-w-full items-center text-amber-900',
        compact
          ? 'justify-center px-0 py-0 text-xs leading-5'
          : 'rounded-lg border border-amber-200/60 bg-amber-50/80 px-3 py-1.5 text-sm leading-6',
        className,
      )}
    >
      <span className='inline-block min-w-0 max-w-full truncate align-bottom'>
        <Trans
          i18nKey='module.chat.lessonUpdateRecommendRetake'
          components={{
            action: (
              <button
                type='button'
                aria-label={t('module.chat.lessonUpdateRetakeAccessibleLabel')}
                onClick={handleRetakeButtonClick}
                disabled={isRetakingCurrentLesson}
                className={cn(
                  'inline-flex h-auto min-h-0 items-baseline rounded px-0.5 py-0 font-semibold text-amber-950 underline decoration-amber-700/35 underline-offset-[3px] transition-colors hover:bg-amber-100/80 hover:text-amber-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 disabled:cursor-not-allowed disabled:opacity-60',
                  compact
                    ? 'focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--base-background,#fff)]'
                    : 'focus-visible:ring-offset-2 focus-visible:ring-offset-amber-50',
                )}
              />
            ),
          }}
        />
      </span>
      <Dialog
        open={showRetakeConfirm}
        onOpenChange={handleRetakeConfirmOpenChange}
      >
        <DialogContent
          showClose={!isRetakingCurrentLesson}
          onEscapeKeyDown={event => {
            if (isRetakingCurrentLesson) {
              event.preventDefault();
            }
          }}
          onPointerDownOutside={event => {
            if (isRetakingCurrentLesson) {
              event.preventDefault();
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>{t('module.lesson.reset.confirmTitle')}</DialogTitle>
            <DialogDescription>
              {t('module.lesson.reset.confirmContent')}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type='button'
              variant='outline'
              onClick={() => setShowRetakeConfirm(false)}
              disabled={isRetakingCurrentLesson}
            >
              {t('common.core.cancel')}
            </Button>
            <Button
              type='button'
              onClick={() => {
                void handleRetakeCurrentLesson().then(didReset => {
                  if (didReset) {
                    setShowRetakeConfirm(false);
                  }
                });
              }}
              disabled={isRetakingCurrentLesson}
            >
              {t('common.core.ok')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default LessonUpdateNotice;
