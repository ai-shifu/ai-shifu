import React from 'react';

type OnboardingCardProps = {
  title: React.ReactNode;
  description: React.ReactNode;
  stepIndex: number;
  totalSteps: number;
  continueLabel: React.ReactNode;
  actionLabel?: React.ReactNode;
  actionHref?: string;
  skipLabel?: React.ReactNode;
  onSkip?: () => void;
};

export function OnboardingCard({
  title,
  description,
  stepIndex,
  totalSteps,
  continueLabel,
  actionLabel,
  actionHref,
  skipLabel,
  onSkip,
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
      <div className='mt-4 flex items-center justify-between gap-3'>
        <p className='text-xs font-medium uppercase tracking-[0.12em] text-slate-400'>
          {continueLabel}
        </p>
        {skipLabel ? (
          <button
            type='button'
            onClick={event => {
              event.stopPropagation();
              onSkip?.();
            }}
            className='shrink-0 cursor-pointer text-xs font-medium text-slate-400 underline-offset-4 transition-colors hover:text-slate-600 hover:underline'
          >
            {skipLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
