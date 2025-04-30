import { memo, useCallback } from 'react';
import LineButton from 'Components/LineButton';
import classNames from 'classnames';
import { useCourseStore } from 'stores/useCourseStore';
import { Modal } from 'antd';
import { useTracking, EVENT_NAMES } from 'common/hooks/useTracking';
import { useTranslation } from 'react-i18next';
import { shifu } from 'Service/Shifu';

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
  const { resetChapter, updateLessonId } = useCourseStore((state) => ({
    resetChapter: state.resetChapter,
    updateLessonId: state.updateLessonId,
  }));

  const onButtonClick = useCallback(
    async (e) => {
      Modal.confirm({
        title: t('lesson.reset.resetConfirmTitle'),
        content: t('lesson.reset.resetConfirmContent'),
        onOk: async () => {
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
        },
      });
      trackEvent(EVENT_NAMES.RESET_CHAPTER, {
        chapter_id: chapterId,
        chapter_name: chapterName,
      });
      e.detail = { chapterId };
      onClick?.(e);
    },
    [
      chapterId,
      chapterName,
      onClick,
      onConfirm,
      resetChapter,
      t,
      trackEvent,
      lessonId,
      updateLessonId,
    ],
  );

  return (
    <>
      <LineButton
        className={classNames(className)}
        onClick={onButtonClick}
        size="small"
        shape="round"
      >
        {t('lesson.reset.resetTitle')}
      </LineButton>
    </>
  );
};

export default memo(ResetChapterButton);
