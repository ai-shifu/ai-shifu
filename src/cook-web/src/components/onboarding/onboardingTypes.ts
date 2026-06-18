import type React from 'react';

export type OnboardingStep = {
  id: string;
  title: React.ReactNode;
  description: React.ReactNode;
  targetId?: string;
  skipWhenTargetMissing?: boolean;
  waitForTargetMs?: number;
  highlightPadding?: number;
  actionLabel?: React.ReactNode;
  actionHref?: string;
};
