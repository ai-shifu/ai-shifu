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
import { useLessonResetStatus } from '@/hooks/useLessonResetStatus';
import { fail } from '@/hooks/useToast';
import { stopActiveLessonStream } from '@/app/c/[[...id]]/events';
import {
  buildResetChapterAnalytics,
  buildResetChapterConfirmAnalytics,
  RESET_CHAPTER_CONFIRM_EVENT,
  RESET_CHAPTER_EVENT,
  shouldTrackResetChapter,
  RESET_CHAPTER_BLOCKED_EVENT,
  buildResetChapterBlockedAnalytics,
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
  const resetButtonClickAtRef = useRef(0);
  const { phase, setFailure } = useLessonResetStatus(lessonId, showConfirm);
  const blockedTrackedRef = useRef(false);
  const blocked = phase === 'exhausted' || phase === 'unavailable';

  useEffect(() => {
    if (!showConfirm) {
      blockedTrackedRef.current = false;
      return;
    }
    if (
      !blocked ||
      blockedTrackedRef.current ||
      !shouldTrackResetChapter(previewMode)
    )
      return;
    blockedTrackedRef.current = true;
    try {
      void Promise.resolve(
        trackEvent(
          RESET_CHAPTER_BLOCKED_EVENT,
          buildResetChapterBlockedAnalytics(
            { shifuBid, chapterId, lessonId },
            'catalog',
            phase === 'exhausted' ? 'limit_reached' : 'unavailable',
          ),
        ),
      ).catch(() => {});
    } catch {}
  }, [
    blocked,
    chapterId,
    lessonId,
    phase,
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
    if (blocked) {
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
      setFailure(error);
      if (![4021, 4022].includes((error as { code?: number }).code || 0)) {
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
                phase === 'ready'
                  ? 'module.lesson.reset.confirmTitle'
                  : 'module.lesson.reset.title',
              )}
            </DialogTitle>
            <DialogDescription>
              {t(
                phase === 'ready'
                  ? 'module.lesson.reset.confirmContent'
                  : phase === 'exhausted'
                    ? 'server.learn.resetLimitReached'
                    : phase === 'unavailable'
                      ? 'server.learn.resetUnavailable'
                      : 'module.chat.loading',
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
