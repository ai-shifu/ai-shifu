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
import CreateShifuForm, { type CreateShifuValues } from './CreateShifuForm';

interface CourseCreationChoiceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  courseCreatorUrl: string | null;
  onAiCourseCreatorClick: () => void;
  onAiCoursePromptCopy: (prompt: string) => Promise<boolean>;
  onManualCreate: (values: CreateShifuValues) => Promise<void>;
  onManualCreateCancel: () => void;
}

export default function CourseCreationChoiceDialog({
  open,
  onOpenChange,
  courseCreatorUrl,
  onAiCourseCreatorClick,
  onAiCoursePromptCopy,
  onManualCreate,
  onManualCreateCancel,
}: CourseCreationChoiceDialogProps) {
  const { t } = useTranslation();
  const [copying, setCopying] = useState(false);
  const [copied, setCopied] = useState(false);
  const copyAttemptRef = useRef(0);
  const [submitting, setSubmitting] = useState(false);
  const manualSubmitRef = useRef(false);
  const manualEngagedRef = useRef(false);
  const copyActionLabel = copied
    ? t('component.courseCreationChoiceDialog.copiedAction')
    : t('component.courseCreationChoiceDialog.copyAction');

  useEffect(() => {
    if (!open) {
      copyAttemptRef.current += 1;
      setCopying(false);
      setCopied(false);
      manualEngagedRef.current = false;
    }
  }, [open]);

  const handleOpenChange = (nextOpen: boolean) => {
    if (manualSubmitRef.current) return;
    if (!nextOpen && open && manualEngagedRef.current) {
      manualEngagedRef.current = false;
      onManualCreateCancel();
    }
    onOpenChange(nextOpen);
  };

  const handleManualCreate = async (values: CreateShifuValues) => {
    if (manualSubmitRef.current) return;
    manualSubmitRef.current = true;
    setSubmitting(true);
    try {
      await onManualCreate(values);
    } finally {
      manualSubmitRef.current = false;
      setSubmitting(false);
    }
  };

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
      onOpenChange={handleOpenChange}
    >
      <DialogContent
        className='max-h-[calc(100dvh-32px)] max-w-[920px] gap-6 overflow-y-auto rounded-2xl p-5 sm:w-[calc(100vw-48px)] sm:gap-7 sm:rounded-2xl sm:p-8'
        overlayClassName='bg-black/45 backdrop-blur-sm'
        showClose={!submitting}
        onEscapeKeyDown={event => {
          if (manualSubmitRef.current) event.preventDefault();
        }}
      >
        <DialogHeader className='pe-6 text-start'>
          <DialogTitle className='text-2xl leading-8'>
            {t('component.courseCreationChoiceDialog.title')}
          </DialogTitle>
          <DialogDescription className='sr-only'>
            {t('component.courseCreationChoiceDialog.description')}
          </DialogDescription>
        </DialogHeader>

        <div className='grid items-stretch gap-5 md:grid-cols-2'>
          <section className='flex min-w-0 flex-col rounded-xl border border-primary/15 bg-primary/[0.025] p-5 sm:p-6'>
            <div>
              <div className='flex items-center gap-3'>
                <Sparkles
                  aria-hidden='true'
                  className='h-10 w-10 shrink-0 rounded-lg bg-primary/10 p-2.5 text-primary'
                />
                <h3 className='text-xl font-semibold leading-7'>
                  {t('component.courseCreationChoiceDialog.aiTitle')}
                </h3>
              </div>
              <p className='mt-3 text-sm leading-6 text-muted-foreground'>
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
                  variant='outline'
                  className='mt-3 h-auto min-h-11 w-full whitespace-normal rounded-lg border-primary/25 bg-background px-4 py-3 text-sm text-primary hover:bg-primary/5 hover:text-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
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

            <div className='mt-auto pt-5'>
              {courseCreatorUrl ? (
                <a
                  href={courseCreatorUrl}
                  target='_blank'
                  rel='noopener noreferrer'
                  className='inline-flex min-h-11 items-center rounded-sm text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
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

          <section className='flex min-w-0 flex-col rounded-xl border border-border bg-background p-5 sm:p-6'>
            <div>
              <div className='flex items-center gap-3'>
                <PencilLine
                  aria-hidden='true'
                  className='h-10 w-10 shrink-0 rounded-lg bg-muted p-2.5 text-muted-foreground'
                />
                <h3 className='text-xl font-semibold leading-7'>
                  {t('component.courseCreationChoiceDialog.manualTitle')}
                </h3>
              </div>
              <p className='mt-3 text-sm leading-6 text-muted-foreground'>
                {t('component.courseCreationChoiceDialog.manualDescription')}
              </p>
            </div>
            <CreateShifuForm
              open={open}
              submitting={submitting}
              onSubmit={handleManualCreate}
              onInteraction={() => {
                manualEngagedRef.current = true;
              }}
            />
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
