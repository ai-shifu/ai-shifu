'use client';

import { Copy } from 'lucide-react';
import Loading from '@/components/loading';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import type { FlattenedChapterRow } from './CourseChaptersTab';

type CourseChapterDetailDialogProps = {
  open: boolean;
  selectedChapter: FlattenedChapterRow | null;
  loading: boolean;
  copyDisabled: boolean;
  layout: {
    dialogClassName: string;
    bodyClassName: string;
  };
  sections: Array<{
    label: string;
    value: string;
  }>;
  onOpenChange: (open: boolean) => void;
  onCopy: () => void;
  tOperations: (key: string) => string;
};

export default function CourseChapterDetailDialog({
  open,
  selectedChapter,
  loading,
  copyDisabled,
  layout,
  sections,
  onOpenChange,
  onCopy,
  tOperations,
}: CourseChapterDetailDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className={layout.dialogClassName}>
        <DialogHeader className='border-b border-border px-6 py-4 pr-16'>
          <div className='flex items-center justify-between gap-4'>
            <DialogTitle>
              {tOperations('detail.contentDetailDialog.title')}
            </DialogTitle>
            <DialogDescription className='sr-only'>
              {selectedChapter?.title ||
                tOperations('detail.contentDetailDialog.title')}
            </DialogDescription>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='gap-2'
              onClick={onCopy}
              disabled={loading || copyDisabled}
            >
              <Copy className='h-4 w-4' />
              {tOperations('detail.contentDetailDialog.copy')}
            </Button>
          </div>
        </DialogHeader>
        <div className={layout.bodyClassName}>
          {loading ? (
            <div className='flex h-full min-h-[240px] items-center justify-center'>
              <Loading />
            </div>
          ) : sections.some(section => section.value.trim()) ? (
            <div className='space-y-5'>
              {sections.map(section => (
                <section
                  key={section.label}
                  className='space-y-2'
                >
                  <div className='text-sm font-medium text-foreground'>
                    {section.label}
                  </div>
                  <pre className='overflow-x-auto whitespace-pre-wrap break-words rounded-lg border border-border bg-muted/20 p-4 text-sm leading-6 text-foreground'>
                    {section.value.trim() ||
                      tOperations('detail.contentDetailDialog.empty')}
                  </pre>
                </section>
              ))}
            </div>
          ) : (
            <div className='flex h-full min-h-[240px] items-center justify-center text-sm text-muted-foreground'>
              {tOperations('detail.contentDetailDialog.empty')}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
