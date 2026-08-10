'use client';

import { memo, useEffect, useRef, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { getLearnerProfile } from '@/c-api/user';
import { useUserStore } from '@/store/useUserStore';
import { LEARNER_PROFILE_CHANGED_EVENT } from '@/lib/learnerProfileEvents';
import { buildUrlWithLessonId } from '@/c-utils/urlUtils';

interface PreviewHeaderBannerProps {
  courseId: string;
  lessonId?: string;
  className?: string;
}

export const PreviewHeaderBanner = ({
  courseId,
  lessonId,
  className,
}: PreviewHeaderBannerProps) => {
  const { t } = useTranslation();
  const [profileActive, setProfileActive] = useState<boolean | null>(null);
  const userScope = useUserStore(state => state.userInfo?.user_id || 'guest');
  const requestSequenceRef = useRef(0);

  useEffect(() => {
    let active = true;
    const refreshProfileState = () => {
      const requestSequence = ++requestSequenceRef.current;
      void getLearnerProfile()
        .then(profile => {
          if (active && requestSequence === requestSequenceRef.current) {
            setProfileActive(Boolean(profile.learner_profile?.trim()));
          }
        })
        .catch(() => {
          if (active && requestSequence === requestSequenceRef.current) {
            setProfileActive(null);
          }
        });
    };

    setProfileActive(null);
    refreshProfileState();
    window.addEventListener(LEARNER_PROFILE_CHANGED_EVENT, refreshProfileState);
    return () => {
      active = false;
      requestSequenceRef.current += 1;
      window.removeEventListener(
        LEARNER_PROFILE_CHANGED_EVENT,
        refreshProfileState,
      );
    };
  }, [userScope]);

  const messageKey =
    profileActive === true
      ? 'module.preview.previewModeBannerWithProfile'
      : profileActive === false
        ? 'module.preview.previewModeBannerWithoutProfile'
        : 'module.preview.previewModeBanner';
  const editCourseUrl = buildUrlWithLessonId(`/shifu/${courseId}`, lessonId);

  return (
    <div className={cn('w-full bg-sky-100 text-sky-800', className)}>
      <div className='flex h-full min-h-10 w-full items-center justify-center px-4 py-2 text-center text-[14px] font-medium leading-5 md:text-[15px]'>
        <span className='inline max-w-full'>
          <Trans
            t={t}
            i18nKey={messageKey}
            components={{
              editLink: (
                <a
                  href={editCourseUrl}
                  className='ml-1 rounded-sm font-semibold underline decoration-sky-700/40 underline-offset-[3px] transition-colors hover:text-sky-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2 focus-visible:ring-offset-sky-100'
                />
              ),
            }}
          />
        </span>
      </div>
    </div>
  );
};

export default memo(PreviewHeaderBanner);
