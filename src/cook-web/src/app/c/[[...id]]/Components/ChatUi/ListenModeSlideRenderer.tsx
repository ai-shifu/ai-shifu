import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import Image from 'next/image';
import { createPortal } from 'react-dom';
import { Maximize2 } from 'lucide-react';
import { getDocumentFullscreenElement } from '@/c-utils/browserFullscreen';
import { cn } from '@/lib/utils';
import { Avatar, AvatarImage } from '@/components/ui/Avatar';
import { LoadingDots } from '@/components/loading';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/Popover';
import { lessonFeedbackInteractionDefaultValueOptions } from '@/c-utils/lesson-feedback-interaction-defaults';
import { resolveInteractionSubmission } from '@/c-utils/interaction-user-input';
import { isLessonFeedbackInteractionContent } from '@/c-utils/lesson-feedback-interaction';
import { isSystemInteractionContent } from '@/c-utils/system-interaction';
import { type OnSendContentParams } from 'markdown-flow-ui/renderer';
import {
  Slide,
  type Element as SlideElement,
  type ElementSubtitleCue,
  type MobileViewMode,
  type SlidePlayerCustomActionContext,
} from 'markdown-flow-ui/slide';
import { ChatContentItemType, type ChatContentItem } from './useChatLogicHook';
import {
  resolveListenSlideAudioSource,
  resolveListenSlideElementType,
  resolveListenSlideSubtitleCues,
} from './listenModeUtils';
import {
  buildListenMarkerSequenceKey,
  getListenMarkerIdentityKey,
  reconcileListenPlaybackStepCount,
  resolveCurrentStepAudioCompletion,
  type ListenPlaybackState,
} from './listenPlaybackState';
import {
  applyListenPlaybackSpeedToAudioElement,
  formatListenPlaybackSpeed,
  LISTEN_PLAYBACK_SPEED_OPTIONS,
  readListenPlaybackSpeedFromStorage,
  type ListenPlaybackSpeed,
  writeListenPlaybackSpeedToStorage,
} from './listenPlaybackSpeed';
import AskBlock from './AskBlock';
import type { AskMessage } from './AskBlock';
import AskIcon from '@/c-assets/newchat/light/icon_ask.svg';
import './ListenModeRenderer.scss';
import { useListenContentData } from './useListenMode';
import { buildAskListByAnchorElementBid } from './askState';
import { useAskStateStore } from './useAskStateStore';
import { DEFAULT_LISTEN_MOBILE_VIEW_MODE } from './listenModeTypes';
import {
  isListenLessonFeedbackPromptReady,
  LESSON_FEEDBACK_TAIL_INTERACTION_SETTLE_DELAY_MS,
  shouldDelayListenFeedbackPromptForTailInteraction,
} from './lessonFeedbackPromptState';
import { requestClassroomBrowserFullscreen } from '../learningModeUrl';

type ListenSlideElement = SlideElement & {
  blockBid?: string;
  page?: number;
  is_audio_streaming?: boolean;
  isAudioStreaming?: boolean;
  ask_list?: AskMessage[];
  subtitle_cues?: ElementSubtitleCue[];
};

type ListenSlideBufferingText =
  | string
  | {
      waitingForAudio?: string;
      loadingAudio?: string;
      waitingForMoreAudio?: string;
    };

type ListenSlideProps = Omit<
  React.ComponentProps<typeof Slide>,
  'bufferingText'
> & {
  bufferingText?: ListenSlideBufferingText;
};

const ListenSlide = Slide as React.ComponentType<ListenSlideProps>;

const CLASSROOM_PAGE_SHORTCUT_KEY_MAP: Record<
  string,
  'ArrowLeft' | 'ArrowRight'
> = {
  ArrowUp: 'ArrowLeft',
  PageUp: 'ArrowLeft',
  ArrowDown: 'ArrowRight',
  PageDown: 'ArrowRight',
};

const CLASSROOM_PAGE_SHORTCUT_IGNORE_SELECTOR = [
  'input',
  'textarea',
  'select',
  '[contenteditable]:not([contenteditable="false"])',
  '[role="textbox"]',
  '[role="slider"]',
  '[role="listbox"]',
  '[role="combobox"]',
  '[role="tablist"]',
  '[role="menu"]',
  '[role="tree"]',
  '[role="grid"]',
  '[data-player-keyboard-shortcuts-ignore="true"]',
].join(', ');

const CLASSROOM_SPACE_NATIVE_ACTION_SELECTOR = "button, [role='button']";

const isClassroomSpaceShortcutEvent = (event: KeyboardEvent) => {
  const normalizedKey = event.key.toLowerCase();
  return (
    event.code === 'Space' || event.key === ' ' || normalizedKey === 'spacebar'
  );
};

const resolveClassroomPageShortcutKey = (
  event: KeyboardEvent,
): 'ArrowLeft' | 'ArrowRight' | null => {
  const mappedKey = CLASSROOM_PAGE_SHORTCUT_KEY_MAP[event.key];
  if (mappedKey) {
    return mappedKey;
  }

  if (isClassroomSpaceShortcutEvent(event)) {
    return 'ArrowRight';
  }

  return null;
};

const shouldIgnoreClassroomPageShortcutEvent = (event: KeyboardEvent) => {
  if (
    event.defaultPrevented ||
    event.altKey ||
    event.ctrlKey ||
    event.metaKey ||
    event.shiftKey
  ) {
    return true;
  }

  const target = event.target;
  if (!(target instanceof Element)) {
    return false;
  }

  return Boolean(
    target.closest(CLASSROOM_PAGE_SHORTCUT_IGNORE_SELECTOR) ||
    (isClassroomSpaceShortcutEvent(event) &&
      target.closest(CLASSROOM_SPACE_NATIVE_ACTION_SELECTOR)),
  );
};

type ListenSlidePresentationVariant = 'listen' | 'classroom';

interface ListenModeSlideRendererProps {
  items: ChatContentItem[];
  mobileStyle: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
  variant?: ListenSlidePresentationVariant;
  isLoading?: boolean;
  sectionTitle?: string;
  courseName?: string;
  courseAvatar?: string;
  lessonId?: string;
  shifuBid?: string;
  previewMode?: boolean;
  lessonStatus?: string;
  onSend?: (content: OnSendContentParams, blockBid: string) => void;
  onPlayerVisibilityChange?: (visible: boolean) => void;
  onPlaybackStateChange?: (state: {
    isAudioPlaying: boolean;
    isAudioSequenceActive: boolean;
  }) => void;
  onLessonFeedbackPromptStateChange?: (ready: boolean) => void;
  onMobileViewModeChange?: (viewMode: MobileViewMode) => void;
}

interface ListenSlidePresentationProfile {
  includeAudio: boolean;
  showLeadingTextPlaceholder: boolean;
  trackBrowserFullscreen: boolean;
  enablePageShortcutBridge: boolean;
  showPlayerCustomActions: boolean;
  pausePlayerCustomActionOnActive: boolean;
  showMobileAskEntry: boolean;
  showAskOverlays: boolean;
  showManualFullscreenButton: boolean;
  disableLoadingOverlay: boolean;
  playerClassName?: string;
}

// Centralize presentation capabilities so listen/classroom differences do not
// spread through the renderer as one-off mode checks.
const LISTEN_SLIDE_PRESENTATION_PROFILES: Record<
  ListenSlidePresentationVariant,
  ListenSlidePresentationProfile
> = {
  listen: {
    includeAudio: true,
    showLeadingTextPlaceholder: true,
    trackBrowserFullscreen: false,
    enablePageShortcutBridge: false,
    showPlayerCustomActions: true,
    pausePlayerCustomActionOnActive: true,
    showMobileAskEntry: true,
    showAskOverlays: true,
    showManualFullscreenButton: false,
    disableLoadingOverlay: false,
  },
  classroom: {
    includeAudio: false,
    showLeadingTextPlaceholder: false,
    trackBrowserFullscreen: true,
    enablePageShortcutBridge: true,
    showPlayerCustomActions: false,
    pausePlayerCustomActionOnActive: false,
    showMobileAskEntry: false,
    showAskOverlays: false,
    showManualFullscreenButton: true,
    disableLoadingOverlay: true,
    playerClassName: 'classroom-slide-player',
  },
};

const resolveListenSlidePresentationProfile = (
  variant: ListenSlidePresentationVariant,
) => LISTEN_SLIDE_PRESENTATION_PROFILES[variant];

type ResolveRenderSequence = (params: {
  item: ChatContentItem;
  itemType: 'content' | 'interaction';
  fallbackSequence: number;
}) => number;

