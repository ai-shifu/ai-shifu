import React from 'react';

type OnboardingCardProps = {
  title: React.ReactNode;
  description: React.ReactNode;
  stepIndex: number;
  totalSteps: number;
  continueLabel: React.ReactNode;
  actionLabel?: React.ReactNode;
  actionHref?: string;
};

export function OnboardingCard({
  title,
  description,
  stepIndex,
  totalSteps,
  continueLabel,
  actionLabel,
  actionHref,
}: OnboardingCardProps) {
  const progressLabel = `${stepIndex + 1} / ${totalSteps}`;

  return (
    <div className='w-[340px] max-w-[calc(100vw-32px)] rounded-2xl bg-white p-5 text-left text-slate-950 shadow-[0_24px_60px_rgba(15,23,42,0.22)]'>
      <div className='mb-3 inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600'>
        {progressLabel}
      </div>
      <h3 className='text-base font-semibold leading-6'>{title}</h3>
      <div className='mt-2 text-left text-sm leading-6 text-slate-600'>
        {description}
      </div>
      {actionHref && actionLabel ? (
        <a
          href={actionHref}
          target='_blank'
          rel='noopener noreferrer'
          onClick={event => event.stopPropagation()}
          className='mt-3 inline-flex text-sm font-medium leading-6 text-blue-600 underline-offset-4 transition-colors hover:text-blue-700 hover:underline'
        >
          {actionLabel}
        </a>
      ) : null}
      <p className='mt-4 text-xs font-medium uppercase tracking-[0.12em] text-slate-400'>
        {continueLabel}
      </p>
    </div>
  );
}
