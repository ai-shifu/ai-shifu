'use client';

import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

export const RETENTION_AUTOPLAY_INTERVAL_MS = 8_000;

type RetentionAudience = {
  id:
    | 'shopper'
    | 'basketballFan'
    | 'shopOwner'
    | 'universityStudent'
    | 'stayAtHomeParent'
    | 'entrepreneur'
    | 'primarySchoolStudent'
    | 'photographyEnthusiast'
    | 'physicsStudent'
    | 'officeWorker'
    | 'beginnerRunner'
    | 'danceTeacher';
  label: string;
  body: string;
};

type RetentionSlide = {
  id: 'percentage' | 'opportunityCost' | 'blueSky' | 'warmUp';
  topic: string;
  question: string;
  audiences: RetentionAudience[];
};

export type LearnerProfileRetentionViewProps = {
  headingRef?: React.RefObject<HTMLHeadingElement | null>;
  scrollContainerRef?: React.RefObject<HTMLElement | null>;
  disabled?: boolean;
};

function buildRetentionSlides(t: TFunction): RetentionSlide[] {
  return [
    {
      id: 'percentage',
      topic: t(
        'module.profileOnboarding.dialog.retention.slides.percentage.topic',
      ),
      question: t(
        'module.profileOnboarding.dialog.retention.slides.percentage.question',
      ),
      audiences: [
        {
          id: 'shopper',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.percentage.audiences.shopper.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.percentage.audiences.shopper.body',
          ),
        },
        {
          id: 'basketballFan',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.percentage.audiences.basketballFan.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.percentage.audiences.basketballFan.body',
          ),
        },
        {
          id: 'shopOwner',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.percentage.audiences.shopOwner.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.percentage.audiences.shopOwner.body',
          ),
        },
      ],
    },
    {
      id: 'opportunityCost',
      topic: t(
        'module.profileOnboarding.dialog.retention.slides.opportunityCost.topic',
      ),
      question: t(
        'module.profileOnboarding.dialog.retention.slides.opportunityCost.question',
      ),
      audiences: [
        {
          id: 'universityStudent',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.opportunityCost.audiences.universityStudent.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.opportunityCost.audiences.universityStudent.body',
          ),
        },
        {
          id: 'stayAtHomeParent',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.opportunityCost.audiences.stayAtHomeParent.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.opportunityCost.audiences.stayAtHomeParent.body',
          ),
        },
        {
          id: 'entrepreneur',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.opportunityCost.audiences.entrepreneur.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.opportunityCost.audiences.entrepreneur.body',
          ),
        },
      ],
    },
    {
      id: 'blueSky',
      topic: t(
        'module.profileOnboarding.dialog.retention.slides.blueSky.topic',
      ),
      question: t(
        'module.profileOnboarding.dialog.retention.slides.blueSky.question',
      ),
      audiences: [
        {
          id: 'primarySchoolStudent',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.blueSky.audiences.primarySchoolStudent.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.blueSky.audiences.primarySchoolStudent.body',
          ),
        },
        {
          id: 'photographyEnthusiast',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.blueSky.audiences.photographyEnthusiast.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.blueSky.audiences.photographyEnthusiast.body',
          ),
        },
        {
          id: 'physicsStudent',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.blueSky.audiences.physicsStudent.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.blueSky.audiences.physicsStudent.body',
          ),
        },
      ],
    },
    {
      id: 'warmUp',
      topic: t('module.profileOnboarding.dialog.retention.slides.warmUp.topic'),
      question: t(
        'module.profileOnboarding.dialog.retention.slides.warmUp.question',
      ),
      audiences: [
        {
          id: 'officeWorker',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.warmUp.audiences.officeWorker.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.warmUp.audiences.officeWorker.body',
          ),
        },
        {
          id: 'beginnerRunner',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.warmUp.audiences.beginnerRunner.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.warmUp.audiences.beginnerRunner.body',
          ),
        },
        {
          id: 'danceTeacher',
          label: t(
            'module.profileOnboarding.dialog.retention.slides.warmUp.audiences.danceTeacher.label',
          ),
          body: t(
            'module.profileOnboarding.dialog.retention.slides.warmUp.audiences.danceTeacher.body',
          ),
        },
      ],
    },
  ];
}

