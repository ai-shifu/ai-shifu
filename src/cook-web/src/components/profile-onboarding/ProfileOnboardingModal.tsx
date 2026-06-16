'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Textarea } from '@/components/ui/Textarea';
import { cn } from '@/lib/utils';
import {
  type ProfileOnboardingStep,
  parseProfileOnboardingFlow,
} from './profileOnboardingFlow';

type ProfileOnboardingValues = Record<string, string>;

type ProfileOnboardingModalProps = {
  open: boolean;
  markdownflow: string;
  currentValues?: ProfileOnboardingValues;
  errorMessage?: string;
  submitting?: boolean;
  onComplete: (variables: ProfileOnboardingValues) => void | Promise<void>;
  onSkip: () => void | Promise<void>;
};

const PROFILE_ONBOARDING_VARIABLE_LABEL_KEYS: Record<string, string> = {
  sys_user_background:
    'module.profileOnboarding.variableLabels.sys_user_background',
  sys_user_nickname:
    'module.profileOnboarding.variableLabels.sys_user_nickname',
  sys_user_style: 'module.profileOnboarding.variableLabels.sys_user_style',
};

const getVariableLabel = (
  t: ReturnType<typeof useTranslation>['t'],
  variableKey: string,
) => {
  const labelKey = PROFILE_ONBOARDING_VARIABLE_LABEL_KEYS[variableKey];
  return labelKey ? t(labelKey) : variableKey;
};

const normalizeValues = (
  steps: ProfileOnboardingStep[],
  currentValues?: ProfileOnboardingValues,
) =>
  steps.reduce<ProfileOnboardingValues>((acc, step) => {
    const currentValue = currentValues?.[step.variableKey];
    if (typeof currentValue === 'string' && currentValue.trim()) {
      acc[step.variableKey] = currentValue;
    }
    return acc;
  }, {});

export default function ProfileOnboardingModal({
  open,
  markdownflow,
  currentValues,
  errorMessage = '',
  submitting = false,
  onComplete,
  onSkip,
}: ProfileOnboardingModalProps) {
  const { t } = useTranslation();
  const steps = React.useMemo(
    () => parseProfileOnboardingFlow(markdownflow),
    [markdownflow],
  );
  const [activeIndex, setActiveIndex] = React.useState(0);
  const [values, setValues] = React.useState<ProfileOnboardingValues>(() =>
    normalizeValues(steps, currentValues),
  );

  React.useEffect(() => {
    if (!open) {
      return;
    }
    setActiveIndex(0);
    setValues(normalizeValues(steps, currentValues));
  }, [currentValues, open, steps]);

  const activeStep = steps[activeIndex];
  const currentValue = activeStep ? values[activeStep.variableKey] || '' : '';
  const isLastStep = activeIndex >= steps.length - 1;
  const canAdvance = !activeStep || currentValue.trim().length > 0;

  const updateCurrentValue = React.useCallback(
    (value: string) => {
      if (!activeStep) {
        return;
      }
      setValues(current => ({
        ...current,
        [activeStep.variableKey]: value,
      }));
    },
    [activeStep],
  );

  const submitValues = React.useCallback(async () => {
    const trimmedValues = Object.fromEntries(
      Object.entries(values)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => Boolean(value)),
    );
    await onComplete(trimmedValues);
  }, [onComplete, values]);

  const handleNext = React.useCallback(async () => {
    if (!canAdvance || submitting) {
      return;
    }
    if (!activeStep || isLastStep) {
      await submitValues();
      return;
    }
    setActiveIndex(index => Math.min(index + 1, steps.length - 1));
  }, [
    activeStep,
    canAdvance,
    isLastStep,
    steps.length,
    submitValues,
    submitting,
  ]);

  const fallbackPrompt = activeStep
    ? t('module.profileOnboarding.variablePrompt', {
        variable: getVariableLabel(t, activeStep.variableKey),
      })
    : '';
  const prompt = activeStep?.prompt || fallbackPrompt;

  return (
    <Dialog open={open}>
      <DialogContent
        className='max-w-[560px] gap-5 rounded-lg p-0'
        showClose={false}
      >
        <div className='border-b px-6 py-5'>
          <DialogHeader>
            <DialogTitle>{t('module.profileOnboarding.title')}</DialogTitle>
            <DialogDescription>
              {t('module.profileOnboarding.description')}
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className='space-y-4 px-6'>
          {activeStep?.intro ? (
            <div className='max-h-32 overflow-y-auto whitespace-pre-wrap rounded-md bg-muted px-4 py-3 text-sm leading-6 text-foreground'>
              {activeStep.intro}
            </div>
          ) : null}

          {activeStep ? (
            <div className='space-y-3'>
              <div className='rounded-md bg-primary/10 px-4 py-3 text-sm font-medium leading-6 text-foreground'>
                {prompt}
              </div>

              {activeStep.type === 'choice' ? (
                <div className='grid gap-2 sm:grid-cols-2'>
                  {activeStep.options.map(option => {
                    const selected = currentValue === option.value;
                    return (
                      <Button
                        key={option.value}
                        type='button'
                        variant={selected ? 'default' : 'outline'}
                        className={cn(
                          'h-auto min-h-10 justify-start whitespace-normal text-left',
                          selected ? '' : 'bg-background',
                        )}
                        disabled={submitting}
                        onClick={() => updateCurrentValue(option.value)}
                      >
                        {option.label}
                      </Button>
                    );
                  })}
                </div>
              ) : (
                <Textarea
                  value={currentValue}
                  minRows={3}
                  maxRows={5}
                  disabled={submitting}
                  placeholder={t('module.profileOnboarding.inputPlaceholder')}
                  onChange={event => updateCurrentValue(event.target.value)}
                />
              )}
            </div>
          ) : (
            <div className='rounded-md bg-muted px-4 py-3 text-sm'>
              {t('module.profileOnboarding.emptyFlow')}
            </div>
          )}

          {errorMessage ? (
            <div
              role='alert'
              className='rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive'
            >
              {errorMessage}
            </div>
          ) : null}
        </div>

        <DialogFooter className='gap-2 border-t px-6 py-4 sm:justify-between sm:space-x-0'>
          <Button
            type='button'
            variant='ghost'
            disabled={submitting}
            onClick={onSkip}
          >
            {t('module.profileOnboarding.skip')}
          </Button>
          <Button
            type='button'
            disabled={!canAdvance || submitting}
            onClick={handleNext}
          >
            {isLastStep || !activeStep
              ? t('module.profileOnboarding.complete')
              : t('module.profileOnboarding.next')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
