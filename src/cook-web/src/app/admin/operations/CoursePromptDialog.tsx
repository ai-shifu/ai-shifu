import { type RefObject, type CSSProperties } from 'react';
import { Copy } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AdminOperationCourseItem } from './operation-course-types';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';

type CoursePromptDialogProps = {
  course: AdminOperationCourseItem | null;
  text: string;
  loading: boolean;
  error: string;
  expanded: boolean;
  canToggle: boolean;
  hasText: boolean;
  collapsedStyle: CSSProperties;
  contentRef: RefObject<HTMLDivElement | null>;
  onOpenChange: (open: boolean) => void;
  onCopy: () => void;
  onRetry: (course: AdminOperationCourseItem) => void;
  onToggleExpanded: () => void;
};

export default function CoursePromptDialog({
  course,
  text,
  loading,
  error,
  expanded,
  canToggle,
  hasText,
  collapsedStyle,
  contentRef,
  onOpenChange,
  onCopy,
  onRetry,
  onToggleExpanded,
}: CoursePromptDialogProps) {
  const { t } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');

  return (
    <Dialog
      open={Boolean(course)}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='w-[min(88vw,760px)] max-w-[760px] p-0'>
        <DialogHeader className='border-b border-border px-6 py-4 pr-12'>
          <div className='flex items-center justify-between gap-4'>
            <DialogTitle>{tOperations('coursePromptDialog.title')}</DialogTitle>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='gap-2'
              onClick={onCopy}
              disabled={!hasText || loading || Boolean(error)}
            >
              <Copy className='h-4 w-4' />
              {tOperations('coursePromptDialog.copy')}
            </Button>
          </div>
        </DialogHeader>
        <div className='min-h-[240px] max-h-[460px] overflow-auto px-6 py-5'>
          <section>
            <div className='rounded-lg border border-border bg-muted/20 p-4'>
              {loading ? (
                <div className='flex min-h-[180px] items-center justify-center'>
                  <Loading />
                </div>
              ) : null}
              {!loading && error ? (
                <div className='flex min-h-[180px] flex-col items-center justify-center gap-3 text-center'>
                  <p className='text-sm leading-6 text-destructive'>{error}</p>
                  <button
                    type='button'
                    className='text-sm font-medium text-primary transition-colors hover:text-primary/80'
                    onClick={() => {
                      if (course) {
                        onRetry(course);
                      }
                    }}
                  >
                    {t('common.core.retry')}
                  </button>
                </div>
              ) : null}
              {!loading && !error ? (
                <>
                  <div
                    ref={contentRef}
                    className='break-words whitespace-pre-wrap text-sm leading-6 text-foreground'
                    style={expanded || !canToggle ? undefined : collapsedStyle}
                  >
                    {hasText ? text : tOperations('coursePromptDialog.empty')}
                  </div>
                  {canToggle ? (
                    <div className='mt-3 flex justify-end'>
                      <button
                        type='button'
                        className='text-sm font-medium text-primary transition-colors hover:text-primary/80'
                        onClick={onToggleExpanded}
                      >
                        {expanded
                          ? t('common.core.collapse')
                          : t('common.core.expand')}
                      </button>
                    </div>
                  ) : null}
                </>
              ) : null}
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
