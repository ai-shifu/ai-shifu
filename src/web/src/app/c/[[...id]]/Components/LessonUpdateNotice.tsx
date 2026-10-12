import { useCallback, useEffect, useRef, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { stopActiveLessonStream } from '@/app/c/[[...id]]/events';
import { shifu } from '@/lib/shifu/Shifu';
import { useCourseStore } from '@/store/useCourseStore';
import { fail } from '@/hooks/useToast';
import { useSingleFlight } from '@/hooks/useSingleFlight';
import { useLessonResetStatus } from '@/hooks/useLessonResetStatus';
import { useTracking } from '@/hooks/useTracking';
import { useEnvStore } from '@/store/envStore';
import { useSystemStore } from '@/store/useSystemStore';
import {
  RESET_CHAPTER_EVENT,
  RESET_CHAPTER_CONFIRM_EVENT,
  RESET_CHAPTER_BLOCKED_EVENT,
  buildResetChapterAnalytics,
  buildResetChapterConfirmAnalytics,
  buildResetChapterBlockedAnalytics,
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
  const { trackEvent } = useTracking();
  const shifuBid = useEnvStore(state => state.courseId);
  const previewMode = useSystemStore(state => state.previewMode);
  const blocked = phase === 'exhausted' || phase === 'unavailable';
  const blockedTracked = useRef(false);
  const track = useCallback(
    (name: string, payload: Record<string, unknown>) => {
      if (!shouldTrackResetChapter(previewMode)) return;
      try {
        void Promise.resolve(trackEvent(name, payload)).catch(() => {});
      } catch {}
    },
    [previewMode, trackEvent],
  );

  useEffect(() => {
    if (!showRetakeConfirm) {
      blockedTracked.current = false;
      return;
    }
    if (!blocked || blockedTracked.current) return;
    blockedTracked.current = true;
    track(
      RESET_CHAPTER_BLOCKED_EVENT,
      buildResetChapterBlockedAnalytics(
        { shifuBid, chapterId, lessonId: resolvedLessonId },
        'lesson_update',
        phase === 'exhausted' ? 'limit_reached' : 'unavailable',
      ),
    );
  }, [
    blocked,
    chapterId,
    phase,
    resolvedLessonId,
    shifuBid,
    showRetakeConfirm,
    track,
  ]);

  const handleRetakeCurrentLesson = useSingleFlight(async () => {
    if (blocked) {
      setShowRetakeConfirm(false);
      return false;
    }
    if (!resolvedLessonId || phase !== 'ready') {
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
      track(
        RESET_CHAPTER_CONFIRM_EVENT,
        buildResetChapterConfirmAnalytics({
          shifuBid,
          chapterId,
          lessonId: resolvedLessonId,
        }),
      );
      return true;
    } catch (error) {
      setFailure(error);
      if (![4021, 4022].includes((error as { code?: number }).code || 0)) {
        fail(
          (error as Error).message ||
            t('module.backend.common.operationFailed'),
        );
      }
      return false;
    }
  });

  const handleRetakeButtonClick = useCallback(() => {
    if (!resolvedLessonId || isRetakingCurrentLesson) {
      return;
    }

    setShowRetakeConfirm(true);
    track(
      RESET_CHAPTER_EVENT,
      buildResetChapterAnalytics({ shifuBid, chapterId }),
    );
  }, [chapterId, isRetakingCurrentLesson, resolvedLessonId, shifuBid, track]);

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
        {phase !== 'ready' ? (
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
