'use client';
import React, { useState } from 'react';
import { Button } from '@/components/ui/Button';
import Link from 'next/link';

import { useShifu } from '@/store';
import Loading from '../loading';
import { useAlert } from '@/components/ui/UseAlert';
import api from '@/api';
import {
  BookOpen,
  ChevronDown,
  ChevronLeft,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  Copy,
  Headphones,
  Presentation,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import Preivew from '@/components/preview';
import ShifuSetting from '@/components/shifu-setting';
import { useTranslation } from 'react-i18next';
import s from './header.module.scss';
import { useTracking } from '@/c-common/hooks/useTracking';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useToast } from '@/hooks/useToast';
import type { LearningMode } from '@/c-types/store';
import { cn } from '@/lib/utils';
import {
  buildCourseLearningUrl,
  buildLearningModeUrl,
  isPublishLearningModeAvailable,
  PUBLISH_LEARNING_MODES,
} from './publishLearningMode';
import { buildOnboardingTargetProps } from '@/lib/onboardingTargets';

const publishModeIcons: Record<LearningMode, LucideIcon> = {
  read: BookOpen,
  listen: Headphones,
  classroom: Presentation,
};

const writeClipboardText = async (text: string) => {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textArea = document.createElement('textarea');
  textArea.value = text;
  textArea.style.position = 'fixed';
  textArea.style.left = '-9999px';
  textArea.style.top = '0';
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();

  try {
    const copied = document.execCommand('copy');
    if (!copied) {
      throw new Error('Copy command failed');
    }
  } finally {
    document.body.removeChild(textArea);
  }
};

type HeaderProps = {
  backHomeTargetId?: string;
  settingsTriggerTargetId?: string;
  settingsOpenSignal?: string;
  settingsShouldStayOpen?: boolean;
  previewTargetId?: string;
  publishTargetId?: string;
};

