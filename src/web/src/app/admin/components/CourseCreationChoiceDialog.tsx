'use client';

import { ArrowUpRight, Check, Copy, PencilLine, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  buildOnboardingTargetProps,
  ONBOARDING_TARGET_IDS,
} from '@/lib/onboardingTargets';

interface CourseCreationChoiceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  courseCreatorUrl: string | null;
  onAiCourseCreatorClick: () => void;
  onAiCoursePromptCopy: (prompt: string) => Promise<boolean>;
  onManualCreateClick: () => void;
}

export default function CourseCreationChoiceDialog({
  open,
  onOpenChange,
  courseCreatorUrl,
  onAiCourseCreatorClick,
  onAiCoursePromptCopy,
  onManualCreateClick,
}: CourseCreationChoiceDialogProps) {
  const { t } = useTranslation();
  const [copying, setCopying] = useState(false);
  const [copied, setCopied] = useState(false);
  const copyAttemptRef = useRef(0);
  const copyActionLabel = copied
    ? t('component.courseCreationChoiceDialog.copiedAction')
    : t('component.courseCreationChoiceDialog.copyAction');

  useEffect(() => {
    if (!open) {
      copyAttemptRef.current += 1;
      setCopying(false);
      setCopied(false);
    }
  }, [open]);

  const handleCopy = async () => {
    if (copying) return;
    const attempt = ++copyAttemptRef.current;
    setCopying(true);
    const success = await onAiCoursePromptCopy(
      t('component.courseCreationChoiceDialog.aiPrompt'),
    );
    if (copyAttemptRef.current !== attempt) return;
    setCopying(false);
    setCopied(success);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='max-h-[calc(100vh-32px)] overflow-y-auto p-0 sm:max-w-[760px]'>
        <DialogHeader className='px-6 pb-1 pt-6 pe-12 sm:px-8 sm:pt-7 sm:pe-14'>
          <DialogTitle className='text-2xl leading-8'>
            {t('component.courseCreationChoiceDialog.title')}
          </DialogTitle>
          <DialogDescription className='text-sm leading-6'>
            {t('component.courseCreationChoiceDialog.description')}
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-3 px-6 pb-6 sm:px-8 sm:pb-7'>
          <section className='relative overflow-hidden rounded-2xl border border-primary/25 bg-primary/[0.04] p-5'>
            <div className='pointer-events-none absolute -end-12 -top-16 h-40 w-40 rounded-full bg-primary/10 blur-3xl' />
            <div className='relative'>
              <div className='flex flex-wrap items-center gap-3'>
                <span className='flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground'>
                  <Sparkles className='h-5 w-5' />
                </span>
                <h3 className='text-lg font-semibold text-foreground sm:text-xl'>
                  {t('component.courseCreationChoiceDialog.aiTitle')}
                </h3>
                <Badge className='border-0 bg-primary/10 text-primary hover:bg-primary/10'>
                  {t('component.courseCreationChoiceDialog.recommended')}
                </Badge>
              </div>

              <p className='mt-3 max-w-2xl text-sm leading-6 text-muted-foreground'>
                {t('component.courseCreationChoiceDialog.aiDescription')}
              </p>

              <div className='mt-4 flex flex-col gap-3 border-t border-primary/10 pt-4 sm:flex-row sm:items-center sm:justify-between'>
                <div className='min-w-0 text-xs leading-5 text-muted-foreground'>
                  {courseCreatorUrl ? (
                    <a
                      href={courseCreatorUrl}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='mt-1 inline-flex items-center text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline'
                      onClick={onAiCourseCreatorClick}
                      {...buildOnboardingTargetProps(
                        ONBOARDING_TARGET_IDS.lobsterCreateEntry,
                      )}
                    >
                      {t('component.courseCreationChoiceDialog.guideAction')}
                      <ArrowUpRight className='ms-1 h-4 w-4' />
                    </a>
                  ) : null}
                </div>
                <Button
                  className='shrink-0 self-start sm:self-center'
                  disabled={copying}
                  onClick={handleCopy}
                >
                  {copied ? (
                    <Check className='h-4 w-4' />
                  ) : (
                    <Copy className='h-4 w-4' />
                  )}
                  {copyActionLabel}
                </Button>
              </div>
            </div>
          </section>

          <section className='grid w-full grid-cols-[auto_minmax(0,1fr)] items-center gap-3 rounded-2xl border bg-background p-4 text-start sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:px-5'>
            <span className='flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground'>
              <PencilLine className='h-5 w-5' />
            </span>
            <div className='min-w-0'>
              <h3 className='font-semibold text-foreground'>
                {t('component.courseCreationChoiceDialog.manualTitle')}
              </h3>
              <p className='mt-1 text-sm leading-6 text-muted-foreground'>
                {t('component.courseCreationChoiceDialog.manualDescription')}
              </p>
            </div>
            <Button
              variant='outline'
              className='col-start-2 mt-1 shrink-0 justify-self-start sm:col-start-3 sm:row-start-1 sm:mt-0 sm:justify-self-end'
              onClick={onManualCreateClick}
              {...buildOnboardingTargetProps(
                ONBOARDING_TARGET_IDS.blankCreateEntry,
              )}
            >
              {t('component.courseCreationChoiceDialog.manualAction')}
            </Button>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
