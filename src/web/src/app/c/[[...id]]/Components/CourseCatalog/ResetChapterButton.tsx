import { useRetakeAllowance } from '@/hooks/useRetakeAllowance';
import { RetakeAllowanceMessage } from '@/components/RetakeAllowanceMessage';
import { memo, useCallback, useRef, useState, type MouseEvent } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

import { useShallow } from 'zustand/react/shallow';
import { useCourseStore } from '@/store/useCourseStore';
import { useEnvStore } from '@/store/envStore';
import { useSystemStore } from '@/store/useSystemStore';

import { useTracking } from '@/hooks/useTracking';
import { shifu } from '@/lib/shifu/Shifu';
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
import {
  buildResetChapterAnalytics,
  buildResetChapterConfirmAnalytics,
  RESET_CHAPTER_CONFIRM_EVENT,
  RESET_CHAPTER_EVENT,
  shouldTrackResetChapter,
} from './resetChapterAnalytics';

type ResetChapterButtonProps = {
  className?: string;
  chapterId: string;
  chapterName?: string;
  lessonId?: string;
  onClick?: (event: MouseEvent) => void;
  onConfirm?: () => void;
};

export const ResetChapterButton = ({
  className,
  chapterId,
  chapterName,
  lessonId,
  onClick,
  onConfirm,
}: ResetChapterButtonProps) => {
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const shifuBid = useEnvStore(state => state.courseId);
  const previewMode = useSystemStore(state => state.previewMode);

  const [showConfirm, setShowConfirm] = useState(false);
  const allowance = useRetakeAllowance(showConfirm, lessonId, 'catalog');
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
    (e: MouseEvent) => {
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
      if (shouldTrackResetChapter(previewMode)) {
        trackEvent(
          RESET_CHAPTER_EVENT,
          buildResetChapterAnalytics({ shifuBid, chapterId }),
        );
      }
    },
    [
      chapterId,
      isResettingCurrentLesson,
      onClick,
      previewMode,
      shifuBid,
      showConfirm,
      trackEvent,
    ],
  );

  const handleConfirm = useSingleFlight(async () => {
    if (!lessonId || allowance.blocked) {
      return;
    }

    stopActiveLessonStream(lessonId);
    try {
      await resetChapter(lessonId);
      allowance.result(true);
    } catch {
      allowance.result(false);
      return;
    }
    updateLessonId(lessonId);

    shifu.resetTools.resetChapter({
      chapter_id: chapterId,
      lesson_id: lessonId,
      chapter_name: chapterName,
    });

    if (shouldTrackResetChapter(previewMode)) {
      trackEvent(
        RESET_CHAPTER_CONFIRM_EVENT,
        buildResetChapterConfirmAnalytics({
          shifuBid,
          chapterId,
          lessonId,
        }),
      );
    }

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
          {...(allowance.blocked ? { 'aria-describedby': undefined } : {})}
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
            {!allowance.blocked && (
              <DialogDescription>
                {t('module.lesson.reset.confirmContent')}
              </DialogDescription>
            )}
          </DialogHeader>
          <RetakeAllowanceMessage {...allowance} />
          <DialogFooter>
            <Button
              onClick={() => {
                void handleConfirm();
              }}
              disabled={isResettingCurrentLesson || allowance.blocked}
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