const Header = ({
  backHomeTargetId,
  settingsTriggerTargetId,
  settingsOpenSignal,
  settingsShouldStayOpen,
  previewTargetId,
  publishTargetId,
}: HeaderProps) => {
  const { t } = useTranslation();
  const alert = useAlert();
  const [publishing, setPublishing] = useState(false);
  const { toast } = useToast();
  const { trackEvent } = useTracking();
  const { isSaving, lastSaveTime, currentShifu, error, actions } = useShifu();
  // Only allow publish when backend grants explicit publish permission.
  const canPublish =
    Boolean(currentShifu?.bid) && currentShifu?.canPublish === true;
  const onShifuSave = async () => {
    if (currentShifu) {
      await actions.loadShifu(currentShifu.bid, { silent: true });
    }
  };
  const getCourseUrl = () =>
    buildCourseLearningUrl(currentShifu?.bid || '', currentShifu?.url);
  const getLearningModeUrl = (mode: LearningMode) =>
    buildLearningModeUrl(getCourseUrl(), mode);
  const isLearningModeAvailable = (mode: LearningMode) =>
    isPublishLearningModeAvailable({
      mode,
      ttsEnabled: currentShifu?.tts_enabled,
    });
  const getPublishModeUnavailableLabel = (mode: LearningMode) => {
    if (!isLearningModeAvailable(mode) && mode === 'listen') {
      return t('component.header.listenModeRequiresTts');
    }

    return null;
  };
  const getPublishModeLabel = (mode: LearningMode) => {
    if (mode === 'classroom') {
      return t('component.header.publishAndOpenClassroomMode');
    }
    if (mode === 'listen') {
      return t('component.header.publishAndOpenListenMode');
    }
    return t('component.header.publishAndOpenReadMode');
  };
  const getCopyModeLabel = (mode: LearningMode) => {
    if (mode === 'classroom') {
      return t('component.header.copyClassroomModeLink');
    }
    if (mode === 'listen') {
      return t('component.header.copyListenModeLink');
    }
    return t('component.header.copyReadModeLink');
  };
  const copyLearningModeUrl = async (mode: LearningMode) => {
    if (!isLearningModeAvailable(mode)) {
      return;
    }

    try {
      await writeClipboardText(getLearningModeUrl(mode));
      trackEvent('creator_publish_link_copy', {
        shifu_bid: currentShifu?.bid || '',
        learning_mode: mode,
      });
      toast({ title: t('component.header.copyLinkSuccess') });
    } catch {
      toast({
        title: t('component.header.copyLinkFailed'),
        variant: 'destructive',
      });
    }
  };
  const copyPublishedUrl = async (
    publishedUrl: string,
    mode?: LearningMode,
  ) => {
    try {
      await writeClipboardText(publishedUrl);
      trackEvent('creator_publish_link_copy', {
        shifu_bid: currentShifu?.bid || '',
        learning_mode: mode || '',
      });
      toast({ title: t('component.header.copyLinkSuccess') });
    } catch {
      toast({
        title: t('component.header.copyLinkFailed'),
        variant: 'destructive',
      });
    }
  };
  const showPublishSuccessAlert = (
    publishedUrl: string,
    mode?: LearningMode,
  ) => {
    alert.showAlert({
      title: t('component.header.publishSuccess'),
      confirmText: t('component.header.publishSuccessDone'),
      showConfirm: false,
      descriptionAsChild: true,
      description: (
        <div className='space-y-4 text-left'>
          <div className='space-y-1'>
            <div className='flex items-center gap-1.5 font-medium text-foreground'>
              <span>{t('component.header.publishSuccessDescription')}</span>
              <TooltipProvider delayDuration={200}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type='button'
                      aria-label={t('component.header.publishSuccessDraftHelp')}
                      className='inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-blue-300'
                    >
                      <CircleHelp className='h-3.5 w-3.5' />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent className='z-[112] max-w-xs text-left leading-5'>
                    {t('component.header.publishSuccessDraftHelp')}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
            <p>{t('component.header.publishSuccessAudienceDescription')}</p>
          </div>
          <div className='space-y-1.5'>
            <div className='text-xs font-medium text-foreground'>
              {t('component.header.learningLink')}
            </div>
            <div className='flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-2'>
              <a
                href={publishedUrl}
                target='_blank'
                rel='noopener noreferrer'
                className='min-w-0 flex-1 break-all text-sm font-medium text-blue-600 hover:underline'
              >
                {publishedUrl}
              </a>
              <button
                type='button'
                aria-label={t('component.header.copyLearningLink')}
                className='flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-blue-600 transition-colors hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-300'
                onClick={() => {
                  void copyPublishedUrl(publishedUrl, mode);
                }}
              >
                <Copy className='h-4 w-4' />
              </button>
            </div>
          </div>
        </div>
      ),
    });
  };
  const openLearningModeUrl = (
    courseUrl: string,
    mode: LearningMode,
    pendingWindow?: Window | null,
  ) => {
    const targetUrl = buildLearningModeUrl(courseUrl, mode);
    if (pendingWindow && !pendingWindow.closed) {
      pendingWindow.opener = null;
      pendingWindow.location.href = targetUrl;
      return true;
    }

    return Boolean(window.open(targetUrl, '_blank', 'noopener,noreferrer'));
  };
  const publish = async (mode?: LearningMode) => {
    if (
      !canPublish ||
      publishing ||
      !currentShifu?.bid ||
      (mode && !isLearningModeAvailable(mode))
    ) {
      return;
    }
    trackEvent('creator_publish_click', {
      shifu_bid: currentShifu?.bid || '',
      learning_mode: mode || '',
    });
    // TODO: publish
    // actions.publishScenario();
    // await actions.saveBlocks(currentShifu?.bid || '');
    const pendingWindow = mode ? window.open('about:blank', '_blank') : null;
    setPublishing(true);
    try {
      await actions.saveMdflow();
      trackEvent('creator_publish_confirm', {
        shifu_bid: currentShifu?.bid || '',
        learning_mode: mode || '',
      });
      const result = await api.publishShifu({
        shifu_bid: currentShifu?.bid || '',
      });
      if (mode) {
        if (openLearningModeUrl(result, mode, pendingWindow)) {
          return;
        }

        showPublishSuccessAlert(buildLearningModeUrl(result, mode), mode);
        return;
      }

      showPublishSuccessAlert(result);
    } catch {
      pendingWindow?.close();
      toast({
        title: t('common.core.actionFailed'),
        variant: 'destructive',
      });
    } finally {
      setPublishing(false);
    }
  };
  return (
    <div className='flex items-center w-full h-16 px-4 py-[11px] bg-white border-b border-gray-200'>
      <div className='flex items-center space-x-4'>
        <Link
          href={'/admin'}
          {...(backHomeTargetId
            ? buildOnboardingTargetProps(backHomeTargetId)
            : {})}
        >
          <ChevronLeft size={24} />
        </Link>

        <div className='flex items-center'>
          {currentShifu?.avatar ? (
            <div className='bg-blue-100 flex items-center justify-center h-10 w-10 rounded-md p-1 mr-2 overflow-hidden'>
              <img
                src={currentShifu?.avatar}
                alt='Profile'
                className='rounded'
              />
            </div>
          ) : null}

          <div className='flex flex-col'>
            <div className='flex items-center'>
              <span className='text-black text-base not-italic font-semibold leading-7'>
                {currentShifu?.name}
              </span>
              {currentShifu?.readonly && (
                <span className={s.readonly}>
                  {t('component.header.readonly')}
                </span>
              )}
              {currentShifu?.archived && (
                <span className={s.archived}>{t('common.core.archived')}</span>
              )}
              <div className='ml-2'>
                <ShifuSetting
                  shifuId={currentShifu?.bid || ''}
                  onSave={onShifuSave}
                  triggerTargetId={settingsTriggerTargetId}
                  openSignal={settingsOpenSignal}
                  shouldStayOpen={settingsShouldStayOpen}
                />
              </div>
            </div>

            <div className='flex items-center'>
              {isSaving && <Loading className='h-4 w-4 mr-1' />}
              {!error && !isSaving && lastSaveTime && (
                <span className='flex flex-row items-center'>
                  <CircleCheck
                    size={16}
                    className='mr-2  text-green-500'
                  />
                </span>
              )}
              {error && (
                <span className='flex flex-row items-center text-red-500'>
                  <CircleAlert
                    size={16}
                    className='mr-2'
                  />{' '}
                  {error}
                </span>
              )}
              {lastSaveTime && (
                <div
                  key={lastSaveTime.getTime()}
                  style={{ color: 'rgba(0, 0, 0, 0.45)' }}
                  className='text-sm not-italic font-normal bg-white leading-5 tracking-normal transform transition-all duration-300 ease-in-out translate-x-0 animate-slide-in'
                >
                  {t('component.header.saved')} {lastSaveTime?.toLocaleString()}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className='flex-1'></div>

      <div className='flex flex-row items-center'>
        <Preivew targetId={previewTargetId} />
        <div className='flex items-center justify-center h-9 rounded-lg cursor-pointer shifu-setting-icon-container ml-2'>
          <DropdownMenu>
            <div className='flex items-center'>
              <Button
                size='sm'
                className='rounded-r-none'
                disabled={!canPublish || publishing}
                {...(publishTargetId && canPublish
                  ? buildOnboardingTargetProps(publishTargetId)
                  : {})}
                onClick={() => {
                  void publish();
                }}
              >
                {publishing && <Loading className='h-4 w-4 mr-1' />}
                <span className='title text-white'>
                  {t('component.header.publish')}
                </span>
              </Button>
              <DropdownMenuTrigger asChild>
                <Button
                  size='sm'
                  className='rounded-l-none border-l border-white/25 px-2'
                  disabled={!canPublish || publishing}
                  aria-label={t('component.header.publishMenuLabel')}
                >
                  <ChevronDown className='h-4 w-4' />
                </Button>
              </DropdownMenuTrigger>
            </div>
            <DropdownMenuContent
              align='end'
              className='w-64 rounded-lg p-1'
            >
              <TooltipProvider delayDuration={200}>
                {PUBLISH_LEARNING_MODES.map(mode => {
                  const ModeIcon = publishModeIcons[mode];
                  const unavailableLabel = getPublishModeUnavailableLabel(mode);
                  const modeDisabled =
                    !canPublish || publishing || Boolean(unavailableLabel);
                  const copyButton = (
                    <button
                      type='button'
                      aria-label={getCopyModeLabel(mode)}
                      className={cn(
                        'mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground/60 opacity-50 transition-all hover:bg-background hover:text-foreground hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 group-hover:opacity-100 group-focus-within:opacity-100',
                        modeDisabled
                          ? 'cursor-not-allowed opacity-30 hover:bg-transparent hover:text-muted-foreground/60 group-hover:opacity-30'
                          : '',
                      )}
                      disabled={modeDisabled}
                      onClick={event => {
                        event.preventDefault();
                        event.stopPropagation();
                        void copyLearningModeUrl(mode);
                      }}
                    >
                      <Copy className='h-3.5 w-3.5' />
                    </button>
                  );
                  const rowContent = (
                    <div
                      className={cn(
                        'group flex items-center rounded-md transition-colors',
                        unavailableLabel
                          ? 'cursor-not-allowed opacity-50'
                          : 'hover:bg-accent focus-within:bg-accent',
                      )}
                    >
                      <DropdownMenuItem
                        asChild
                        disabled={modeDisabled}
                        className={cn(
                          'min-w-0 flex-1 bg-transparent px-3 py-2 text-sm focus:bg-transparent',
                          unavailableLabel
                            ? 'cursor-not-allowed'
                            : 'cursor-pointer',
                        )}
                        onSelect={() => {
                          void publish(mode);
                        }}
                      >
                        <button
                          type='button'
                          disabled={modeDisabled}
                          className={cn(
                            'flex min-w-0 items-center gap-2.5 text-left',
                            unavailableLabel ? 'cursor-not-allowed' : '',
                          )}
                        >
                          <ModeIcon className='h-4 w-4 shrink-0 text-muted-foreground/70' />
                          <span className='truncate'>
                            {getPublishModeLabel(mode)}
                          </span>
                        </button>
                      </DropdownMenuItem>
                      {unavailableLabel ? (
                        copyButton
                      ) : (
                        <Tooltip>
                          <TooltipTrigger asChild>{copyButton}</TooltipTrigger>
                          <TooltipContent
                            side='left'
                            className='z-[113]'
                          >
                            {getCopyModeLabel(mode)}
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  );

                  if (unavailableLabel) {
                    return (
                      <Tooltip key={mode}>
                        <TooltipTrigger asChild>{rowContent}</TooltipTrigger>
                        <TooltipContent
                          side='left'
                          className='z-[113]'
                        >
                          {unavailableLabel}
                        </TooltipContent>
                      </Tooltip>
                    );
                  }

                  return (
                    <React.Fragment key={mode}>{rowContent}</React.Fragment>
                  );
                })}
              </TooltipProvider>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  );
};

export default Header;
