import React from 'react';

type OnboardingCardProps = {
  title: React.ReactNode;
  description: React.ReactNode;
  stepIndex: number;
  totalSteps: number;
  continueLabel: React.ReactNode;
};

export function OnboardingCard({
  title,
  description,
  stepIndex,
  totalSteps,
  continueLabel,
}: OnboardingCardProps) {
  const progressLabel = `${stepIndex + 1} / ${totalSteps}`;

  return (
    <div className='w-[340px] max-w-[calc(100vw-32px)] rounded-2xl bg-white p-5 text-slate-950 shadow-[0_24px_60px_rgba(15,23,42,0.22)]'>
      <div className='mb-3 inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600'>
        {progressLabel}
      </div>
      <h3 className='text-base font-semibold leading-6'>{title}</h3>
      <div className='mt-2 text-sm leading-6 text-slate-600'>{description}</div>
      <p className='mt-4 text-xs font-medium uppercase tracking-[0.12em] text-slate-400'>
        {continueLabel}
      </p>
    </div>
  );
}
