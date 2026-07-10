import { Download, FileText, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';

interface LessonPdfDownloadCardProps {
  isFollowUpStreaming: boolean;
  isPreparing: boolean;
  onDownload: () => void;
}

export default function LessonPdfDownloadCard({
  isFollowUpStreaming,
  isPreparing,
  onDownload,
}: LessonPdfDownloadCardProps) {
  const { t } = useTranslation();
  const isDisabled = isFollowUpStreaming || isPreparing;
  const helperText = isFollowUpStreaming
    ? t('module.chat.lessonPdfFollowUpInProgress')
    : t('module.chat.lessonPdfPrintHint');

  return (
    <section
      data-lesson-print-exclude='true'
      className='mx-auto mb-8 mt-10 w-full max-w-[1000px] px-5'
      aria-labelledby='lesson-pdf-ready-title'
    >
      <div className='flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between'>
        <div className='flex min-w-0 items-start gap-3'>
          <div className='flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary'>
            <FileText
              className='h-5 w-5'
              aria-hidden='true'
            />
          </div>
          <div className='min-w-0'>
            <h2
              id='lesson-pdf-ready-title'
              className='text-base font-semibold text-foreground'
            >
              {t('module.chat.lessonPdfReadyTitle')}
            </h2>
            <p className='mt-1 text-sm leading-5 text-muted-foreground'>
              {t('module.chat.lessonPdfReadyDescription')}
            </p>
          </div>
        </div>
        <Button
          type='button'
          className='shrink-0'
          disabled={isDisabled}
          aria-describedby='lesson-pdf-download-hint'
          aria-busy={isPreparing}
          onClick={onDownload}
        >
          {isPreparing ? (
            <Loader2
              className='animate-spin'
              aria-hidden='true'
            />
          ) : (
            <Download aria-hidden='true' />
          )}
          {isPreparing
            ? t('module.chat.lessonPdfPreparing')
            : t('module.chat.lessonPdfDownload')}
        </Button>
      </div>
      <p
        id='lesson-pdf-download-hint'
        className='mt-2 text-center text-xs leading-5 text-muted-foreground sm:text-right'
        aria-live='polite'
      >
        {helperText}
      </p>
    </section>
  );
}
