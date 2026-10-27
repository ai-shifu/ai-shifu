import { useCallback, useEffect, useRef, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { stopActiveLessonStream } from '@/app/c/[[...id]]/events';
import { shifu } from '@/lib/shifu/Shifu';
import { useCourseStore } from '@/store/useCourseStore';
import { useEnvStore } from '@/store/envStore';
import { useSystemStore } from '@/store/useSystemStore';
import { fail } from '@/hooks/useToast';
import { useSingleFlight } from '@/hooks/useSingleFlight';
import {
  LESSON_RESET_LIMIT_REACHED_CODE,
  useLessonResetStatus,
} from '@/hooks/useLessonResetStatus';
import { useTracking } from '@/hooks/useTracking';
import { startLessonUpdateRetakeTracking } from './lessonUpdateRetakeTracking';
import {
  buildResetChapterBlockedAnalytics,
  RESET_CHAPTER_BLOCKED_EVENT,
  shouldTrackResetChapter,
} from './CourseCatalog/resetChapterAnalytics';
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
  const { trackEvent } = useTracking();
  const shifuBid = useEnvStore(state => state.courseId);
  const previewMode = useSystemStore(state => state.previewMode);
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
  const { phase, setFailure } = useLessonResetStatus(resolvedLessonId, true);
  const exhausted = phase === 'exhausted';
  const blockedTrackedRef = useRef(false);

  useEffect(() => {
    if (!showRetakeConfirm) {
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
            { shifuBid, chapterId, lessonId: resolvedLessonId },
            'lesson_update',
          ),
        ),
      ).catch(() => {});
    } catch {}
  }, [
    chapterId,
    exhausted,
    previewMode,
    resolvedLessonId,
    shifuBid,
    showRetakeConfirm,
    trackEvent,
  ]);

  const handleRetakeCurrentLesson = useSingleFlight(async () => {
    if (exhausted) {
      setShowRetakeConfirm(false);
      return false;
    }
    if (
      !resolvedLessonId.trim() ||
      isRetakingCurrentLesson ||
      phase !== 'ready'
    ) {
      return false;
    }

    const finishTracking = startLessonUpdateRetakeTracking({
      shifuBid,
      outlineBid: resolvedLessonId,
      previewMode,
      trackEvent,
    });
    try {
      stopActiveLessonStream(resolvedLessonId);
      await resetChapter(resolvedLessonId);
      updateLessonId(resolvedLessonId);
      shifu.resetTools.resetChapter({
        chapter_id: chapterId,
        lesson_id: resolvedLessonId,
        chapter_name: lessonTitle,
      });
      finishTracking?.('success');
      return true;
    } catch (error) {
      finishTracking?.('failed');
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
      return false;
    }
  });

  const handleRetakeButtonClick = useCallback(() => {
    if (!resolvedLessonId.trim() || isRetakingCurrentLesson) {
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
        {exhausted ? (
          t('module.chat.lessonUpdateReviewAvailable')
        ) : (
          <Trans
            i18nKey='module.chat.lessonUpdateRecommendRetake'
            components={{
              action: (
                <button
                  type='button'
                  aria-label={t(
                    'module.chat.lessonUpdateRetakeAccessibleLabel',
                  )}
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
        )}
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
              disabled={
                isRetakingCurrentLesson ||
                phase === 'checking' ||
                phase === 'idle'
              }
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
