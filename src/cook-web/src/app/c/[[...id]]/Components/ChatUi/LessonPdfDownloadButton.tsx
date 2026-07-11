import { FileDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface LessonPdfDownloadState {
  isFollowUpStreaming: boolean;
  isPreparing: boolean;
}

export interface LessonPdfDownloadButtonProps extends LessonPdfDownloadState {
  isContentReady: boolean;
  onDownload?: () => void;
}

export interface LessonPdfDownloadAction extends LessonPdfDownloadState {
  lessonId: string;
  onDownload: () => void;
}

export default function LessonPdfDownloadButton({
  isContentReady,
  isFollowUpStreaming,
  isPreparing,
  onDownload,
}: LessonPdfDownloadButtonProps) {
  const { t } = useTranslation();
  const isContentAvailable = isContentReady && Boolean(onDownload);
  const isDisabled = !isContentAvailable || isFollowUpStreaming || isPreparing;
  const hint = isPreparing
    ? t('module.chat.lessonPdfPreparing')
    : !isContentAvailable
      ? t('module.chat.lessonPdfContentInProgress')
      : isFollowUpStreaming
        ? t('module.chat.lessonPdfFollowUpInProgress')
        : t('module.chat.lessonPdfPrintHint');
  const accessibleLabel = isPreparing
    ? t('module.chat.lessonPdfPreparing')
    : t('module.chat.lessonPdfDownload');
  const button = (
    <Button
      data-lesson-print-exclude='true'
      type='button'
      variant='ghost'
      size='icon'
      className='h-8 w-8 shrink-0 text-muted-foreground shadow-none hover:bg-muted/50 hover:text-foreground aria-disabled:cursor-not-allowed aria-disabled:opacity-50'
      aria-disabled={isDisabled}
      aria-label={accessibleLabel}
      aria-busy={isPreparing}
      onClick={isDisabled ? undefined : onDownload}
    >
      <FileDown
        className={isPreparing ? 'animate-pulse' : undefined}
        aria-hidden='true'
      />
    </Button>
  );

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent>{hint}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
