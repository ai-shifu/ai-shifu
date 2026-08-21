import React, { useState } from 'react';
import { Button } from '@/components/button';
import { Eye } from 'lucide-react';
import { useEnvStore } from '@/c-store';
import { useShifu, useUserStore } from '@/store';
import api from '@/api';
import { useTranslation } from 'react-i18next';
import { useTracking } from '@/c-common/hooks/useTracking';
import { useBillingOverview } from '@/hooks/useBillingData';
import { buildOnboardingTargetProps } from '@/lib/onboardingTargets';
import { buildAbsoluteUrlWithLessonId } from '@/c-utils/urlUtils';
import {
  DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE,
  resolveCourseCreditInsufficientAudience,
  showCreditInsufficientToast,
} from '@/lib/creditInsufficientToast';

type PreviewSettingsModalProps = {
  targetId?: string;
};

const PreviewSettingsModal = ({ targetId }: PreviewSettingsModalProps) => {
  const { t } = useTranslation();
  const { currentNode, currentShifu, actions } = useShifu();
  const currentUser = useUserStore(state => state.userInfo);
  const currentUserId = currentUser?.user_bid || currentUser?.user_id || '';
  const isCourseOwner = currentUser
    ? Boolean(
        currentShifu?.created_user_bid &&
        currentUserId &&
        currentShifu.created_user_bid === currentUserId,
      )
    : null;
  const creditInsufficientAudience = resolveCourseCreditInsufficientAudience({
    previewMode: true,
    isCurrentUserCourseOwner: isCourseOwner,
  });
  const { trackEvent } = useTracking();
  const [loading, setLoading] = useState(false);
  const billingEnabled = useEnvStore(state => state.billingEnabled === 'true');
  const { data: billingOverview } = useBillingOverview();
  const debugBlockedByCredits =
    isCourseOwner === true &&
    billingEnabled &&
    billingOverview?.debug_allowed === false;
  const debugAllowed =
    isCourseOwner !== null &&
    (!isCourseOwner ||
      !billingEnabled ||
      billingOverview?.debug_allowed === true);

  const handleStartPreview = async () => {
    if (loading || creditInsufficientAudience === null) {
      return;
    }
    if (debugBlockedByCredits) {
      showCreditInsufficientToast({
        audience: creditInsufficientAudience,
        code: DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE,
      });
      return;
    }
    if (!debugAllowed) {
      return;
    }

    try {
      setLoading(true);
      if (!currentShifu?.readonly) {
        await actions.saveMdflow();
      }
      trackEvent('creator_shifu_preview_click', {
        shifu_bid: currentShifu?.bid || '',
      });
      const result = await api.previewShifu(
        {
          shifu_bid: currentShifu?.bid || '',
          skip: false,
          variables: {},
        },
        {
          creditInsufficientAudience,
        },
      );
      if (result) {
        const currentLessonId =
          (currentNode?.depth ?? 0) > 0 ? currentNode?.bid : undefined;
        window.open(
          buildAbsoluteUrlWithLessonId(result, currentLessonId),
          '_blank',
          'noopener,noreferrer',
        );
      }
    } catch (error) {
      console.error('Preview failed:', error);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div
      className='flex items-center justify-center h-9 rounded-lg cursor-pointer shifu-setting-icon-container ml-2'
      {...(targetId && debugAllowed
        ? buildOnboardingTargetProps(targetId)
        : {})}
    >
      <Button
        variant='ghost'
        size='sm'
        className='h-8 px-2 text-xs font-normal aria-disabled:cursor-not-allowed aria-disabled:opacity-50'
        onClick={handleStartPreview}
        disabled={loading || (!debugAllowed && !debugBlockedByCredits)}
        aria-disabled={debugBlockedByCredits}
        loading={loading}
        icon={Eye}
        iconClassName='h-4 w-4'
      >
        <span className='title'>{t('module.preview.previewAll')}</span>
      </Button>
    </div>
  );
};

export default PreviewSettingsModal;