type PlayerCustomActionState = {
  currentElement?: ListenSlideElement;
  isActive: boolean;
};

type PlayerCustomActionContextSnapshot = PlayerCustomActionState & {
  setActive: (active: boolean) => void;
};

interface ListenSlideAskPlayerActionProps {
  actionRef?: React.MutableRefObject<HTMLButtonElement | null>;
  context: SlidePlayerCustomActionContext;
  label: string;
  onBeforeOpen: () => void;
  onContextChange: (snapshot: PlayerCustomActionContextSnapshot) => void;
  disabled?: boolean;
  renderButton?: boolean;
}

const ListenSlideAskPlayerAction = memo(
  ({
    actionRef,
    context,
    label,
    onBeforeOpen,
    onContextChange,
    disabled = false,
    renderButton = true,
  }: ListenSlideAskPlayerActionProps) => {
    const { currentElement, isActive, setActive, toggleActive } = context;

    useEffect(() => {
      onContextChange({
        currentElement: currentElement as ListenSlideElement | undefined,
        isActive,
        setActive,
      });
    }, [currentElement, isActive, onContextChange, setActive]);

    const handleClick = useCallback(() => {
      if (disabled) {
        return;
      }

      if (!isActive) {
        onBeforeOpen();
      }

      toggleActive();
    }, [disabled, isActive, onBeforeOpen, toggleActive]);

    if (!renderButton) {
      return null;
    }

    return (
      <button
        aria-label={label}
        aria-pressed={isActive}
        className={cn(
          'slide-player__action',
          isActive && 'slide-player__action--active',
        )}
        onClick={handleClick}
        ref={actionRef}
        type='button'
        disabled={disabled}
      >
        <svg
          xmlns='http://www.w3.org/2000/svg'
          width='32'
          height='32'
          viewBox='0 0 32 32'
          fill='none'
          className='slide-player__icon'
        >
          <path
            d='M26.3445 4.74414C26.4675 5.09781 26.6652 5.42133 26.9246 5.69141C27.184 5.96145 27.499 6.17239 27.8474 6.30957L29.8621 7.10254L27.8474 7.89648C27.499 8.03368 27.184 8.24459 26.9246 8.51465C26.6652 8.78475 26.4675 9.10822 26.3445 9.46191L25.6257 11.5264L24.908 9.46191C24.7849 9.10813 24.5864 8.78479 24.3269 8.51465C24.0674 8.24451 23.7526 8.03368 23.4041 7.89648L21.3894 7.10254L23.4041 6.30957C23.7526 6.17238 24.0674 5.96155 24.3269 5.69141C24.5864 5.42126 24.7849 5.09794 24.908 4.74414L25.6257 2.67871L26.3445 4.74414Z'
            fill='currentColor'
            stroke='currentColor'
            strokeWidth='2'
          />
          <path
            d='M16 3.70312C16.1784 3.70312 16.3558 3.70749 16.5322 3.71484L17.0586 3.74707C17.1746 3.75677 17.2657 3.82138 17.3213 3.95996C17.3818 4.11086 17.3772 4.31265 17.2832 4.4834C17.1747 4.68036 16.9667 4.79221 16.7686 4.7793C16.5128 4.76236 16.2563 4.75294 16 4.75293C9.84302 4.75293 4.81741 9.6034 4.53711 15.6904L4.5332 15.7549L4.5293 15.7959L4.52539 15.8311V27.7031H14.7822L14.834 27.6943L15.0098 27.6631L15.2109 27.6768C15.4715 27.6944 15.7346 27.7031 16 27.7031C22.3375 27.7031 27.4745 22.566 27.4746 16.2285C27.4746 16.0954 27.5582 15.9612 27.6973 15.9004C27.7337 15.8846 27.7698 15.8698 27.8037 15.8545V15.8535C27.9815 15.7729 28.1848 15.7842 28.332 15.8564C28.4673 15.9228 28.5235 16.0181 28.5244 16.1328C28.5247 16.1646 28.5254 16.1966 28.5254 16.2285C28.5253 23.1458 22.9173 28.7529 16 28.7529C15.7108 28.7529 15.4238 28.7438 15.1396 28.7246L15.0674 28.7197L14.9951 28.7324C14.9163 28.7463 14.8343 28.7529 14.75 28.7529H4.875C4.10179 28.7529 3.47468 28.1267 3.47461 27.3535V15.8535C3.47461 15.7964 3.47888 15.7407 3.48535 15.6865L3.4873 15.6641L3.48828 15.6426C3.79411 8.99765 9.27913 3.70312 16 3.70312Z'
            fill='currentColor'
            stroke='currentColor'
            strokeWidth='2'
          />
          <path
            d='M16 11.3262C16.1392 11.3262 16.2726 11.382 16.3711 11.4805C16.4695 11.5789 16.5254 11.7123 16.5254 11.8516V21.9766C16.5254 22.1158 16.4695 22.2492 16.3711 22.3477C16.2726 22.4461 16.1392 22.502 16 22.502C15.8608 22.502 15.7274 22.4461 15.6289 22.3477C15.5304 22.2492 15.4746 22.1158 15.4746 21.9766V11.8516C15.4746 11.7123 15.5304 11.5789 15.6289 11.4805C15.7274 11.382 15.8608 11.3262 16 11.3262ZM11 13.7012C11.1392 13.7012 11.2726 13.757 11.3711 13.8555C11.4696 13.9539 11.5254 14.0873 11.5254 14.2266V19.4766C11.5254 19.6158 11.4696 19.7492 11.3711 19.8477C11.2726 19.9461 11.1392 20.002 11 20.002C10.8608 20.002 10.7274 19.9461 10.6289 19.8477C10.5304 19.7492 10.4746 19.6158 10.4746 19.4766V14.2266L10.4854 14.124C10.5055 14.023 10.555 13.9294 10.6289 13.8555C10.7274 13.757 10.8608 13.7012 11 13.7012ZM21 13.7012C21.1392 13.7012 21.2726 13.757 21.3711 13.8555C21.4695 13.9539 21.5254 14.0873 21.5254 14.2266V19.4766C21.5254 19.6158 21.4695 19.7492 21.3711 19.8477C21.2726 19.9461 21.1392 20.002 21 20.002C20.8608 20.002 20.7274 19.9461 20.6289 19.8477C20.5305 19.7492 20.4746 19.6158 20.4746 19.4766V14.2266C20.4746 14.0873 20.5305 13.9539 20.6289 13.8555C20.7274 13.757 20.8608 13.7012 21 13.7012Z'
            fill='currentColor'
            stroke='currentColor'
            strokeWidth='2'
          />
        </svg>
      </button>
    );
  },
);

ListenSlideAskPlayerAction.displayName = 'ListenSlideAskPlayerAction';

interface ListenPlaybackSpeedPlayerActionProps {
  ariaLabel: string;
  label: string;
  playbackSpeed: ListenPlaybackSpeed;
  portalContainer?: HTMLElement | null;
  onPlaybackSpeedChange: (playbackSpeed: ListenPlaybackSpeed) => void;
}

const ListenPlaybackSpeedPlayerAction = memo(
  ({
    ariaLabel,
    label,
    playbackSpeed,
    portalContainer,
    onPlaybackSpeedChange,
  }: ListenPlaybackSpeedPlayerActionProps) => {
    const [isOpen, setIsOpen] = useState(false);
    const currentPlaybackSpeedLabel = formatListenPlaybackSpeed(playbackSpeed);

    const handlePlaybackSpeedChange = useCallback(
      (nextPlaybackSpeed: ListenPlaybackSpeed) => {
        onPlaybackSpeedChange(nextPlaybackSpeed);
        setIsOpen(false);
      },
      [onPlaybackSpeedChange],
    );

    return (
      <Popover
        open={isOpen}
        onOpenChange={setIsOpen}
      >
        <PopoverTrigger asChild>
          <button
            aria-label={ariaLabel}
            className='slide-player__action listen-playback-speed-action'
            title={ariaLabel}
            type='button'
          >
            <span className='listen-playback-speed-action__label'>
              {currentPlaybackSpeedLabel}
            </span>
          </button>
        </PopoverTrigger>
        <PopoverContent
          align='center'
          className='listen-playback-speed-popover'
          container={portalContainer}
          side='top'
          sideOffset={8}
        >
          <div
            aria-label={label}
            className='listen-playback-speed-menu'
            role='radiogroup'
          >
            <div className='listen-playback-speed-menu__title'>{label}</div>
            {LISTEN_PLAYBACK_SPEED_OPTIONS.map(option => {
              const isSelected = option === playbackSpeed;
              const optionLabel = formatListenPlaybackSpeed(option);
              return (
                <button
                  aria-checked={isSelected}
                  aria-label={optionLabel}
                  className={cn(
                    'listen-playback-speed-option',
                    isSelected && 'listen-playback-speed-option--active',
                  )}
                  key={option}
                  onClick={() => handlePlaybackSpeedChange(option)}
                  role='radio'
                  title={optionLabel}
                  type='button'
                >
                  <span className='listen-playback-speed-option__label'>
                    {optionLabel}
                  </span>
                </button>
              );
            })}
          </div>
        </PopoverContent>
      </Popover>
    );
  },
);

