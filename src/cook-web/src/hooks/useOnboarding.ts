import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import api from '@/api';
import type { CreatorOnboardingStatus } from '@/types/onboarding';
import { getOnboardingTargetElement } from '@/lib/onboardingTargets';
import type { OnboardingStep } from '@/components/onboarding/onboardingTypes';

export function useCreatorOnboardingStatus(enabled: boolean) {
  return useSWR<CreatorOnboardingStatus>(
    enabled ? ['creator-onboarding-status'] : null,
    async () =>
      (await api.getCreatorOnboardingStatus({})) as CreatorOnboardingStatus,
    {
      revalidateOnFocus: false,
    },
  );
}

type UseOnboardingOptions = {
  enabled: boolean;
  steps: OnboardingStep[];
  onComplete: () => Promise<void> | void;
  onStepResolved?: (step: OnboardingStep, stepIndex: number) => void;
  onStepMissing?: (step: OnboardingStep, stepIndex: number) => void;
};

const rectEquals = (current: DOMRect | null, next: DOMRect | null) => {
  if (current === next) {
    return true;
  }
  if (!current || !next) {
    return false;
  }
  return (
    current.top === next.top &&
    current.left === next.left &&
    current.width === next.width &&
    current.height === next.height
  );
};

export function useOnboarding({
  enabled,
  steps,
  onComplete,
  onStepResolved,
  onStepMissing,
}: UseOnboardingOptions) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [isCompleting, setIsCompleting] = useState(false);
  const startedRef = useRef(false);
  const completingRef = useRef(false);
  const resolvedStepIdsRef = useRef<Set<string>>(new Set());
  const missingStepIdsRef = useRef<Set<string>>(new Set());
  const onCompleteRef = useRef(onComplete);
  const onStepResolvedRef = useRef(onStepResolved);
  const onStepMissingRef = useRef(onStepMissing);

  onCompleteRef.current = onComplete;
  onStepResolvedRef.current = onStepResolved;
  onStepMissingRef.current = onStepMissing;

  const currentStep = steps[currentStepIndex] || null;

  const resetOnboarding = useCallback(() => {
    startedRef.current = false;
    resolvedStepIdsRef.current = new Set();
    missingStepIdsRef.current = new Set();
    setIsOpen(false);
    setCurrentStepIndex(0);
    setTargetRect(null);
    setIsCompleting(false);
    completingRef.current = false;
  }, []);

  const completeFlow = useCallback(async () => {
    if (completingRef.current) {
      return;
    }
    completingRef.current = true;
    setIsCompleting(true);
    try {
      await onCompleteRef.current();
      setIsOpen(false);
    } finally {
      completingRef.current = false;
      setIsCompleting(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled || steps.length === 0) {
      resetOnboarding();
      return;
    }
    if (startedRef.current) {
      return;
    }
    startedRef.current = true;
    resolvedStepIdsRef.current = new Set();
    missingStepIdsRef.current = new Set();
    setCurrentStepIndex(0);
    setIsOpen(true);
  }, [enabled, resetOnboarding, steps]);

  useEffect(() => {
    if (!isOpen || !currentStep) {
      setTargetRect(null);
      return;
    }

    if (!currentStep.targetId) {
      setTargetRect(null);
      if (!resolvedStepIdsRef.current.has(currentStep.id)) {
        resolvedStepIdsRef.current.add(currentStep.id);
        onStepResolvedRef.current?.(currentStep, currentStepIndex);
      }
      return;
    }

    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;
    let missingTimer: ReturnType<typeof setTimeout> | null = null;

    const syncRect = () => {
      const element = getOnboardingTargetElement(currentStep.targetId);
      if (!element) {
        setTargetRect(current => (current === null ? current : null));
        return false;
      }
      const nextRect = element.getBoundingClientRect();
      const visibleRect =
        nextRect.width > 0 && nextRect.height > 0 ? nextRect : null;
      setTargetRect(current =>
        rectEquals(current, visibleRect) ? current : visibleRect,
      );
      return nextRect.width > 0 && nextRect.height > 0;
    };

    const handleResolved = () => {
      if (!resolvedStepIdsRef.current.has(currentStep.id)) {
        resolvedStepIdsRef.current.add(currentStep.id);
        onStepResolvedRef.current?.(currentStep, currentStepIndex);
      }
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
      if (missingTimer) {
        clearTimeout(missingTimer);
        missingTimer = null;
      }
    };

    const resolvedNow = syncRect();
    if (resolvedNow) {
      handleResolved();
    } else {
      intervalId = setInterval(() => {
        if (cancelled) {
          return;
        }
        if (syncRect()) {
          handleResolved();
        }
      }, 120);
      if (currentStep.skipWhenTargetMissing) {
        missingTimer = setTimeout(() => {
          if (cancelled || resolvedStepIdsRef.current.has(currentStep.id)) {
            return;
          }
          if (!missingStepIdsRef.current.has(currentStep.id)) {
            missingStepIdsRef.current.add(currentStep.id);
            onStepMissingRef.current?.(currentStep, currentStepIndex);
          }
          if (currentStepIndex >= steps.length - 1) {
            void completeFlow();
            return;
          }
          setCurrentStepIndex(index => index + 1);
        }, currentStep.waitForTargetMs ?? 600);
      }
    }

    const handleViewportChange = () => {
      syncRect();
    };

    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);

    return () => {
      cancelled = true;
      if (intervalId) {
        clearInterval(intervalId);
      }
      if (missingTimer) {
        clearTimeout(missingTimer);
      }
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [completeFlow, currentStep, currentStepIndex, isOpen, steps.length]);

  const advance = async () => {
    if (!isOpen || !currentStep || isCompleting) {
      return;
    }
    if (currentStepIndex >= steps.length - 1) {
      await completeFlow();
      return;
    }
    setCurrentStepIndex(index => index + 1);
  };

  const totalSteps = useMemo(() => steps.length, [steps.length]);

  return {
    isOpen,
    currentStep,
    currentStepIndex,
    totalSteps,
    targetRect,
    isCompleting,
    advance,
  };
}