export function LearnerProfileRetentionView({
  headingRef,
  scrollContainerRef,
  disabled = false,
}: LearnerProfileRetentionViewProps) {
  const { t } = useTranslation();
  const retentionSlides = React.useMemo(() => buildRetentionSlides(t), [t]);
  const [currentSlideIndex, setCurrentSlideIndex] = React.useState(0);
  const [autoplayLocked, setAutoplayLocked] = React.useState(false);
  const [motionPreferenceResolved, setMotionPreferenceResolved] =
    React.useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = React.useState(false);
  const [pointerReading, setPointerReading] = React.useState(false);
  const [documentHidden, setDocumentHidden] = React.useState(false);
  const [manualAnnouncement, setManualAnnouncement] = React.useState('');
  const [manualAnnouncementVersion, setManualAnnouncementVersion] =
    React.useState(0);
  const readingRegionRef = React.useRef<HTMLDivElement | null>(null);

  const currentSlide = retentionSlides[currentSlideIndex];
  const currentTopic = currentSlide.topic;
  const temporarilyPaused = pointerReading || documentHidden;
  const autoplayRunning =
    motionPreferenceResolved &&
    !prefersReducedMotion &&
    !temporarilyPaused &&
    !autoplayLocked &&
    !disabled;

  const lockAutoplay = React.useCallback(() => {
    if (!disabled) setAutoplayLocked(true);
  }, [disabled]);

  React.useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) {
      setMotionPreferenceResolved(true);
      return;
    }

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => {
      setPrefersReducedMotion(mediaQuery.matches);
      setMotionPreferenceResolved(true);
    };

    updatePreference();
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', updatePreference);
    } else {
      mediaQuery.addListener?.(updatePreference);
    }

    return () => {
      if (mediaQuery.removeEventListener) {
        mediaQuery.removeEventListener('change', updatePreference);
      } else {
        mediaQuery.removeListener?.(updatePreference);
      }
    };
  }, []);

  React.useEffect(() => {
    if (typeof document === 'undefined') return;

    const updateVisibility = () => setDocumentHidden(document.hidden);
    updateVisibility();
    document.addEventListener('visibilitychange', updateVisibility);
    return () =>
      document.removeEventListener('visibilitychange', updateVisibility);
  }, []);

  React.useEffect(() => {
    const scrollContainer = scrollContainerRef?.current;
    if (!scrollContainer) return;

    const passiveOptions = { passive: true };
    scrollContainer.addEventListener('wheel', lockAutoplay, passiveOptions);
    scrollContainer.addEventListener(
      'touchstart',
      lockAutoplay,
      passiveOptions,
    );
    scrollContainer.addEventListener(
      'pointerdown',
      lockAutoplay,
      passiveOptions,
    );
    scrollContainer.addEventListener('keydown', lockAutoplay);

    return () => {
      scrollContainer.removeEventListener('wheel', lockAutoplay);
      scrollContainer.removeEventListener('touchstart', lockAutoplay);
      scrollContainer.removeEventListener('pointerdown', lockAutoplay);
      scrollContainer.removeEventListener('keydown', lockAutoplay);
    };
  }, [lockAutoplay, scrollContainerRef]);

  React.useEffect(() => {
    if (!autoplayRunning) return;

    const timer = window.setTimeout(() => {
      setCurrentSlideIndex(current => (current + 1) % retentionSlides.length);
    }, RETENTION_AUTOPLAY_INTERVAL_MS);

    return () => window.clearTimeout(timer);
  }, [autoplayRunning, currentSlideIndex, retentionSlides.length]);

  React.useEffect(() => {
    readingRegionRef.current?.scrollTo?.({ top: 0, behavior: 'auto' });
    if (readingRegionRef.current) {
      readingRegionRef.current.scrollTop = 0;
    }
  }, [currentSlideIndex]);

  const announceManualSlide = React.useCallback(
    (nextIndex: number) => {
      const nextSlide = retentionSlides[nextIndex];
      setManualAnnouncement(
        t('module.profileOnboarding.dialog.retention.manualAnnouncement', {
          current: nextIndex + 1,
          total: retentionSlides.length,
          topic: nextSlide.topic,
        }),
      );
      setManualAnnouncementVersion(current => current + 1);
    },
    [retentionSlides, t],
  );

  const navigateManually = React.useCallback(
    (direction: -1 | 1) => {
      if (disabled) return;

      const nextIndex =
        (currentSlideIndex + direction + retentionSlides.length) %
        retentionSlides.length;
      lockAutoplay();
      setCurrentSlideIndex(nextIndex);
      announceManualSlide(nextIndex);
    },
    [
      announceManualSlide,
      currentSlideIndex,
      disabled,
      lockAutoplay,
      retentionSlides.length,
    ],
  );

  const pauseForTouch = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === 'touch') {
      lockAutoplay();
    }
  };

  return (
    <section
      data-testid='learner-profile-retention-view'
      className='flex h-auto flex-none flex-col gap-4 sm:h-full sm:min-h-0 sm:flex-1 sm:gap-3 [@media(max-height:620px)]:h-auto [@media(max-height:620px)]:flex-none'
    >
      <div className='shrink-0 space-y-1.5 text-start sm:space-y-2 sm:text-center'>
        <h2
          ref={headingRef}
          tabIndex={-1}
          className='text-xl font-semibold leading-7 outline-none sm:text-3xl sm:font-bold sm:leading-9 [@media(max-height:620px)]:text-2xl [@media(max-height:620px)]:leading-8'
        >
          {t('module.profileOnboarding.dialog.retention.title')}
        </h2>
        <p className='mx-auto max-w-4xl text-sm leading-6 text-muted-foreground sm:text-base sm:leading-6 [@media(max-height:620px)]:text-sm [@media(max-height:620px)]:leading-6'>
          {t('module.profileOnboarding.dialog.retention.description')}
        </p>
      </div>

      <div
        data-testid='learner-profile-retention-carousel'
        data-autoplay={
          autoplayRunning
            ? 'running'
            : temporarilyPaused &&
                !autoplayLocked &&
                !prefersReducedMotion &&
                !disabled
              ? 'temporarily-paused'
              : 'paused'
        }
        role='region'
        aria-roledescription={t(
          'module.profileOnboarding.dialog.retention.carouselRoleDescription',
        )}
        aria-label={t(
          'module.profileOnboarding.dialog.retention.carouselLabel',
        )}
        className='flex flex-none flex-col overflow-visible border-b border-border/70 sm:min-h-0 sm:flex-1 sm:overflow-hidden [@media(max-height:620px)]:flex-none [@media(max-height:620px)]:overflow-visible'
        onPointerEnter={event => {
          if (event.pointerType !== 'touch') setPointerReading(true);
        }}
        onPointerLeave={event => {
          if (event.pointerType !== 'touch') setPointerReading(false);
        }}
        onPointerDownCapture={pauseForTouch}
        onFocusCapture={lockAutoplay}
      >
        <p className='shrink-0 px-4 py-2 text-sm font-medium leading-5 text-foreground/80 sm:px-5 sm:py-2 sm:text-center sm:text-base sm:font-semibold sm:leading-6 [@media(max-height:620px)]:py-2 [@media(max-height:620px)]:text-base [@media(max-height:620px)]:leading-6'>
          {t('module.profileOnboarding.dialog.retention.exampleLead')}
        </p>

        <div
          key={currentSlide.id}
          ref={readingRegionRef}
          data-testid={`learner-profile-retention-slide-${currentSlide.id}`}
          role='group'
          aria-roledescription={t(
            'module.profileOnboarding.dialog.retention.slideRoleDescription',
          )}
          aria-label={t(
            'module.profileOnboarding.dialog.retention.slideLabel',
            {
              current: currentSlideIndex + 1,
              total: retentionSlides.length,
              topic: currentTopic,
            },
          )}
          aria-live='off'
          tabIndex={0}
          className={cn(
            'flex-none overflow-visible px-4 py-4 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/50 sm:min-h-0 sm:flex-1 sm:overflow-y-auto sm:overscroll-contain sm:px-6 sm:py-3 lg:px-8 [@media(max-height:620px)]:flex-none [@media(max-height:620px)]:overflow-visible [@media(max-height:620px)]:px-5 [@media(max-height:620px)]:py-3',
            !prefersReducedMotion &&
              'animate-in fade-in-0 duration-200 motion-reduce:animate-none motion-reduce:duration-0',
          )}
          onWheelCapture={lockAutoplay}
        >
          <div>
            <h3 className='text-lg font-semibold leading-7 text-foreground sm:text-center sm:text-xl sm:leading-7 [@media(max-height:620px)]:text-lg [@media(max-height:620px)]:leading-7'>
              {currentSlide.question}
            </h3>
          </div>

          <div className='mt-2'>
            {currentSlide.audiences.map(audience => (
              <article
                key={`${currentSlide.id}-${audience.id}`}
                className='grid gap-1.5 border-t border-border/70 py-3 first:border-t-0 sm:grid-cols-[minmax(9rem,0.28fr)_minmax(0,1fr)] sm:items-start sm:gap-4 sm:py-2 [@media(max-height:620px)]:gap-4 [@media(max-height:620px)]:py-3'
              >
                <h4 className='text-sm font-semibold leading-6 text-primary sm:text-lg sm:leading-7 [@media(max-height:620px)]:text-sm [@media(max-height:620px)]:leading-6'>
                  {audience.label}
                </h4>
                <p className='text-sm leading-6 text-foreground/85 sm:border-s sm:border-border/80 sm:ps-5 sm:text-base sm:leading-6 [@media(max-height:620px)]:ps-4 [@media(max-height:620px)]:text-sm [@media(max-height:620px)]:leading-6'>
                  {audience.body}
                </p>
              </article>
            ))}
          </div>
        </div>

        <div className='shrink-0 border-t border-border/70 px-3 py-3 sm:px-4 sm:py-2'>
          <div
            className='mb-3 flex gap-1.5 sm:mb-2'
            aria-hidden='true'
          >
            {retentionSlides.map((slide, index) => (
              <span
                key={slide.id}
                className={cn(
                  'h-1 flex-1 rounded-full bg-muted',
                  index === currentSlideIndex && 'bg-primary',
                )}
              />
            ))}
          </div>

          <div className='flex items-center justify-center gap-2 sm:gap-4'>
            <Button
              data-testid='learner-profile-retention-previous'
              type='button'
              variant='ghost'
              size='icon'
              className='min-h-10 min-w-10'
              disabled={disabled}
              aria-label={t(
                'module.profileOnboarding.dialog.retention.previous',
              )}
              onClick={() => navigateManually(-1)}
            >
              <ChevronLeft
                className='rtl:rotate-180'
                aria-hidden='true'
              />
              <span className='sr-only'>
                {t('module.profileOnboarding.dialog.retention.previous')}
              </span>
            </Button>

            <p className='min-w-28 text-center text-xs font-medium text-muted-foreground sm:min-w-48 sm:text-sm'>
              <bdi>
                {t('module.profileOnboarding.dialog.retention.counter', {
                  current: currentSlideIndex + 1,
                  total: retentionSlides.length,
                  topic: currentTopic,
                })}
              </bdi>
            </p>

            <Button
              data-testid='learner-profile-retention-next'
              type='button'
              variant='ghost'
              size='icon'
              className='min-h-10 min-w-10'
              disabled={disabled}
              aria-label={t('module.profileOnboarding.dialog.retention.next')}
              onClick={() => navigateManually(1)}
            >
              <span className='sr-only'>
                {t('module.profileOnboarding.dialog.retention.next')}
              </span>
              <ChevronRight
                className='rtl:rotate-180'
                aria-hidden='true'
              />
            </Button>
          </div>
        </div>
      </div>

      <p
        data-testid='learner-profile-retention-announcement'
        className='sr-only'
        aria-live='polite'
        aria-atomic='true'
      >
        {manualAnnouncement ? (
          <span key={manualAnnouncementVersion}>{manualAnnouncement}</span>
        ) : null}
      </p>
    </section>
  );
}