ListenPlaybackSpeedPlayerAction.displayName = 'ListenPlaybackSpeedPlayerAction';

const hasListenStepAudio = (element?: SlideElement) => {
  const listenElement = element as ListenSlideElement | undefined;

  return Boolean(
    listenElement?.audio_url ||
    listenElement?.audio_segments?.length ||
    listenElement?.is_audio_streaming ||
    listenElement?.isAudioStreaming,
  );
};

const hasBlockingListenInteraction = (element?: SlideElement) => {
  if (element?.type !== 'interaction') {
    return false;
  }

  const interactionElement = element as ListenSlideElement | undefined;
  const hasUserInput = Boolean(interactionElement?.user_input?.trim());
  const interactionContent =
    typeof interactionElement?.content === 'string'
      ? interactionElement.content
      : '';

  return (
    !Boolean(interactionElement?.readonly) &&
    !hasUserInput &&
    !isLessonFeedbackInteractionContent(interactionContent) &&
    !isSystemInteractionContent(interactionContent)
  );
};

const getListenPlaybackSequenceActive = ({
  currentStepIndex,
  totalStepCount,
  currentStepHasAudio,
  currentStepHasBlockingInteraction,
  hasCompletedCurrentStepAudio,
  isAudioPlaying,
  isAudioWaiting,
}: ListenPlaybackState) => {
  if (totalStepCount > 0 && currentStepIndex < 0) {
    return true;
  }

  const hasFutureSteps =
    currentStepIndex >= 0 && currentStepIndex < totalStepCount - 1;
  const hasPendingCurrentStepAudio =
    currentStepHasAudio && !hasCompletedCurrentStepAudio;

  return (
    hasFutureSteps ||
    hasPendingCurrentStepAudio ||
    currentStepHasBlockingInteraction ||
    isAudioPlaying ||
    isAudioWaiting
  );
};

const createEmptyStateElement = (
  sectionTitle: string | undefined,
): ListenSlideElement => ({
  sequence_number: 1,
  type: 'slot',
  content: (
    <div className='flex h-full w-full items-center justify-center text-center text-[40px] font-bold leading-[1.3] text-primary'>
      {sectionTitle}
    </div>
  ),
  is_marker: true,
  is_renderable: true,
  is_new: true,
  blockBid: 'empty-ppt',
  page: 0,
});

const buildSlideElementList = ({
  items,
  askListByAnchorElementBid,
  sectionTitle,
  interactionInputMap,
  lastInteractionBid,
  lastItemIsInteraction,
  includeAudio,
  showLeadingTextPlaceholder,
  resolveRenderSequence,
}: {
  items: ChatContentItem[];
  askListByAnchorElementBid: Map<string, AskMessage[]>;
  sectionTitle?: string;
  interactionInputMap: Record<string, string>;
  lastInteractionBid: string | null;
  lastItemIsInteraction: boolean;
  includeAudio: boolean;
  showLeadingTextPlaceholder: boolean;
  resolveRenderSequence: ResolveRenderSequence;
}) => {
  let pageCursor = 0;
  let sequenceNumber = 0;
  let hasResolvedFirstContentType = false;
  let hasLeadingTextContentElement = false;
  const elementList: ListenSlideElement[] = [];

  items.forEach(item => {
    if (item.type === ChatContentItemType.CONTENT) {
      const { audioSegments, audioUrl, isAudioStreaming } = includeAudio
        ? resolveListenSlideAudioSource(item)
        : {};
      const contentType = resolveListenSlideElementType(item);
      const subtitleCues = includeAudio
        ? resolveListenSlideSubtitleCues(item)
        : undefined;
      const askList = askListByAnchorElementBid.get(item.element_bid);

      if (!hasResolvedFirstContentType) {
        hasResolvedFirstContentType = true;
        hasLeadingTextContentElement = contentType === 'text';
      }

      sequenceNumber += 1;
      elementList.push({
        sequence_number: resolveRenderSequence({
          item,
          itemType: 'content',
          fallbackSequence: sequenceNumber,
        }),
        type: contentType,
        content: item.content || '',
        is_marker: item.is_marker ?? true,
        is_renderable: item.is_renderable ?? true,
        is_new: item.is_new ?? true,
        is_speakable: includeAudio
          ? (item.is_speakable ?? Boolean(audioUrl || audioSegments?.length))
          : true,
        ...(includeAudio
          ? {
              audio_url: audioUrl,
              is_audio_streaming: isAudioStreaming,
              isAudioStreaming,
              audio_segments: audioSegments,
              subtitle_cues: subtitleCues,
            }
          : {}),
        ask_list: askList,
        blockBid: item.element_bid,
        page: pageCursor,
      });

      pageCursor += 1;
      return;
    }

    if (item.type !== ChatContentItemType.INTERACTION) {
      return;
    }

    if (isLessonFeedbackInteractionContent(item.content)) {
      return;
    }

    // Prefer in-memory interaction state, then fall back to persisted user_input.
    const currentUserInput =
      interactionInputMap[item.element_bid] ?? item.user_input ?? '';
    const isSystemInteraction = isSystemInteractionContent(item.content);
    const isLatestEditable =
      lastItemIsInteraction && item.element_bid === lastInteractionBid;
    const askList = askListByAnchorElementBid.get(item.element_bid);

    sequenceNumber += 1;
    elementList.push({
      sequence_number: resolveRenderSequence({
        item,
        itemType: 'interaction',
        fallbackSequence: sequenceNumber,
      }),
      type: 'interaction',
      content: item.content || '',
      is_marker: item.is_marker ?? true,
      is_renderable: item.is_renderable ?? true,
      is_new: item.is_new ?? true,
      blockBid: item.element_bid,
      page: Math.max(pageCursor - 1, 0),
      user_input: isSystemInteraction ? '' : currentUserInput,
      ask_list: askList,
      readonly:
        !isSystemInteraction &&
        (Boolean(item.readonly) ||
          Boolean(currentUserInput) ||
          !isLatestEditable),
    });
  });

  if (!elementList.length) {
    return [createEmptyStateElement(sectionTitle)];
  }

  // Keep a leading placeholder when the first content payload is text.
  if (showLeadingTextPlaceholder && hasLeadingTextContentElement) {
    const firstSequenceNumber = Number(elementList[0]?.sequence_number ?? 1);
    elementList.unshift({
      ...createEmptyStateElement(sectionTitle),
      sequence_number: Math.max(firstSequenceNumber - 1, 0),
    });
  }

  return elementList;
};

