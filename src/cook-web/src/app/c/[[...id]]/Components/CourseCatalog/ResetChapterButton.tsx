import { memo, useCallback, useState } from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

import { useShallow } from 'zustand/react/shallow';
import LineButton from '@/c-components/LineButton';
import { useCourseStore } from '@/c-store/useCourseStore';

import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import { shifu } from '@/c-service/Shifu';

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export const ResetChapterButton = ({
  className,
  chapterId,
  chapterName,
  lessonId,
  onClick,
  onConfirm,
}) => {
  const { t } = useTranslation('translation', { keyPrefix: 'c' });
  const { trackEvent } = useTracking();

  const [showConfirm, setShowConfirm] = useState(false)

  const { resetChapter, updateLessonId } = useCourseStore(
    useShallow((state) => ({
      resetChapter: state.resetChapter,
      updateLessonId: state.updateLessonId,
    }))
  );


  const onButtonClick = useCallback(
    async (e) => {
      setShowConfirm(true)
      // Modal.confirm({
      //   title: t('lesson.reset.resetConfirmTitle'),
      //   content: t('lesson.reset.resetConfirmContent'),
      //   onOk: async () => {
      //     await resetChapter(chapterId);
      //     updateLessonId(lessonId);
      //     shifu.resetTools.resetChapter({
      //       chapter_id: chapterId,
      //       chapter_name: chapterName,
      //     });
      //     trackEvent(EVENT_NAMES.RESET_CHAPTER_CONFIRM, {
      //       chapter_id: chapterId,
      //       chapter_name: chapterName,
      //     });
      //     onConfirm?.();
      //   },
      // });
      trackEvent(EVENT_NAMES.RESET_CHAPTER, {
        chapter_id: chapterId,
        chapter_name: chapterName,
      });
      e.detail = { chapterId };
      onClick?.(e);
    },
    [chapterId, chapterName, onClick, trackEvent]
    // [chapterId, chapterName, onClick, onConfirm, resetChapter, t, trackEvent, lessonId, updateLessonId]
  );

  async function handleConfirm() {
    await resetChapter(chapterId);
    updateLessonId(lessonId);
    
    shifu.resetTools.resetChapter({
      chapter_id: chapterId,
      chapter_name: chapterName,
    });
    
    trackEvent(EVENT_NAMES.RESET_CHAPTER_CONFIRM, {
      chapter_id: chapterId,
      chapter_name: chapterName,
    });

    onConfirm?.();

    setShowConfirm(false)
  }

  return (
    <>
      <LineButton
        className={cn(className)}
        onClick={onButtonClick}
        size="small"
        shape="round"
      >
        {t('lesson.reset.resetTitle') }
      </LineButton>
      <Dialog open={showConfirm} onOpenChange={(open) => setShowConfirm(open)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              { t('lesson.reset.resetConfirmTitle') }
            </DialogTitle>
            <DialogDescription>
              { t('lesson.reset.resetConfirmContent') }
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button onClick={handleConfirm}>
              { t('common.ok')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default memo(ResetChapterButton);
