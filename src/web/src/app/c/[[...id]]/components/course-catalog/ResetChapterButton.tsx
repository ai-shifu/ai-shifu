import {
  memo,
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent,
} from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

import { useShallow } from 'zustand/react/shallow';
import { useCourseStore } from '@/store/use-course-store';
import { useEnvStore } from '@/store/env-store';
import { useSystemStore } from '@/store/use-system-store';

import { useTracking } from '@/hooks/use-tracking';
import { shifu } from '@/lib/shifu/shifu-runtime';
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
import { useSingleFlight } from '@/hooks/use-single-flight';
import {
  LESSON_RESET_LIMIT_REACHED_CODE,
  useLessonResetStatus,
} from '@/hooks/use-lesson-reset-status';
import { fail } from '@/hooks/use-toast';
import { stopActiveLessonStream } from '@/app/c/[[...id]]/events';
import {
  buildResetChapterAnalytics,
  buildResetChapterBlockedAnalytics,
  buildResetChapterConfirmAnalytics,
  RESET_CHAPTER_BLOCKED_EVENT,
  RESET_CHAPTER_CONFIRM_EVENT,
  RESET_CHAPTER_EVENT,
  shouldTrackResetChapter,
} from './reset-chapter-analytics';

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
  const resetButtonClickAtRef = useRef(0);
  const { phase, setFailure } = useLessonResetStatus(lessonId, showConfirm);
  const exhausted = phase === 'exhausted';
  const blockedTrackedRef = useRef(false);

  useEffect(() => {
    if (!showConfirm) {
      blockedTrackedRef.current = false;
      return;
    }
    if (
      !exhausted ||
      blockedTrackedRef.current ||
      !shouldTrackResetChapter(previewMode)
    ) {
      return;
    }
    blockedTrackedRef.current = true;
    try {
      void Promise.resolve(
        trackEvent(
          RESET_CHAPTER_BLOCKED_EVENT,
          buildResetChapterBlockedAnalytics(
            { shifuBid, chapterId, lessonId },
            'catalog',
          ),
        ),
      ).catch(() => {});
    } catch {}
  }, [
    chapterId,
    exhausted,
    lessonId,
    previewMode,
    shifuBid,
    showConfirm,
    trackEvent,
  ]);

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
    if (exhausted) {
      setShowConfirm(false);
      return;
    }
    if (!lessonId || phase !== 'ready') {
      return;
    }

    try {
      stopActiveLessonStream(lessonId);
      await resetChapter(lessonId);
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
    } catch (error) {
      // The backend is the authority on the limit: it answers 4021 when another
      // tab spent the last reset, and the dialog then explains instead of toasting.
      setFailure(error);
      if (
        (error as { code?: number } | null)?.code !==
        LESSON_RESET_LIMIT_REACHED_CODE
      ) {
        fail(
          (error as Error).message ||
            t('module.backend.common.operationFailed'),
        );
      }
    }
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
            <DialogTitle>
              {t(
                exhausted
                  ? 'module.lesson.reset.title'
                  : 'module.lesson.reset.confirmTitle',
              )}
            </DialogTitle>
            <DialogDescription>
              {t(
                exhausted
                  ? 'server.learn.resetLimitReached'
                  : 'module.lesson.reset.confirmContent',
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              onClick={() => {
                void handleConfirm();
              }}
              disabled={
                isResettingCurrentLesson ||
                phase === 'checking' ||
                phase === 'idle'
              }
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