const ListenModeSlideRenderer = ({
  items,
  mobileStyle,
  chatRef,
  variant = 'listen',
  isLoading = false,
  sectionTitle,
  courseName = '',
  courseAvatar = '',
  lessonId = '',
  shifuBid = '',
  previewMode = false,
  onSend,
  onPlayerVisibilityChange,
  onPlaybackStateChange,
  onLessonFeedbackPromptStateChange,
  onMobileViewModeChange,
}: ListenModeSlideRendererProps) => {
  const { t } = useTranslation();
  const presentationProfile = resolveListenSlidePresentationProfile(variant);
  const {
    includeAudio,
    showLeadingTextPlaceholder,
    trackBrowserFullscreen,
    enablePageShortcutBridge,
    showPlayerCustomActions,
    pausePlayerCustomActionOnActive,
    showMobileAskEntry,
    showAskOverlays,
    showManualFullscreenButton,
    disableLoadingOverlay,
    playerClassName,
  } = presentationProfile;
  const renderSequenceByStreamKeyRef = useRef<Map<string, number>>(new Map());
  const audioListenerCleanupMapRef = useRef<Map<HTMLAudioElement, () => void>>(
    new Map(),
  );
  const audioWaitingStateMapRef = useRef<Map<HTMLAudioElement, boolean>>(
    new Map(),
  );
  const [playbackSpeed, setPlaybackSpeed] = useState<ListenPlaybackSpeed>(() =>
    readListenPlaybackSpeedFromStorage(shifuBid),
  );
  const playbackSpeedRef = useRef<ListenPlaybackSpeed>(playbackSpeed);
  const [interactionInputMap, setInteractionInputMap] = useState<
    Record<string, string>
  >({});
  const [playbackState, setPlaybackState] = useState<ListenPlaybackState>({
    currentStepIndex: -1,
    totalStepCount: 0,
    currentStepHasAudio: false,
    currentStepHasBlockingInteraction: false,
    hasCompletedCurrentStepAudio: false,
    isAudioPlaying: false,
    isAudioWaiting: false,
  });
  const [hasSettledTailInteraction, setHasSettledTailInteraction] =
    useState(false);
  const [isMobileAskOpen, setIsMobileAskOpen] = useState(false);
  const [isMobileAskPanelMounted, setIsMobileAskPanelMounted] = useState(false);
  const [mobileAskPanelElementBid, setMobileAskPanelElementBid] = useState('');
  const [isPlayerVisible, setIsPlayerVisible] = useState(true);
  const [isClassroomFullscreenActive, setIsClassroomFullscreenActive] =
    useState(false);
  const [mobileViewMode, setMobileViewMode] = useState<MobileViewMode>(
    DEFAULT_LISTEN_MOBILE_VIEW_MODE,
  );
  const [fullscreenPortalContainer, setFullscreenPortalContainer] =
    useState<HTMLElement | null>(null);
  const [currentStepBlockBid, setCurrentStepBlockBid] = useState('');
  const [playerCustomActionState, setPlayerCustomActionState] =
    useState<PlayerCustomActionState>({
      currentElement: undefined,
      isActive: false,
    });
  const [isDesktopAskPanelMounted, setIsDesktopAskPanelMounted] =
    useState(false);
  const [desktopAskPanelElementBid, setDesktopAskPanelElementBid] =
    useState('');
  const mobileAskActionRef = useRef<HTMLButtonElement | null>(null);
  const desktopAskActionRef = useRef<HTMLButtonElement | null>(null);
  const playerCustomActionSetActiveRef = useRef<(active: boolean) => void>(
    () => {},
  );
  const customAskOverlayRef = useRef<HTMLDivElement | null>(null);
  const slideShellRef = useRef<HTMLDivElement | null>(null);
  const ensureLessonScope = useAskStateStore(state => state.ensureLessonScope);
  const hydrateAskListMap = useAskStateStore(state => state.hydrateAskListMap);
  const lessonScopeKey = useAskStateStore(state => state.lessonScopeKey);
  const storedAskListByAnchorElementBid = useAskStateStore(
    state => state.askListByAnchorElementBid,
  );

  useEffect(() => {
    const storedPlaybackSpeed = readListenPlaybackSpeedFromStorage(shifuBid);
    playbackSpeedRef.current = storedPlaybackSpeed;
    setPlaybackSpeed(storedPlaybackSpeed);
  }, [shifuBid]);

  useEffect(() => {
    playbackSpeedRef.current = playbackSpeed;
  }, [playbackSpeed]);

  const handleListenPlaybackSpeedChange = useCallback(
    (nextPlaybackSpeed: ListenPlaybackSpeed) => {
      playbackSpeedRef.current = nextPlaybackSpeed;
      setPlaybackSpeed(nextPlaybackSpeed);
      writeListenPlaybackSpeedToStorage(shifuBid, nextPlaybackSpeed);
    },
    [shifuBid],
  );

  const {
    lastInteractionBid,
    lastItemIsInteraction,
    lastItemIsLessonFeedbackInteraction,
    firstContentItem,
  } = useListenContentData(items);
  const baseAskListByAnchorElementBid = useMemo(
    () => buildAskListByAnchorElementBid(items),
    [items],
  );
  const askListByAnchorElementBid = useMemo(() => {
    const nextMap = new Map(baseAskListByAnchorElementBid);
    const scopedStoredAskListByAnchorElementBid =
      lessonScopeKey === lessonId ? storedAskListByAnchorElementBid : {};

    Object.entries(scopedStoredAskListByAnchorElementBid).forEach(
      ([anchorElementBid, askList]) => {
        if (!anchorElementBid) {
          return;
        }

        nextMap.set(anchorElementBid, askList);
      },
    );

    return nextMap;
  }, [
    baseAskListByAnchorElementBid,
    lessonId,
    lessonScopeKey,
    storedAskListByAnchorElementBid,
  ]);

  useEffect(() => {
    ensureLessonScope(lessonId);
  }, [ensureLessonScope, lessonId]);

  useEffect(() => {
    hydrateAskListMap(baseAskListByAnchorElementBid);
  }, [baseAskListByAnchorElementBid, hydrateAskListMap]);

  const elementList = useMemo(() => {
    const sequenceMap = renderSequenceByStreamKeyRef.current;
    const activeStreamKeys = new Set<string>();
    const activeSequenceNumbers = new Set<number>();

    const hasOccupiedSequenceNumber = (
      nextSequenceNumber: number,
      currentStreamKey: string,
    ) => {
      if (activeSequenceNumbers.has(nextSequenceNumber)) {
        return true;
      }

      for (const [streamKey, sequenceNumber] of sequenceMap.entries()) {
        if (streamKey === currentStreamKey) {
          continue;
        }
        if (sequenceNumber === nextSequenceNumber) {
          return true;
        }
      }

      return false;
    };

    const resolveRenderSequence: ResolveRenderSequence = ({
      item,
      itemType,
      fallbackSequence,
    }) => {
      const streamBid = item.element_bid || '';
      const streamKey = streamBid
        ? `${itemType}:${streamBid}`
        : `${itemType}:fallback-${fallbackSequence}`;
      activeStreamKeys.add(streamKey);

      const existingSequence = sequenceMap.get(streamKey);
      if (typeof existingSequence === 'number') {
        activeSequenceNumbers.add(existingSequence);
        return existingSequence;
      }

      const incomingSequence = Number(item.sequence_number);
      const hasIncomingSequence =
        Number.isFinite(incomingSequence) && incomingSequence > 0;
      let nextSequence = hasIncomingSequence
        ? incomingSequence
        : fallbackSequence;

      while (hasOccupiedSequenceNumber(nextSequence, streamKey)) {
        nextSequence += 1;
      }

      sequenceMap.set(streamKey, nextSequence);
      activeSequenceNumbers.add(nextSequence);

      return nextSequence;
    };

    const nextElementList = buildSlideElementList({
      items,
      askListByAnchorElementBid,
      sectionTitle,
      interactionInputMap,
      lastInteractionBid,
      lastItemIsInteraction,
      includeAudio,
      showLeadingTextPlaceholder,
      resolveRenderSequence,
    });

    for (const streamKey of Array.from(sequenceMap.keys())) {
      if (activeStreamKeys.has(streamKey)) {
        continue;
      }
      sequenceMap.delete(streamKey);
    }

    return nextElementList;
  }, [
    askListByAnchorElementBid,
    includeAudio,
    interactionInputMap,
    items,
    lastInteractionBid,
    lastItemIsInteraction,
    sectionTitle,
    showLeadingTextPlaceholder,
  ]);
  const markerStepCount = useMemo(
    () => elementList.filter(element => Boolean(element.is_marker)).length,
    [elementList],
  );
  const markerStepList = useMemo(
    () => elementList.filter(element => Boolean(element.is_marker)),
    [elementList],
  );
  const markerSequenceKey = useMemo(
    () => buildListenMarkerSequenceKey(markerStepList),
    [markerStepList],
  );
  const currentMarkerStepElement = useMemo(() => {
    if (playbackState.currentStepIndex < 0) {
      return undefined;
    }

    return markerStepList[playbackState.currentStepIndex];
  }, [markerStepList, playbackState.currentStepIndex]);
  const currentMarkerStepKey = useMemo(() => {
    const markerIdentityKey = getListenMarkerIdentityKey(
      currentMarkerStepElement,
    );

    if (!markerIdentityKey) {
      return '';
    }

    return [
      markerIdentityKey,
      typeof currentMarkerStepElement?.content === 'string'
        ? currentMarkerStepElement.content
        : '',
    ].join(':');
  }, [currentMarkerStepElement]);
  const previousMarkerStepKeyRef = useRef('');

  const shouldRenderEmptyPpt =
    !isLoading &&
    elementList.length === 1 &&
    elementList[0]?.blockBid === 'empty-ppt';

  const fallbackAskElementBid = firstContentItem?.element_bid ?? '';
  const currentPlayerElementBid = useMemo(() => {
    const blockBid = playerCustomActionState.currentElement?.blockBid;

    if (blockBid && blockBid !== 'empty-ppt') {
      return blockBid;
    }

    return '';
  }, [playerCustomActionState.currentElement]);
  const resolvedAskElementBid =
    currentPlayerElementBid || currentStepBlockBid || fallbackAskElementBid;
  const resolvePlayerAskElementBid = useCallback(
    (element?: ListenSlideElement) => {
      const blockBid = element?.blockBid;
      if (blockBid && blockBid !== 'empty-ppt') {
        return blockBid;
      }

      return fallbackAskElementBid;
    },
    [fallbackAskElementBid],
  );
  const playerCustomAskElementBid = useMemo(() => {
    return resolvePlayerAskElementBid(playerCustomActionState.currentElement);
  }, [playerCustomActionState.currentElement, resolvePlayerAskElementBid]);
  const renderedPlayerCustomAskElementBid =
    playerCustomActionState.isActive || !desktopAskPanelElementBid
      ? playerCustomAskElementBid
      : desktopAskPanelElementBid;
  const renderedMobileAskElementBid =
    isMobileAskOpen || !mobileAskPanelElementBid
      ? resolvedAskElementBid
      : mobileAskPanelElementBid;
  const resolveAskListByElementBid = useCallback(
    (elementBid: string) => {
      if (!elementBid) {
        return [];
      }

      return (elementList.find(element => element.blockBid === elementBid)
        ?.ask_list ?? []) as AskMessage[];
    },
    [elementList],
  );
  const playerCustomAskList = useMemo<AskMessage[]>(() => {
    return resolveAskListByElementBid(renderedPlayerCustomAskElementBid);
  }, [renderedPlayerCustomAskElementBid, resolveAskListByElementBid]);
  const currentAskList = useMemo<AskMessage[]>(() => {
    return resolveAskListByElementBid(renderedMobileAskElementBid);
  }, [renderedMobileAskElementBid, resolveAskListByElementBid]);
  const currentAskTargetElement = useMemo(() => {
    if (playerCustomActionState.currentElement) {
      return playerCustomActionState.currentElement;
    }

    if (!resolvedAskElementBid) {
      return undefined;
    }

    return elementList.find(
      element => element.blockBid === resolvedAskElementBid,
    );
  }, [
    elementList,
    playerCustomActionState.currentElement,
    resolvedAskElementBid,
  ]);
  const isAskActionDisabled = currentAskTargetElement?.type === 'interaction';

  const handleInteractionSend = useCallback(
    (content: OnSendContentParams, element?: SlideElement) => {
      const blockBid = (element as ListenSlideElement | undefined)?.blockBid;
      if (!blockBid) {
        return;
      }

      const submittedValue = resolveInteractionSubmission(content).userInput;
      if (submittedValue) {
        setInteractionInputMap(prev => ({
          ...prev,
          [blockBid]: submittedValue,
        }));
      }

      onSend?.(content, blockBid);
    },
    [onSend],
  );

  const closeInteractionOverlayIfOpen = useCallback(() => {
    const shellElement = slideShellRef.current;
    if (!shellElement) {
      return;
    }

    const notesToggleButton =
      shellElement.querySelector<HTMLButtonElement>(
        'button[aria-label="Notes"].slide-player__action',
      ) ??
      shellElement.querySelector<HTMLButtonElement>(
        '.slide-player__controls .slide-player__group:last-of-type > .slide-player__action:last-of-type',
      );

    if (
      !notesToggleButton ||
      !notesToggleButton.classList.contains('slide-player__action--active')
    ) {
      return;
    }

    // Reuse the player toggle path so the default overlay closes first.
    notesToggleButton.click();
  }, []);

  const handleMobileAskToggle = useCallback(() => {
    if (isAskActionDisabled) {
      return;
    }

    if (isMobileAskOpen) {
      setIsMobileAskOpen(false);
      playerCustomActionSetActiveRef.current(false);
      return;
    }

    closeInteractionOverlayIfOpen();
    setMobileAskPanelElementBid(resolvedAskElementBid);
    setIsMobileAskPanelMounted(true);
    setIsMobileAskOpen(true);
    playerCustomActionSetActiveRef.current(true);
  }, [
    closeInteractionOverlayIfOpen,
    isAskActionDisabled,
    isMobileAskOpen,
    resolvedAskElementBid,
  ]);

  const handleMobileAskClose = useCallback(() => {
    setIsMobileAskOpen(false);
    playerCustomActionSetActiveRef.current(false);
  }, []);

  const handlePlayerCustomActionContextChange = useCallback(
    ({
      currentElement,
      isActive,
      setActive,
    }: PlayerCustomActionContextSnapshot) => {
      playerCustomActionSetActiveRef.current = setActive;
      if (isActive) {
        setDesktopAskPanelElementBid(
          resolvePlayerAskElementBid(currentElement),
        );
        setIsDesktopAskPanelMounted(true);
      }
      setPlayerCustomActionState(prevState => {
        if (
          prevState.currentElement === currentElement &&
          prevState.isActive === isActive
        ) {
          return prevState;
        }

        return {
          currentElement,
          isActive,
        };
      });
    },
    [resolvePlayerAskElementBid],
  );

  const handlePlayerCustomActionClose = useCallback(() => {
    setPlayerCustomActionState(prevState => {
      if (!prevState.isActive) {
        return prevState;
      }

      return {
        ...prevState,
        isActive: false,
      };
    });
    playerCustomActionSetActiveRef.current(false);
  }, []);

  useEffect(() => {
    if (!isAskActionDisabled) {
      return;
    }

    if (mobileStyle) {
      if (!isMobileAskOpen) {
        return;
      }

      handleMobileAskClose();
      return;
    }

    if (!playerCustomActionState.isActive) {
      return;
    }

    handlePlayerCustomActionClose();
  }, [
    handleMobileAskClose,
    handlePlayerCustomActionClose,
    isAskActionDisabled,
    isMobileAskOpen,
    mobileStyle,
    playerCustomActionState.isActive,
  ]);

  const handlePlayerVisibilityChange = useCallback(
    (visible: boolean) => {
      setIsPlayerVisible(visible);
      onPlayerVisibilityChange?.(visible);
    },
    [onPlayerVisibilityChange],
  );

  const requestClassroomFullscreen = useCallback(async () => {
    const slideShellElement = slideShellRef.current;
    if (!slideShellElement) {
      return false;
    }

    const didEnterFullscreen =
      Boolean(getDocumentFullscreenElement()) ||
      (await requestClassroomBrowserFullscreen(slideShellElement));
    setIsClassroomFullscreenActive(didEnterFullscreen);

    return didEnterFullscreen;
  }, []);

  useEffect(() => {
    if (!trackBrowserFullscreen) {
      setIsClassroomFullscreenActive(false);
      return;
    }

    setIsClassroomFullscreenActive(Boolean(getDocumentFullscreenElement()));
  }, [lessonId, trackBrowserFullscreen]);

  useEffect(() => {
    if (!trackBrowserFullscreen) {
      return;
    }

    const handleFullscreenChange = () => {
      setIsClassroomFullscreenActive(Boolean(getDocumentFullscreenElement()));
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);

    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
      document.removeEventListener(
        'webkitfullscreenchange',
        handleFullscreenChange,
      );
    };
  }, [trackBrowserFullscreen]);

  useEffect(() => {
    if (!enablePageShortcutBridge) {
      return;
    }

    const handleClassroomPageShortcut = (event: KeyboardEvent) => {
      const forwardedKey = resolveClassroomPageShortcutKey(event);
      if (!forwardedKey || shouldIgnoreClassroomPageShortcutEvent(event)) {
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();

      const forwardedEvent = new KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        code: forwardedKey,
        composed: true,
        key: forwardedKey,
        repeat: event.repeat,
      });
      document.dispatchEvent(forwardedEvent);
    };

    document.addEventListener('keydown', handleClassroomPageShortcut, true);

    return () => {
      document.removeEventListener(
        'keydown',
        handleClassroomPageShortcut,
        true,
      );
    };
  }, [enablePageShortcutBridge]);

  const syncMediaPlaybackState = useCallback(() => {
    const trackedAudioElements = Array.from(
      audioWaitingStateMapRef.current.keys(),
    );
    const nextIsAudioPlaying = trackedAudioElements.some(
      audioElement =>
        Boolean(audioElement.currentSrc) &&
        !audioElement.paused &&
        !audioElement.ended,
    );
    const nextIsAudioWaiting = trackedAudioElements.some(
      audioElement =>
        Boolean(audioElement.currentSrc) &&
        !audioElement.ended &&
        Boolean(audioWaitingStateMapRef.current.get(audioElement)),
    );

    setPlaybackState(prevState => {
      if (
        prevState.isAudioPlaying === nextIsAudioPlaying &&
        prevState.isAudioWaiting === nextIsAudioWaiting
      ) {
        return prevState;
      }

      return {
        ...prevState,
        isAudioPlaying: nextIsAudioPlaying,
        isAudioWaiting: nextIsAudioWaiting,
      };
    });
  }, []);

  useEffect(() => {
    const container = chatRef.current;
    if (!container) {
      return;
    }

    const audioListenerCleanupMap = audioListenerCleanupMapRef.current;
    const audioWaitingStateMap = audioWaitingStateMapRef.current;

    const registerAudioElement = (audioElement: HTMLAudioElement) => {
      applyListenPlaybackSpeedToAudioElement(
        audioElement,
        playbackSpeedRef.current,
      );

      if (audioListenerCleanupMapRef.current.has(audioElement)) {
        return;
      }

      const setWaitingState = (isWaiting: boolean) => {
        audioWaitingStateMapRef.current.set(audioElement, isWaiting);
      };
      const handlePlaybackStarted = () => {
        setWaitingState(false);
        setPlaybackState(prevState => ({
          ...prevState,
          hasCompletedCurrentStepAudio: false,
        }));
        syncMediaPlaybackState();
      };
      const handlePlaybackWaiting = () => {
        setWaitingState(true);
        setPlaybackState(prevState => ({
          ...prevState,
          hasCompletedCurrentStepAudio: false,
        }));
        syncMediaPlaybackState();
      };
      const handlePlaybackReady = () => {
        setWaitingState(false);
        syncMediaPlaybackState();
      };
      const handlePlaybackPaused = () => {
        setWaitingState(false);
        syncMediaPlaybackState();
      };
      const handlePlaybackEnded = () => {
        setWaitingState(false);
        setPlaybackState(prevState => ({
          ...prevState,
          hasCompletedCurrentStepAudio: true,
        }));
        syncMediaPlaybackState();
      };

      audioWaitingStateMapRef.current.set(audioElement, false);
      audioElement.addEventListener('play', handlePlaybackStarted);
      audioElement.addEventListener('playing', handlePlaybackStarted);
      audioElement.addEventListener('loadstart', handlePlaybackWaiting);
      audioElement.addEventListener('waiting', handlePlaybackWaiting);
      audioElement.addEventListener('seeking', handlePlaybackWaiting);
      audioElement.addEventListener('canplay', handlePlaybackReady);
      audioElement.addEventListener('canplaythrough', handlePlaybackReady);
      audioElement.addEventListener('seeked', handlePlaybackReady);
      audioElement.addEventListener('pause', handlePlaybackPaused);
      audioElement.addEventListener('ended', handlePlaybackEnded);
      audioListenerCleanupMapRef.current.set(audioElement, () => {
        audioElement.removeEventListener('play', handlePlaybackStarted);
        audioElement.removeEventListener('playing', handlePlaybackStarted);
        audioElement.removeEventListener('loadstart', handlePlaybackWaiting);
        audioElement.removeEventListener('waiting', handlePlaybackWaiting);
        audioElement.removeEventListener('seeking', handlePlaybackWaiting);
        audioElement.removeEventListener('canplay', handlePlaybackReady);
        audioElement.removeEventListener('canplaythrough', handlePlaybackReady);
        audioElement.removeEventListener('seeked', handlePlaybackReady);
        audioElement.removeEventListener('pause', handlePlaybackPaused);
        audioElement.removeEventListener('ended', handlePlaybackEnded);
        audioWaitingStateMapRef.current.delete(audioElement);
      });
      syncMediaPlaybackState();
    };

    const syncAudioElements = () => {
      const nextAudioElements = new Set(
        Array.from(container.querySelectorAll('audio')),
      );

      audioListenerCleanupMapRef.current.forEach((cleanup, audioElement) => {
        if (nextAudioElements.has(audioElement)) {
          return;
        }
        cleanup();
        audioListenerCleanupMapRef.current.delete(audioElement);
      });

      nextAudioElements.forEach(registerAudioElement);
      syncMediaPlaybackState();
    };

    syncAudioElements();

    const mutationObserver = new MutationObserver(() => {
      syncAudioElements();
    });
    mutationObserver.observe(container, {
      childList: true,
      subtree: true,
    });

    return () => {
      mutationObserver.disconnect();
      audioListenerCleanupMap.forEach(cleanup => {
        cleanup();
      });
      audioListenerCleanupMap.clear();
      audioWaitingStateMap.clear();
    };
  }, [chatRef, syncMediaPlaybackState]);

  useEffect(() => {
    const container = chatRef.current;
    if (!container) {
      return;
    }

    const syncPlaybackSpeedToAudio = (audioElement: HTMLAudioElement) => {
      applyListenPlaybackSpeedToAudioElement(audioElement, playbackSpeed);
    };

    Array.from(container.querySelectorAll<HTMLAudioElement>('audio')).forEach(
      syncPlaybackSpeedToAudio,
    );
    audioWaitingStateMapRef.current.forEach((_isWaiting, audioElement) => {
      syncPlaybackSpeedToAudio(audioElement);
    });
  }, [chatRef, playbackSpeed]);

  const handleStepChange = useCallback(
    (element: SlideElement | undefined, index: number) => {
      const blockBid = (element as ListenSlideElement | undefined)?.blockBid;
      if (blockBid && blockBid !== 'empty-ppt') {
        setCurrentStepBlockBid(blockBid);
      }

      setPlaybackState(prevState => {
        if (
          prevState.currentStepIndex === index &&
          prevState.totalStepCount === markerStepCount
        ) {
          return prevState;
        }

        return {
          ...prevState,
          currentStepIndex: index,
          totalStepCount: markerStepCount,
        };
      });
    },
    [markerStepCount],
  );

  useEffect(() => {
    if (!mobileStyle) {
      return;
    }
    setIsMobileAskOpen(false);
    setIsMobileAskPanelMounted(false);
  }, [mobileStyle]);

  useEffect(() => {
    if (!mobileStyle) {
      return;
    }

    handlePlayerCustomActionClose();
  }, [handlePlayerCustomActionClose, mobileStyle]);

  useEffect(() => {
    if (!mobileStyle || !isMobileAskOpen) {
      return;
    }

    const handleWindowPointerDown = (event: PointerEvent) => {
      const eventTarget = event.target as Node | null;

      if (!eventTarget) {
        return;
      }

      if (mobileAskActionRef.current?.contains(eventTarget)) {
        return;
      }

      if (customAskOverlayRef.current?.contains(eventTarget)) {
        return;
      }

      handleMobileAskClose();
    };

    window.addEventListener('pointerdown', handleWindowPointerDown);

    return () => {
      window.removeEventListener('pointerdown', handleWindowPointerDown);
    };
  }, [handleMobileAskClose, isMobileAskOpen, mobileStyle]);

  useEffect(() => {
    if (mobileStyle || !playerCustomActionState.isActive) {
      return;
    }

    const handleWindowPointerDown = (event: PointerEvent) => {
      const eventTarget = event.target as Node | null;

      if (!eventTarget) {
        return;
      }

      if (desktopAskActionRef.current?.contains(eventTarget)) {
        return;
      }

      if (customAskOverlayRef.current?.contains(eventTarget)) {
        return;
      }

      handlePlayerCustomActionClose();
    };

    window.addEventListener('pointerdown', handleWindowPointerDown);

    return () => {
      window.removeEventListener('pointerdown', handleWindowPointerDown);
    };
  }, [
    handlePlayerCustomActionClose,
    mobileStyle,
    playerCustomActionState.isActive,
  ]);

  useEffect(() => {
    const currentStepHasAudio = hasListenStepAudio(currentMarkerStepElement);
    const currentStepHasBlockingInteraction = hasBlockingListenInteraction(
      currentMarkerStepElement,
    );
    const isSameMarkerStep =
      previousMarkerStepKeyRef.current === currentMarkerStepKey;

    setPlaybackState(prevState => {
      const nextHasCompletedCurrentStepAudio =
        resolveCurrentStepAudioCompletion({
          previousStepHasAudio: prevState.currentStepHasAudio,
          nextStepHasAudio: currentStepHasAudio,
          previousCompleted: prevState.hasCompletedCurrentStepAudio,
          isSameMarkerStep,
        });

      if (
        prevState.totalStepCount === markerStepCount &&
        prevState.currentStepHasAudio === currentStepHasAudio &&
        prevState.currentStepHasBlockingInteraction ===
          currentStepHasBlockingInteraction &&
        prevState.hasCompletedCurrentStepAudio ===
          nextHasCompletedCurrentStepAudio
      ) {
        return prevState;
      }

      return {
        ...prevState,
        totalStepCount: markerStepCount,
        currentStepHasAudio,
        currentStepHasBlockingInteraction,
        hasCompletedCurrentStepAudio: nextHasCompletedCurrentStepAudio,
      };
    });
    previousMarkerStepKeyRef.current = currentMarkerStepKey;
  }, [currentMarkerStepElement, currentMarkerStepKey, markerStepCount]);

  useEffect(() => {
    onPlaybackStateChange?.({
      isAudioPlaying: playbackState.isAudioPlaying,
      isAudioSequenceActive: getListenPlaybackSequenceActive(playbackState),
    });
  }, [onPlaybackStateChange, playbackState]);

  const shouldDelayTailInteractionFeedbackPrompt = useMemo(
    () =>
      shouldDelayListenFeedbackPromptForTailInteraction({
        lastItemIsLessonFeedbackInteraction,
        markerStepCount,
        currentStepIndex: playbackState.currentStepIndex,
        currentStepHasAudio: playbackState.currentStepHasAudio,
        currentStepHasBlockingInteraction:
          playbackState.currentStepHasBlockingInteraction,
        currentStepElementType: currentMarkerStepElement?.type,
      }),
    [
      currentMarkerStepElement?.type,
      lastItemIsLessonFeedbackInteraction,
      markerStepCount,
      playbackState.currentStepHasAudio,
      playbackState.currentStepHasBlockingInteraction,
      playbackState.currentStepIndex,
    ],
  );

  useLayoutEffect(() => {
    if (!shouldDelayTailInteractionFeedbackPrompt) {
      setHasSettledTailInteraction(true);
      return;
    }

    setHasSettledTailInteraction(false);
    const timer = window.setTimeout(() => {
      setHasSettledTailInteraction(true);
    }, LESSON_FEEDBACK_TAIL_INTERACTION_SETTLE_DELAY_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [currentMarkerStepKey, shouldDelayTailInteractionFeedbackPrompt]);

  const isLessonFeedbackPromptReady = useMemo(() => {
    return isListenLessonFeedbackPromptReady({
      lastItemIsLessonFeedbackInteraction,
      markerStepCount,
      currentStepIndex: playbackState.currentStepIndex,
      isPlaybackSequenceActive: getListenPlaybackSequenceActive(playbackState),
      hasSettledTailInteraction,
    });
  }, [
    hasSettledTailInteraction,
    lastItemIsLessonFeedbackInteraction,
    markerStepCount,
    playbackState,
  ]);

  useEffect(() => {
    onLessonFeedbackPromptStateChange?.(isLessonFeedbackPromptReady);
  }, [isLessonFeedbackPromptReady, onLessonFeedbackPromptStateChange]);

  useEffect(() => {
    previousMarkerStepKeyRef.current = '';
    setPlaybackState({
      currentStepIndex: -1,
      totalStepCount: markerStepCount,
      currentStepHasAudio: false,
      currentStepHasBlockingInteraction: false,
      hasCompletedCurrentStepAudio: false,
      isAudioPlaying: false,
      isAudioWaiting: false,
    });
    setHasSettledTailInteraction(false);
  }, [lessonId, markerSequenceKey, markerStepCount]);

  useEffect(() => {
    setPlaybackState(prevState =>
      reconcileListenPlaybackStepCount(prevState, markerStepCount),
    );
  }, [markerStepCount]);

  useEffect(
    () => () => {
      onPlaybackStateChange?.({
        isAudioPlaying: false,
        isAudioSequenceActive: false,
      });
      onLessonFeedbackPromptStateChange?.(false);
    },
    [onLessonFeedbackPromptStateChange, onPlaybackStateChange],
  );

  const playerCustomActions = useCallback(
    (context: SlidePlayerCustomActionContext) => {
      const playbackSpeedLabel = formatListenPlaybackSpeed(playbackSpeed);
      const playbackSpeedAction = (
        <ListenPlaybackSpeedPlayerAction
          ariaLabel={t('module.chat.listenPlaybackSpeedAriaLabel', {
            speed: playbackSpeedLabel,
          })}
          label={t('module.chat.listenPlaybackSpeedLabel')}
          onPlaybackSpeedChange={handleListenPlaybackSpeedChange}
          playbackSpeed={playbackSpeed}
          portalContainer={fullscreenPortalContainer}
        />
      );

      if (mobileStyle) {
        return (
          <>
            {playbackSpeedAction}
            <ListenSlideAskPlayerAction
              context={context}
              label={t('module.chat.ask')}
              onBeforeOpen={closeInteractionOverlayIfOpen}
              onContextChange={handlePlayerCustomActionContextChange}
              disabled={isAskActionDisabled}
              renderButton={false}
            />
          </>
        );
      }

      return (
        <>
          {playbackSpeedAction}
          <ListenSlideAskPlayerAction
            actionRef={desktopAskActionRef}
            context={context}
            label={t('module.chat.ask')}
            onBeforeOpen={closeInteractionOverlayIfOpen}
            onContextChange={handlePlayerCustomActionContextChange}
            disabled={isAskActionDisabled}
          />
        </>
      );
    },
    [
      closeInteractionOverlayIfOpen,
      fullscreenPortalContainer,
      handleListenPlaybackSpeedChange,
      handlePlayerCustomActionContextChange,
      isAskActionDisabled,
      mobileStyle,
      playbackSpeed,
      t,
    ],
  );

  const shouldRenderMobileAskEntry =
    showMobileAskEntry && mobileStyle && !shouldRenderEmptyPpt;
  const isMobileFullscreen = mobileViewMode === 'fullscreen';
  const playerTexts = useMemo(
    () => ({
      settingsTitle: t('module.chat.listenPlayerSettingsTitle'),
      subtitleLabel: t('module.chat.listenPlayerSubtitleLabel'),
      subtitleToggleAriaLabel: t('module.chat.listenPlayerSubtitleToggle'),
      screenLabel: t('module.chat.listenPlayerScreenLabel'),
      nonFullscreenLabel: t('module.chat.listenPlayerPortraitLabel'),
      fullscreenLabel: t('module.chat.listenPlayerLandscapeLabel'),
      fullscreenHintText: t('module.chat.listenPlayerFullscreenHint'),
    }),
    [t],
  );
  const fullscreenHeaderContent = useMemo(() => {
    if (!courseName && !sectionTitle) {
      return null;
    }

    return (
      <div className='flex min-w-0 items-center gap-3 text-[var(--slide-mobile-fullscreen-chrome-foreground,var(--foreground))]'>
        {courseAvatar ? (
          <Avatar className='h-8 w-8 shrink-0'>
            <AvatarImage
              src={courseAvatar}
              alt=''
            />
          </Avatar>
        ) : null}
        <div className='flex min-w-0 flex-col justify-center'>
          {courseName ? (
            <span className='truncate text-base font-bold leading-5 text-current'>
              {courseName}
            </span>
          ) : null}
          {sectionTitle ? (
            <span className='truncate text-xs leading-4 text-current opacity-80'>
              {sectionTitle}
            </span>
          ) : null}
        </div>
      </div>
    );
  }, [courseAvatar, courseName, sectionTitle]);
  const fullscreenHeader = useMemo(
    () => ({
      content: fullscreenHeaderContent,
      backAriaLabel: t('module.chat.listenPlayerBack'),
    }),
    [fullscreenHeaderContent, t],
  );
  const handleMobileViewModeChange = useCallback((viewMode: MobileViewMode) => {
    setMobileViewMode(viewMode);
  }, []);

  useEffect(() => {
    onMobileViewModeChange?.(mobileViewMode);
  }, [mobileViewMode, onMobileViewModeChange]);

  const syncFullscreenPortalContainer = useCallback(() => {
    const slideShellElement = slideShellRef.current;
    if (!slideShellElement) {
      setFullscreenPortalContainer(null);
      return;
    }

    const nextContainer =
      slideShellElement.querySelector<HTMLElement>(
        '.listen-slide-root .slide__viewport',
      ) ?? null;

    if (!nextContainer) {
      setFullscreenPortalContainer(null);
      return;
    }

    if (isMobileFullscreen) {
      setFullscreenPortalContainer(nextContainer);
      return;
    }

    const fullscreenElement = getDocumentFullscreenElement();
    const isCurrentSlideInBrowserFullscreen = Boolean(
      fullscreenElement && slideShellElement.contains(fullscreenElement),
    );

    setFullscreenPortalContainer(
      isCurrentSlideInBrowserFullscreen ? nextContainer : null,
    );
  }, [isMobileFullscreen]);

  useEffect(() => {
    const syncContainer = () => {
      window.requestAnimationFrame(() => {
        syncFullscreenPortalContainer();
      });
    };

    syncContainer();

    document.addEventListener('fullscreenchange', syncContainer);
    document.addEventListener('webkitfullscreenchange', syncContainer);

    return () => {
      document.removeEventListener('fullscreenchange', syncContainer);
      document.removeEventListener('webkitfullscreenchange', syncContainer);
    };
  }, [syncFullscreenPortalContainer]);

  const mobileAskEntryButton = shouldRenderMobileAskEntry ? (
    <button
      type='button'
      className={cn(
        'listen-slide-mobile-ask-entry listen-slide-mobile-ask-button',
        isMobileFullscreen && 'listen-slide-mobile-ask-entry--landscape',
        isAskActionDisabled && 'listen-slide-mobile-ask-button--disabled',
      )}
      aria-pressed={isMobileAskOpen}
      aria-disabled={isAskActionDisabled}
      disabled={isAskActionDisabled}
      onClick={handleMobileAskToggle}
      ref={mobileAskActionRef}
    >
      <Image
        src={AskIcon.src}
        alt='ask'
        width={14}
        height={14}
      />
      <span>{t('module.chat.ask')}</span>
    </button>
  ) : null;

  // console.log('elementlist', elementList);

  const shouldRenderDesktopAskOverlay =
    showAskOverlays &&
    isDesktopAskPanelMounted &&
    !mobileStyle &&
    !shouldRenderEmptyPpt;
  const shouldRenderMobileAskPanel =
    showAskOverlays && isMobileAskPanelMounted && !shouldRenderEmptyPpt;
  const shouldRenderManualFullscreenButton =
    showManualFullscreenButton && !isClassroomFullscreenActive;

  const desktopAskOverlay = shouldRenderDesktopAskOverlay ? (
    <div
      className={cn(
        'slide-ask-overlay',
        isPlayerVisible
          ? 'slide-ask-overlay--with-player'
          : 'slide-ask-overlay--standalone',
      )}
      aria-hidden={!playerCustomActionState.isActive}
      ref={customAskOverlayRef}
      style={playerCustomActionState.isActive ? undefined : { display: 'none' }}
    >
      <div className='slide-player__ask-card'>
        <div className='slide-player__ask-body'>
          <AskBlock
            askList={playerCustomAskList}
            className='listen-slide-ask-block'
            element_bid={renderedPlayerCustomAskElementBid}
            isExpanded={playerCustomActionState.isActive}
            onToggleAskExpanded={handlePlayerCustomActionClose}
            outline_bid={lessonId}
            preview_mode={previewMode}
            shifu_bid={shifuBid}
          />
        </div>
      </div>
      <div className='slide-player__ask-arrow' />
    </div>
  ) : null;

  return (
    <div
      className={cn(
        'listen-reveal-wrapper',
        previewMode && !mobileStyle && 'listen-reveal-wrapper--preview',
        mobileStyle ? 'mobile bg-white' : 'bg-[var(--color-slide-desktop-bg)]',
      )}
      ref={chatRef}
    >
      <div
        className='listen-slide-shell'
        ref={slideShellRef}
      >
        {isMobileFullscreen && mobileAskEntryButton
          ? fullscreenPortalContainer
            ? createPortal(mobileAskEntryButton, fullscreenPortalContainer)
            : mobileAskEntryButton
          : null}
        {!isMobileFullscreen ? mobileAskEntryButton : null}
        {shouldRenderMobileAskPanel ? (
          mobileStyle ? (
            isMobileFullscreen && fullscreenPortalContainer ? (
              createPortal(
                <div
                  className='listen-slide-mobile-ask-panel listen-slide-mobile-ask-panel--landscape'
                  aria-hidden={!isMobileAskOpen}
                  ref={customAskOverlayRef}
                  style={isMobileAskOpen ? undefined : { display: 'none' }}
                >
                  <AskBlock
                    askList={currentAskList}
                    className='listen-slide-ask-block'
                    element_bid={renderedMobileAskElementBid}
                    forceDesktopSlidePanel={true}
                    isExpanded={isMobileAskOpen}
                    onToggleAskExpanded={handleMobileAskClose}
                    outline_bid={lessonId}
                    preview_mode={previewMode}
                    shifu_bid={shifuBid}
                  />
                </div>,
                fullscreenPortalContainer,
              )
            ) : (
              <div
                className='listen-slide-mobile-ask-panel'
                aria-hidden={!isMobileAskOpen}
                ref={customAskOverlayRef}
                style={isMobileAskOpen ? undefined : { display: 'none' }}
              >
                <AskBlock
                  askList={currentAskList}
                  className='listen-slide-ask-block'
                  element_bid={renderedMobileAskElementBid}
                  isExpanded={isMobileAskOpen}
                  onToggleAskExpanded={handleMobileAskClose}
                  outline_bid={lessonId}
                  preview_mode={previewMode}
                  shifu_bid={shifuBid}
                />
              </div>
            )
          ) : null
        ) : null}
        {desktopAskOverlay
          ? fullscreenPortalContainer
            ? createPortal(desktopAskOverlay, fullscreenPortalContainer)
            : desktopAskOverlay
          : null}
        <ListenSlide
          // playerAlwaysVisible={true}
          className={cn(
            'h-full w-full listen-slide-root',
            isMobileFullscreen && 'listen-slide-root--landscape',
          )}
          elementList={elementList}
          interactionTexts={{
            title: t('module.chat.listenInteractionHint'),
            confirmButtonText: t('module.renderUi.core.confirm'),
            copyButtonText: t('module.renderUi.core.copyCode'),
            copiedButtonText: t('module.renderUi.core.copied'),
          }}
          bufferingText={{
            waitingForAudio: t(
              'module.chat.slideAudioBufferingWaitingForAudio',
            ),
            loadingAudio: t('module.chat.slideAudioBufferingLoadingAudio'),
            waitingForMoreAudio: t(
              'module.chat.slideAudioBufferingWaitingForMoreAudio',
            ),
          }}
          onPlayerVisibilityChange={handlePlayerVisibilityChange}
          onStepChange={handleStepChange}
          interactionDefaultValueOptions={
            lessonFeedbackInteractionDefaultValueOptions
          }
          disableLoadingOverlay={disableLoadingOverlay}
          fullscreenHeader={fullscreenHeader}
          onSend={handleInteractionSend}
          onMobileViewModeChange={handleMobileViewModeChange}
          playerClassName={cn(
            mobileStyle ? 'listen-slide-player-mobile' : '',
            playerClassName,
          )}
          playerCustomActionPauseOnActive={pausePlayerCustomActionOnActive}
          playerCustomActions={
            showPlayerCustomActions ? playerCustomActions : null
          }
          playerTexts={playerTexts}
          showPlayer={!shouldRenderEmptyPpt}
        />
        {shouldRenderManualFullscreenButton ? (
          <button
            type='button'
            className='classroom-fullscreen-button'
            onClick={() => {
              void requestClassroomFullscreen();
            }}
          >
            <Maximize2
              aria-hidden='true'
              size={22}
              strokeWidth={2.2}
            />
            <span>{t('module.chat.classroomEnterFullscreen')}</span>
          </button>
        ) : null}
        {isLoading ? (
          <div
            className={cn(
              'pointer-events-none absolute inset-0 z-[91] flex items-center justify-center backdrop-blur-sm',
              mobileStyle
                ? 'bg-white/75'
                : 'bg-[var(--color-slide-desktop-bg)]/70',
            )}
          >
            <div className='flex flex-col items-center gap-3 text-primary'>
              <LoadingDots
                ariaLabel={t('module.chat.slideAudioBufferingLoadingAudio')}
                count={4}
                durationMs={960}
                dotClassName='bg-primary'
                gap={5}
                restOpacity={0.2}
                size={5}
              />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

ListenModeSlideRenderer.displayName = 'ListenModeSlideRenderer';

export default memo(ListenModeSlideRenderer);
