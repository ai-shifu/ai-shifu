'use client';

import { ArrowUpRight, Check, PencilLine, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

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
      <DialogContent
        className='max-h-[calc(100dvh-32px)] gap-7 overflow-y-auto rounded-2xl p-6 sm:max-w-[840px] sm:gap-8 sm:rounded-2xl sm:p-8'
        overlayClassName='bg-black/45 backdrop-blur-sm'
      >
        <DialogHeader className='pe-6 text-start'>
          <DialogTitle className='text-2xl leading-8 sm:text-3xl sm:leading-9'>
            {t('component.courseCreationChoiceDialog.title')}
          </DialogTitle>
          <DialogDescription className='sr-only'>
            {t('component.courseCreationChoiceDialog.description')}
          </DialogDescription>
        </DialogHeader>

        <div className='grid items-stretch gap-4 sm:grid-cols-2'>
          <section className='min-w-0 rounded-xl border border-primary/15 bg-primary/[0.025] p-5 sm:p-6'>
            <div>
              <div className='flex min-h-8 flex-wrap items-center gap-x-3 gap-y-2'>
                <Sparkles
                  aria-hidden='true'
                  className='h-7 w-7 shrink-0 text-primary'
                />
                <h3 className='text-xl font-semibold leading-7 sm:text-2xl sm:leading-8'>
                  {t('component.courseCreationChoiceDialog.aiTitle')}
                </h3>
              </div>
              <p className='mt-3 text-sm leading-6 text-muted-foreground sm:text-base'>
                {t('component.courseCreationChoiceDialog.aiDescription')}
              </p>
              <p className='mt-1 text-xs leading-5 text-muted-foreground'>
                {t('component.courseCreationChoiceDialog.aiExamples')}
              </p>
            </div>

            <ol className='mt-6 list-decimal space-y-5 ps-5 marker:font-semibold marker:text-primary'>
              <li className='ps-1'>
                <h4 className='text-base font-semibold leading-6'>
                  {t('component.courseCreationChoiceDialog.installStep')}
                </h4>
                <Button
                  className='mt-3 h-auto min-h-11 w-full whitespace-normal rounded-lg px-4 py-3 text-base focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
                  disabled={copying}
                  onClick={handleCopy}
                >
                  {copied ? (
                    <Check
                      aria-hidden='true'
                      className='h-4 w-4'
                    />
                  ) : null}
                  {copyActionLabel}
                </Button>
                <p
                  role='status'
                  className='mt-2 text-sm leading-6 text-muted-foreground'
                >
                  {copied
                    ? t(
                        'component.courseCreationChoiceDialog.copySuccessDescription',
                      )
                    : t('component.courseCreationChoiceDialog.copyHint')}
                </p>
              </li>
              <li className='ps-1'>
                <h4 className='text-base font-semibold leading-6'>
                  {t('component.courseCreationChoiceDialog.createStep')}
                </h4>
                <p className='mt-2 text-sm leading-6 text-muted-foreground'>
                  {t('component.courseCreationChoiceDialog.createExample')}
                </p>
              </li>
            </ol>

            <div>
              {courseCreatorUrl ? (
                <a
                  href={courseCreatorUrl}
                  target='_blank'
                  rel='noopener noreferrer'
                  className='mt-4 inline-flex min-h-9 items-center rounded-sm text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
                  onClick={onAiCourseCreatorClick}
                  {...buildOnboardingTargetProps(
                    ONBOARDING_TARGET_IDS.lobsterCreateEntry,
                  )}
                >
                  {t('component.courseCreationChoiceDialog.guideAction')}
                  <ArrowUpRight
                    aria-hidden='true'
                    className='ms-1 h-4 w-4'
                  />
                </a>
              ) : null}
            </div>
          </section>

          <section className='flex min-w-0 flex-col items-center justify-center rounded-xl border border-border bg-muted/30 px-5 py-8 text-center sm:p-6'>
            <div>
              <div className='flex flex-col items-center gap-4'>
                <PencilLine
                  aria-hidden='true'
                  className='h-12 w-12 shrink-0 rounded-xl bg-background p-3 text-muted-foreground ring-1 ring-border'
                />
                <h3 className='text-xl font-semibold leading-7 sm:text-2xl sm:leading-8'>
                  {t('component.courseCreationChoiceDialog.manualTitle')}
                </h3>
              </div>
              <p className='mt-3 text-sm leading-6 text-muted-foreground sm:text-base'>
                {t('component.courseCreationChoiceDialog.manualDescription')}
              </p>
            </div>
            <Button
              variant='outline'
              className='mt-6 h-auto min-h-11 w-full whitespace-normal rounded-lg border-primary px-4 py-3 text-base text-primary hover:bg-primary/5 hover:text-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
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
