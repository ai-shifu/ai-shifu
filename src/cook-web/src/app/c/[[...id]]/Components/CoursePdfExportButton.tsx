import { useCallback, useMemo, useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { downloadLessonPdf } from '@/c-api/lesson';
import { useTracking } from '@/c-common/hooks/useTracking';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import { useCourseStore } from '@/c-store';
import { useEnvStore } from '@/c-store/envStore';
import { useUiLayoutStore } from '@/c-store/useUiLayoutStore';
import { useSystemStore } from '@/c-store/useSystemStore';
import { FRAME_LAYOUT_MOBILE } from '@/c-constants/uiConstants';
import { useToast } from '@/hooks/useToast';
import { Button } from '@/components/ui/Button';

type CoursePdfExportButtonProps = {
  lessonId?: string;
  lessonTitle?: string;
  lessonStatus?: string;
  variant?: 'desktop' | 'mobile';
  className?: string;
};

const EXPORT_CLICK_EVENT = 'course_pdf_export_click';
const EXPORT_SUCCESS_EVENT = 'course_pdf_export_success';
const EXPORT_FAIL_EVENT = 'course_pdf_export_fail';

const sanitizeFileName = (value: string) =>
  String(value || '')
    .replace(/[\\/:*?"<>|]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

export default function CoursePdfExportButton({
  lessonId = '',
  lessonTitle = '',
  lessonStatus = '',
  variant = 'desktop',
  className = '',
}: CoursePdfExportButtonProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const { courseName } = useCourseStore(
    useShallow(state => ({
      courseName: state.courseName,
    })),
  );
  const courseId = useEnvStore(state => state.courseId);
  const { previewMode, learningMode } = useSystemStore(
    useShallow(state => ({
      previewMode: state.previewMode,
      learningMode: state.learningMode,
    })),
  );
  const frameLayout = useUiLayoutStore(state => state.frameLayout);
  const [isExporting, setIsExporting] = useState(false);

  const isReadMode = learningMode === 'read';
  const hasLesson = Boolean(courseId) && Boolean(lessonId);
  const hasRenderableLesson =
    Boolean(courseId) &&
    Boolean(lessonId) &&
    lessonStatus !== LESSON_STATUS_VALUE.LOCKED;
  const canExport = isReadMode && hasLesson && hasRenderableLesson;
  const isMobileViewport = frameLayout === FRAME_LAYOUT_MOBILE;

  const exportMeta = useMemo(
    () => ({
      shifu_bid: courseId,
      outline_bid: lessonId,
      lesson_title: lessonTitle,
      preview_mode: previewMode,
      learning_mode: learningMode,
      export_source: variant === 'mobile' ? 'mobile_header' : 'desktop_header',
      device_type: isMobileViewport ? 'mobile' : 'desktop',
      lesson_status: lessonStatus,
    }),
    [
      courseId,
      isMobileViewport,
      learningMode,
      lessonId,
      lessonStatus,
      lessonTitle,
      previewMode,
      variant,
    ],
  );

  const triggerDownload = useCallback(
    (blob: Blob, fileName: string) => {
      const objectUrl = window.URL.createObjectURL(blob);
      const normalizedFileName =
        sanitizeFileName(fileName) ||
        `${sanitizeFileName(courseName || courseId)} - ${sanitizeFileName(lessonTitle || lessonId)}.pdf`;

      if (isMobileViewport) {
        const previewWindow = window.open(
          objectUrl,
          '_blank',
          'noopener,noreferrer',
        );
        if (!previewWindow) {
          const anchor = document.createElement('a');
          anchor.href = objectUrl;
          anchor.download = normalizedFileName;
          anchor.rel = 'noopener';
          document.body.appendChild(anchor);
          anchor.click();
          anchor.remove();
        }
      } else {
        const anchor = document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = normalizedFileName;
        anchor.rel = 'noopener';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      }

      window.setTimeout(() => {
        window.URL.revokeObjectURL(objectUrl);
      }, 1500);
    },
    [courseId, courseName, isMobileViewport, lessonId, lessonTitle],
  );

  const handleExport = useCallback(async () => {
    if (!canExport || isExporting) {
      if (learningMode !== 'read') {
        toast({
          title: t('module.chat.exportPdfReadModeOnly'),
          variant: 'destructive',
        });
      }
      return;
    }

    setIsExporting(true);
    await trackEvent(EXPORT_CLICK_EVENT, exportMeta);

    try {
      const { blob, fileName } = await downloadLessonPdf(
        courseId,
        lessonId,
        previewMode,
      );
      triggerDownload(blob, fileName);
      await trackEvent(EXPORT_SUCCESS_EVENT, exportMeta);
      toast({
        title: isMobileViewport
          ? t('module.chat.exportPdfMobileHint')
          : t('module.chat.exportPdfSuccess'),
      });
    } catch (error) {
      const errorType =
        error instanceof Error ? error.message : 'export_pdf_failed';
      await trackEvent(EXPORT_FAIL_EVENT, {
        ...exportMeta,
        error_type: errorType,
      });
      toast({
        title: t('module.chat.exportPdfFailed'),
        variant: 'destructive',
      });
    } finally {
      setIsExporting(false);
    }
  }, [
    canExport,
    courseId,
    exportMeta,
    isExporting,
    isMobileViewport,
    learningMode,
    lessonId,
    previewMode,
    t,
    toast,
    trackEvent,
    triggerDownload,
  ]);

  if (!isReadMode) {
    return null;
  }

  if (variant === 'mobile') {
    return (
      <Button
        type='button'
        variant='ghost'
        size='icon'
        className={className}
        aria-label={
          isExporting
            ? t('module.chat.exportPdfLoading')
            : t('module.chat.exportPdf')
        }
        title={
          isExporting
            ? t('module.chat.exportPdfLoading')
            : t('module.chat.exportPdf')
        }
        onClick={() => {
          void handleExport();
        }}
        disabled={!canExport || isExporting}
        aria-busy={isExporting}
      >
        {isExporting ? (
          <Loader2 className='h-4 w-4 animate-spin' />
        ) : (
          <Download className='h-4 w-4' />
        )}
      </Button>
    );
  }

  return (
    <Button
      type='button'
      variant='outline'
      size='sm'
      className={className}
      aria-label={
        isExporting
          ? t('module.chat.exportPdfLoading')
          : t('module.chat.exportPdf')
      }
      onClick={() => {
        void handleExport();
      }}
      disabled={!canExport || isExporting}
      aria-busy={isExporting}
    >
      {isExporting ? (
        <Loader2 className='h-4 w-4 animate-spin' />
      ) : (
        <Download className='h-4 w-4' />
      )}
      <span>
        {isExporting
          ? t('module.chat.exportPdfLoading')
          : t('module.chat.exportPdf')}
      </span>
    </Button>
  );
}
