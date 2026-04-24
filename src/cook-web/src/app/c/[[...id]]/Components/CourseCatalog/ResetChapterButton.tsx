import { memo, useCallback, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

import { useShallow } from 'zustand/react/shallow';
import { useCourseStore } from '@/c-store/useCourseStore';

import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import { shifu } from '@/c-service/Shifu';
import styles from './ResetChapterButton.module.scss';

import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { useSingleFlight } from '@/hooks/useSingleFlight';
import { stopActiveLessonStream } from '@/app/c/[[...id]]/events';

export const ResetChapterButton = ({
  className,
  chapterId,
  chapterName,
  lessonId,
  onClick,
  onConfirm,
}) => {
  const { t } = useTranslation();
  const { trackEvent } = useTracking();

  const [showConfirm, setShowConfirm] = useState(false);
  const resetButtonClickAtRef = useRef(0);

  const { resetChapter, resettingLessonId, updateLessonId } = useCourseStore(
    useShallow(state => ({
      resetChapter: state.resetChapter,
      resettingLessonId: state.resettingLessonId,
      updateLessonId: state.updateLessonId,
    })),
  );
  const isResettingCurrentLesson =
    Boolean(lessonId) && resettingLessonId === lessonId;

  const onButtonClick = useCallback(
    e => {
      onClick?.(e);

      const now = Date.now();
      if (
        showConfirm ||
        isResettingCurrentLesson ||
        now - resetButtonClickAtRef.current < 300
      ) {
        return;
      }

      resetButtonClickAtRef.current = now;
      setShowConfirm(true);
      trackEvent(EVENT_NAMES.RESET_CHAPTER, {
        chapter_id: chapterId,
        chapter_name: chapterName,
      });
    },
    [
      chapterId,
      chapterName,
      isResettingCurrentLesson,
      onClick,
      showConfirm,
      trackEvent,
    ],
  );

  const handleConfirm = useSingleFlight(async () => {
    if (!lessonId) {
      return;
    }

    stopActiveLessonStream(lessonId);
    await resetChapter(lessonId);
    updateLessonId(lessonId);

    shifu.resetTools.resetChapter({
      chapter_id: chapterId,
      lesson_id: lessonId,
      chapter_name: chapterName,
    });

    trackEvent(EVENT_NAMES.RESET_CHAPTER_CONFIRM, {
      chapter_id: chapterId,
      lesson_id: lessonId,
      chapter_name: chapterName,
    });

    onConfirm?.();

    setShowConfirm(false);
  });

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open && isResettingCurrentLesson) {
        return;
      }

      setShowConfirm(open);
    },
    [isResettingCurrentLesson],
  );

  return (
    <>
      <Button
        size='sm'
        className={cn(styles.resetChapterButton, className)}
        onClick={onButtonClick}
        disabled={isResettingCurrentLesson}
      >
        {t('module.lesson.reset.title')}
      </Button>
      <Dialog
        open={showConfirm}
        onOpenChange={handleOpenChange}
      >
        <DialogContent
          showClose={!isResettingCurrentLesson}
          onEscapeKeyDown={event => {
            if (isResettingCurrentLesson) {
              event.preventDefault();
            }
          }}
          onPointerDownOutside={event => {
            if (isResettingCurrentLesson) {
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
              onClick={() => {
                void handleConfirm();
              }}
              disabled={isResettingCurrentLesson}
            >
              {isResettingCurrentLesson ? (
                <Loader2 className='h-4 w-4 animate-spin' />
              ) : null}
              {t('common.core.ok')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default memo(ResetChapterButton);
