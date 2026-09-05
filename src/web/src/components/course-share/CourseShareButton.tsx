'use client';

import { useRef, useState } from 'react';
import type { ComponentPropsWithoutRef } from 'react';
import { Share2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useTracking } from '@/hooks/useTracking';
import { Button, type ButtonProps } from '@/components/ui/Button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useToast } from '@/hooks/useToast';
import {
  buildCourseShareContent,
  normalizeCourseShareUrl,
  shareCourse,
  type CourseShareMethod,
  type CourseShareOutcome,
} from '@/lib/courseShare';

export type CourseShareSurface =
  | 'teacher_header'
  | 'learner_desktop_header'
  | 'learner_mobile_header'
  | 'learner_mobile_fullscreen';

export type CourseShareButtonProps = {
  courseTitle: string;
  courseDescription?: string;
  shifuBid: string;
  resolveShareUrl: () => string | null;
  surface: CourseShareSurface;
  showLabel?: boolean;
  label?: string;
  variant?: ButtonProps['variant'];
  size?: ButtonProps['size'];
  className?: string;
  tooltipSide?: ComponentPropsWithoutRef<typeof TooltipContent>['side'];
};

export function CourseShareButton({
  courseTitle,
  courseDescription,
  shifuBid,
  resolveShareUrl,
  surface,
  showLabel = false,
  label,
  variant = 'ghost',
  size = 'icon',
  className,
  tooltipSide = 'top',
}: CourseShareButtonProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const sharingRef = useRef(false);
  const [sharing, setSharing] = useState(false);
  const shareLabel = label ?? t('common.core.share');
  const accessibleLabel = label ?? t('common.core.shareCourse');

  const track = (eventName: string, eventData: Record<string, unknown>) => {
    try {
      void Promise.resolve(trackEvent(eventName, eventData)).catch(() => {});
    } catch {
      // Sharing must remain available when analytics is unavailable.
    }
  };

  const trackResult = (
    method: CourseShareMethod,
    outcome: CourseShareOutcome,
  ) => {
    track('course_share_result', {
      shifu_bid: shifuBid,
      surface,
      method,
      outcome,
    });
  };

  const handleShare = async () => {
    if (sharingRef.current) {
      return;
    }

    sharingRef.current = true;
    setSharing(true);
    track('course_share_click', {
      shifu_bid: shifuBid,
      surface,
    });

    try {
      const url = normalizeCourseShareUrl(resolveShareUrl());
      if (!url) {
        trackResult('clipboard', 'failed');
        toast({
          title: t('common.core.shareFailed'),
          variant: 'destructive',
        });
        return;
      }

      const content = buildCourseShareContent({
        courseTitle,
        courseDescription,
        recommendation: t('common.core.shareCourseMessage', {
          courseName: courseTitle,
        }),
        url,
      });
      const result = await shareCourse(content);
      trackResult(result.method, result.outcome);

      if (result.method === 'clipboard' && result.outcome === 'success') {
        toast({ title: t('common.core.shareContentCopied') });
      } else if (result.outcome === 'failed') {
        toast({
          title: t('common.core.shareFailed'),
          variant: 'destructive',
        });
      }
    } catch {
      trackResult('clipboard', 'failed');
      toast({
        title: t('common.core.shareFailed'),
        variant: 'destructive',
      });
    } finally {
      sharingRef.current = false;
      setSharing(false);
    }
  };

  const button = (
    <Button
      data-lesson-print-exclude='true'
      type='button'
      variant={variant}
      size={size}
      className={className}
      aria-label={accessibleLabel}
      aria-busy={sharing}
      disabled={sharing}
      onClick={() => {
        void handleShare();
      }}
    >
      <Share2 aria-hidden='true' />
      {showLabel ? <span>{shareLabel}</span> : null}
    </Button>
  );

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent side={tooltipSide}>{accessibleLabel}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
