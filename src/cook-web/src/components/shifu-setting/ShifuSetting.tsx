import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { SSE } from 'sse.js';
import {
  Plus,
  Minus,
  Settings,
  Volume2,
  Loader2,
  Square,
  Mic,
  RotateCw,
  Trash2,
} from 'lucide-react';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { uploadFile } from '@/lib/file';
import { buildTraceHeaders } from '@/lib/request-trace';
import { getResolvedBaseURL } from '@/c-utils/envUtils';
import { normalizeShifuDetail } from '@/lib/shifu-normalize';
import {
  type AudioSegment,
  mergeAudioSegmentByUniqueKey,
  normalizeAudioSegmentPayload,
} from '@/c-utils/audio-utils';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/Sheet';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Textarea } from '@/components/ui/Textarea';
import { Switch } from '@/components/ui/Switch';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/Form';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import {
  createAudioContext,
  decodeAudioBufferFromBase64,
  playAudioBuffer,
  resumeAudioContext,
} from '@/lib/audio-playback';
import { useToast } from '@/hooks/useToast';

import ModelList from '@/components/model-list';
import { useEnvStore } from '@/c-store';
import { TITLE_MAX_LENGTH } from '@/c-constants/uiConstants';
import { useShifu, useUserStore } from '@/store';
import { useTracking } from '@/c-common/hooks/useTracking';
import { useBillingOverview } from '@/hooks/useBillingData';
import {
  AskProviderSchemaValidationError,
  buildAskProviderConfigForSubmit as buildAskProviderConfigBySchema,
} from '@/components/shifu-setting/ask-provider-schema';
import AskSettingsSection from '@/components/shifu-setting/AskSettingsSection';
import MiniMaxVoiceCloneDialog from '@/components/shifu-setting/MiniMaxVoiceCloneDialog';
import {
  buildMiniMaxClonedVoiceListParams,
  buildMiniMaxVoiceOptions,
  executeMiniMaxVoiceAction,
  isMiniMaxProvider,
  isValidMiniMaxCustomVoiceId,
  loadMiniMaxVoiceRefreshData,
  shouldPreserveCustomMiniMaxVoice,
  type MiniMaxCloneCost,
  type MiniMaxClonedVoice,
} from '@/components/shifu-setting/minimax-voice-clone';
import {
  buildOnboardingTargetProps,
  ONBOARDING_TARGET_IDS,
} from '@/lib/onboardingTargets';

interface Shifu {
  description: string;
  bid: string;
  keywords: string[];
  model: string;
  name: string;
  preview_url: string;
  price: number;
  avatar: string;
  url: string;
  temperature: number;
  system_prompt?: string;
  ask_enabled_status?: number;
  ask_model?: string;
  ask_temperature?: number;
  ask_system_prompt?: string;
  ask_provider_config?: {
    provider?: string;
    mode?: string;
    config?: Record<string, any>;
  };
  archived?: boolean;
  created_user_bid?: string;
  canPublish?: boolean;
  can_publish?: boolean;
  // TTS Configuration
  tts_enabled?: boolean;
  tts_provider?: string;
  tts_model?: string;
  tts_voice_id?: string;
  tts_speed?: number;
  tts_pitch?: number;
  tts_emotion?: string;
  // Language Output Configuration
  use_learner_language?: boolean;
}

const MIN_SHIFU_PRICE = 0.5;
const TEMPERATURE_MIN = 0;
const TEMPERATURE_MAX = 2;
const ASK_MODE_ENABLE = 5103;
const ASK_PROVIDER_LLM = 'llm';
const ASK_PROVIDER_MODE_PROVIDER_ONLY = 'provider_only';
const ASK_TEMPERATURE_MIN = 0;
const ASK_TEMPERATURE_MAX = 2;
const TTS_PREVIEW_CURRENT_TARGET = 'tts-current';
type TtsPreviewOptions = {
  voiceId?: string;
  targetKey?: string;
  demoAudioUrl?: string;
};

export default function ShifuSettingDialog({
  shifuId,
  onSave,
  triggerTargetId,
  openSignal,
  shouldStayOpen,
}: {
  shifuId: string;
  onSave: () => void;
  triggerTargetId?: string;
  openSignal?: string;
  shouldStayOpen?: boolean;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const lastAppliedOpenSignalRef = useRef<string | null>(null);
  const openedByOnboardingRef = useRef(false);
  const { t } = useTranslation();
  const { currentShifu, models } = useShifu();
  const { toast } = useToast();
  const defaultLlmModel = useEnvStore(state => state.defaultLlmModel);
  const currencySymbol = useEnvStore(state => state.currencySymbol);
  const billingEnabled = useEnvStore(state => state.billingEnabled === 'true');
  const { data: billingOverview } = useBillingOverview();
  const debugAllowed =
    !billingEnabled || billingOverview?.debug_allowed === true;
  const baseSelectModelHint = t('module.shifuSetting.selectModelHint');
  const resolvedDefaultModel =
    models.find(option => option.value === defaultLlmModel)?.label ||
    defaultLlmModel;
  const isCjk = /[\u4e00-\u9fff]/.test(baseSelectModelHint);
  const defaultLlmModelSuffix = defaultLlmModel
    ? isCjk
      ? `（${resolvedDefaultModel}）`
      : ` (${resolvedDefaultModel})`
    : '';
  const selectModelHint = `${baseSelectModelHint}${defaultLlmModelSuffix}`;
  const [keywords, setKeywords] = useState(['AIGC']);
  const [shifuImage, setShifuImage] = useState<File | null>(null);
  const [imageError, setImageError] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedImageUrl, setUploadedImageUrl] = useState('');
  const { trackEvent } = useTracking();
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  // Ask configuration state
  const [askModel, setAskModel] = useState('');
  const [askTemperature, setAskTemperature] =
    useState<number>(ASK_TEMPERATURE_MIN);
  const [askTemperatureInput, setAskTemperatureInput] = useState<string>(
    String(ASK_TEMPERATURE_MIN),
  );
  const [askProvider, setAskProvider] = useState(ASK_PROVIDER_LLM);
  const [askProviderConfig, setAskProviderConfig] = useState<
    Record<string, any>
  >({});
  const [askProviderObjectInputs, setAskProviderObjectInputs] = useState<
    Record<string, string>
  >({});
  const [askPreviewLoading, setAskPreviewLoading] = useState(false);
  const [askPreviewQuery, setAskPreviewQuery] = useState('');
  const [askPreviewResult, setAskPreviewResult] = useState('');
  const [askPreviewMeta, setAskPreviewMeta] = useState<{
    provider: string;
    requestedProvider: string;
    fallbackUsed: boolean;
  } | null>(null);

  // TTS Configuration state
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [ttsProvider, setTtsProvider] = useState('');
  const [ttsModel, setTtsModel] = useState('');
  const [ttsVoiceId, setTtsVoiceId] = useState('');
  const [ttsSpeed, setTtsSpeed] = useState<number | null>(1.0);
  const [ttsSpeedInput, setTtsSpeedInput] = useState<string>('1.0');
  const [ttsPitch, setTtsPitch] = useState<number | null>(0);
  const [ttsPitchInput, setTtsPitchInput] = useState<string>('0');
  const [ttsEmotion, setTtsEmotion] = useState('');
  const [minimaxClonedVoices, setMinimaxClonedVoices] = useState<
    MiniMaxClonedVoice[]
  >([]);
  const [minimaxCloneCost, setMinimaxCloneCost] =
    useState<MiniMaxCloneCost | null>(null);
  const [minimaxCloneDialogOpen, setMinimaxCloneDialogOpen] = useState(false);
  const [minimaxManualVoiceId, setMinimaxManualVoiceId] = useState('');
  const ttsProviderToastShownRef = useRef(false);

  // Language Output Configuration state
  const [useLearnerLanguage, setUseLearnerLanguage] = useState(false);
  const open = internalOpen;
  const isOnboardingOpen = Boolean(shouldStayOpen);

  const updateOpen = useCallback((nextOpen: boolean) => {
    setInternalOpen(nextOpen);
  }, []);

  useEffect(() => {
    if (!openSignal) {
      lastAppliedOpenSignalRef.current = null;
      return;
    }
    if (lastAppliedOpenSignalRef.current === openSignal) {
      return;
    }
    lastAppliedOpenSignalRef.current = openSignal;
    openedByOnboardingRef.current = true;
    setInternalOpen(true);
  }, [openSignal]);

  useEffect(() => {
    if (shouldStayOpen !== false || !openedByOnboardingRef.current) {
      return;
    }
    openedByOnboardingRef.current = false;
    setInternalOpen(false);
  }, [shouldStayOpen]);

  // TTS Preview state
  const [ttsPreviewLoading, setTtsPreviewLoading] = useState(false);
  const [ttsPreviewPlaying, setTtsPreviewPlaying] = useState(false);
  const [ttsPreviewTarget, setTtsPreviewTarget] = useState<string | null>(null);
  const ttsPreviewSessionRef = useRef(0);
  const ttsPreviewStreamRef = useRef<any>(null);
  const ttsPreviewAudioContextRef = useRef<AudioContext | null>(null);
  const ttsPreviewSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const ttsPreviewHtmlAudioRef = useRef<HTMLAudioElement | null>(null);
  const ttsPreviewSegmentsRef = useRef<AudioSegment[]>([]);
  const ttsPreviewSegmentIndexRef = useRef(0);
  const ttsPreviewIsPlayingRef = useRef(false);
  const ttsPreviewIsStreamingRef = useRef(false);
  const ttsPreviewWaitingRef = useRef(false);

  const closeTtsPreviewStream = useCallback(() => {
    if (ttsPreviewStreamRef.current) {
      ttsPreviewStreamRef.current.close();
      ttsPreviewStreamRef.current = null;
    }
    ttsPreviewIsStreamingRef.current = false;
  }, []);

  const clearTtsPreviewAudio = useCallback(() => {
    ttsPreviewIsPlayingRef.current = false;
    ttsPreviewWaitingRef.current = false;
    ttsPreviewSegmentsRef.current = [];
    ttsPreviewSegmentIndexRef.current = 0;

    if (ttsPreviewHtmlAudioRef.current) {
      const audio = ttsPreviewHtmlAudioRef.current;
      audio.onplaying = null;
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
      ttsPreviewHtmlAudioRef.current = null;
    }

    if (ttsPreviewSourceRef.current) {
      try {
        ttsPreviewSourceRef.current.stop();
        ttsPreviewSourceRef.current.disconnect();
      } catch {
        // Ignore stop errors
      }
      ttsPreviewSourceRef.current = null;
    }

    if (ttsPreviewAudioContextRef.current) {
      const context = ttsPreviewAudioContextRef.current;
      ttsPreviewAudioContextRef.current = null;
      context.close().catch(() => {});
    }
  }, []);

  const cleanupTtsPreview = useCallback(() => {
    ttsPreviewSessionRef.current += 1;
    closeTtsPreviewStream();
    clearTtsPreviewAudio();
    releaseExclusive();
  }, [clearTtsPreviewAudio, closeTtsPreviewStream, releaseExclusive]);

  const stopTtsPreview = useCallback(() => {
    cleanupTtsPreview();
    setTtsPreviewLoading(false);
    setTtsPreviewPlaying(false);
    setTtsPreviewTarget(null);
  }, [cleanupTtsPreview]);

  const playPreviewSegment = useCallback(
    async (index: number, sessionId: number) => {
      if (ttsPreviewSessionRef.current !== sessionId) {
        return;
      }

      ttsPreviewSegmentIndexRef.current = index;
      const segments = ttsPreviewSegmentsRef.current;
      if (index >= segments.length) {
        if (ttsPreviewIsStreamingRef.current) {
          ttsPreviewWaitingRef.current = true;
          return;
        }
        stopTtsPreview();
        return;
      }

      ttsPreviewWaitingRef.current = false;
      setTtsPreviewLoading(true);

      try {
        let audioContext = ttsPreviewAudioContextRef.current;
        if (!audioContext) {
          audioContext = createAudioContext();
          ttsPreviewAudioContextRef.current = audioContext;
        }

        await resumeAudioContext(audioContext);
        if (ttsPreviewSessionRef.current !== sessionId) {
          return;
        }

        const segment = segments[index];
        const audioBuffer = await decodeAudioBufferFromBase64(
          audioContext,
          segment.audioData,
        );
        if (ttsPreviewSessionRef.current !== sessionId) {
          return;
        }

        const sourceNode = playAudioBuffer(audioContext, audioBuffer, () => {
          if (ttsPreviewSessionRef.current !== sessionId) {
            return;
          }
          if (ttsPreviewIsPlayingRef.current) {
            playPreviewSegment(index + 1, sessionId);
          }
        });
        ttsPreviewSourceRef.current = sourceNode;
        setTtsPreviewLoading(false);
        setTtsPreviewPlaying(true);
        ttsPreviewIsPlayingRef.current = true;
      } catch (error) {
        console.error('Failed to play TTS preview segment:', error);
        if (
          ttsPreviewSessionRef.current === sessionId &&
          ttsPreviewIsPlayingRef.current
        ) {
          playPreviewSegment(index + 1, sessionId);
          return;
        }
        stopTtsPreview();
      }
    },
    [stopTtsPreview],
  );

  // TTS Config from backend
  interface AskProviderConfigItem {
    provider: string;
    title: string;
    description?: string;
    default_config?: Record<string, any>;
    json_schema?: {
      properties?: Record<string, any>;
      required?: string[];
    };
  }
  interface AskConfigMetadata {
    feature_enabled?: boolean;
    default?: {
      provider?: string;
      mode?: string;
      config?: Record<string, any>;
    };
    modes?: Array<{ value: string; title: string }>;
    providers?: AskProviderConfigItem[];
  }
  interface TTSProviderConfig {
    name: string;
    label: string;
    speed: { min: number; max: number; step: number; default: number };
    pitch: { min: number; max: number; step: number; default: number };
    supports_emotion: boolean;
    supports_custom_voice_id?: boolean;
    supports_voice_cloning?: boolean;
    models: { value: string; label: string }[];
    voices: { value: string; label: string; resource_id?: string }[];
    emotions: { value: string; label: string }[];
  }
  const [ttsConfig, setTtsConfig] = useState<{
    providers: TTSProviderConfig[];
  } | null>(null);
  const [askConfigMeta, setAskConfigMeta] = useState<AskConfigMetadata | null>(
    null,
  );
  const normalizeTtsProviders = useCallback(
    (providers?: TTSProviderConfig[] | null): TTSProviderConfig[] =>
      (providers ?? []).map(provider => ({
        ...provider,
        name: (provider.name || '').toLowerCase(),
      })),
    [],
  );
  const normalizeAskProviders = useCallback(
    (providers?: AskProviderConfigItem[] | null): AskProviderConfigItem[] =>
      (providers ?? []).map(provider => ({
        ...provider,
        provider: (provider.provider || '').toLowerCase(),
      })),
    [],
  );

  // Fetch TTS config from backend
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const [ttsConfigResponse, askConfigResponse] = await Promise.all([
          api.ttsConfig({}),
          api.askConfig({}),
        ]);
        setTtsConfig({
          providers: normalizeTtsProviders(ttsConfigResponse?.providers),
        });
        setAskConfigMeta({
          ...askConfigResponse,
          providers: normalizeAskProviders(askConfigResponse?.providers),
        });
      } catch (error) {
        console.error('Failed to fetch config:', error);
      }
    };
    fetchConfig();
  }, [normalizeAskProviders, normalizeTtsProviders]);

  const refreshMinimaxVoiceData = useCallback(async () => {
    if (!shifuId) return;
    const result = await loadMiniMaxVoiceRefreshData({
      fetchVoices: () =>
        api.listMinimaxTtsVoices(
          buildMiniMaxClonedVoiceListParams(shifuId),
        ) as Promise<{
          voices?: MiniMaxClonedVoice[];
        }>,
      fetchCloneCost: () =>
        api.getMinimaxTtsCloneCost({
          shifu_bid: shifuId,
        }) as Promise<MiniMaxCloneCost>,
    });
    if (result.voices !== null) {
      setMinimaxClonedVoices(result.voices);
    }
    if (result.cloneCost !== null) {
      setMinimaxCloneCost(result.cloneCost);
    }
    if (result.errors.length > 0) {
      console.error(
        'Failed to refresh MiniMax voice clone data:',
        result.errors,
      );
    }
  }, [shifuId]);

  const resolvedProvider = (() => {
    const provider = (ttsProvider || '').trim();
    if (!provider) {
      return ttsConfig?.providers?.[0]?.name || '';
    }
    if (ttsConfig?.providers?.length) {
      const exists = ttsConfig.providers.some(p => p.name === provider);
      return exists ? provider : ttsConfig.providers[0]?.name || provider;
    }
    return provider;
  })();
  useEffect(() => {
    if (!ttsEnabled) return;
    if (!ttsConfig?.providers?.length) return;
    const provider = (ttsProvider || '').trim();
    if (provider && ttsConfig.providers.some(p => p.name === provider)) {
      return;
    }
    setTtsProvider(ttsConfig.providers[0].name);
  }, [ttsEnabled, ttsProvider, ttsConfig]);

  // Get current provider config
  const currentProviderConfig =
    ttsConfig?.providers.find(p => p.name === resolvedProvider) ||
    ttsConfig?.providers[0];

  // Get provider options for dropdown
  const ttsProviderOptions =
    ttsConfig?.providers.map(p => ({ value: p.name, label: p.label })) || [];

  // Get models for current provider
  const ttsModelOptions = currentProviderConfig?.models || [];

  // Get voices for current provider
  const ttsVoiceOptions = useMemo(
    () => currentProviderConfig?.voices || [],
    [currentProviderConfig?.voices],
  );

  const showMiniMaxVoiceActionError = useCallback(
    (error: unknown) => {
      toast({
        title: t('common.core.actionFailed'),
        description:
          error instanceof Error
            ? error.message
            : t('common.core.unknownError'),
        variant: 'destructive',
      });
    },
    [t, toast],
  );

  const retryMiniMaxVoice = useCallback(
    async (voiceBid: string) => {
      await executeMiniMaxVoiceAction({
        action: () =>
          api.retryMinimaxTtsVoice({
            voice_bid: voiceBid,
          }),
        onSuccess: refreshMinimaxVoiceData,
        onError: showMiniMaxVoiceActionError,
      });
    },
    [refreshMinimaxVoiceData, showMiniMaxVoiceActionError],
  );

  const deleteMiniMaxVoice = useCallback(
    async (voice: MiniMaxClonedVoice) => {
      await executeMiniMaxVoiceAction({
        action: () =>
          api.deleteMinimaxTtsVoice({
            voice_bid: voice.voice_bid,
          }),
        onSuccess: () => {
          if (ttsVoiceId === voice.voice_id) {
            setTtsVoiceId(ttsVoiceOptions[0]?.value || '');
          }
          refreshMinimaxVoiceData();
        },
        onError: showMiniMaxVoiceActionError,
      });
    },
    [
      refreshMinimaxVoiceData,
      showMiniMaxVoiceActionError,
      ttsVoiceId,
      ttsVoiceOptions,
    ],
  );

  const isMiniMaxTtsProvider = isMiniMaxProvider(resolvedProvider);
  const supportsMiniMaxVoiceCloning =
    isMiniMaxTtsProvider &&
    currentProviderConfig?.supports_voice_cloning === true;
  const minimaxStatusLabels = useMemo(
    () => ({
      queued: t('module.shifuSetting.minimaxCloneStatus.queued'),
      processing: t('module.shifuSetting.minimaxCloneStatus.processing'),
      billing_pending: t(
        'module.shifuSetting.minimaxCloneStatus.billing_pending',
      ),
      failed: t('module.shifuSetting.minimaxCloneStatus.failed'),
      ready: t('module.shifuSetting.minimaxCloneStatus.ready'),
    }),
    [t],
  );
  const mergedTtsVoiceOptions = useMemo(() => {
    if (!isMiniMaxTtsProvider) {
      return ttsVoiceOptions.map(option => ({
        ...option,
        source: 'built_in' as const,
        disabled: false,
      }));
    }
    return buildMiniMaxVoiceOptions({
      builtInVoices: ttsVoiceOptions,
      clonedVoices: minimaxClonedVoices,
      currentVoiceId: ttsVoiceId,
      manualLabel: t('module.shifuSetting.minimaxManualVoiceLabel'),
      statusLabels: minimaxStatusLabels,
    });
  }, [
    isMiniMaxTtsProvider,
    minimaxClonedVoices,
    minimaxStatusLabels,
    t,
    ttsVoiceId,
    ttsVoiceOptions,
  ]);
  const builtInTtsVoiceOptions = useMemo(
    () => mergedTtsVoiceOptions.filter(option => option.source === 'built_in'),
    [mergedTtsVoiceOptions],
  );
  const clonedTtsVoiceOptions = useMemo(
    () => mergedTtsVoiceOptions.filter(option => option.source === 'cloned'),
    [mergedTtsVoiceOptions],
  );
  const manualTtsVoiceOptions = useMemo(
    () => mergedTtsVoiceOptions.filter(option => option.source === 'manual'),
    [mergedTtsVoiceOptions],
  );

  // Get emotions for current provider
  const ttsEmotionOptions =
    currentProviderConfig?.supports_emotion &&
    currentProviderConfig?.emotions?.length > 0
      ? [
          { value: '', label: t('module.shifuSetting.ttsEmotionDefault') },
          ...currentProviderConfig.emotions,
        ]
      : [];
  useEffect(() => {
    if (!open || !ttsEnabled || !isMiniMaxTtsProvider) {
      return;
    }
    refreshMinimaxVoiceData();
  }, [isMiniMaxTtsProvider, open, refreshMinimaxVoiceData, ttsEnabled]);

  useEffect(() => {
    if (!open || !isMiniMaxTtsProvider) {
      return;
    }
    const hasPendingVoice = minimaxClonedVoices.some(voice =>
      ['queued', 'processing', 'billing_pending'].includes(
        String(voice.status || ''),
      ),
    );
    if (!hasPendingVoice) {
      return;
    }
    const timer = setInterval(() => {
      refreshMinimaxVoiceData();
    }, 4000);
    return () => clearInterval(timer);
  }, [
    isMiniMaxTtsProvider,
    minimaxClonedVoices,
    open,
    refreshMinimaxVoiceData,
  ]);
  const normalizeSpeed = useCallback(
    (value: number) => {
      const min = currentProviderConfig?.speed.min ?? 0.5;
      const max = currentProviderConfig?.speed.max ?? 2.0;
      const clamped = Math.min(Math.max(value, min), max);
      return Number(clamped.toFixed(1));
    },
    [currentProviderConfig?.speed.max, currentProviderConfig?.speed.min],
  );
  const speedMin = currentProviderConfig?.speed?.min ?? 0.5;
  const speedMax = currentProviderConfig?.speed?.max ?? 2.0;
  const speedStep = currentProviderConfig?.speed?.step ?? 0.1;
  const speedValue = normalizeSpeed(ttsSpeed ?? speedMin);
  const isSpeedAtMin = speedValue <= speedMin;
  const isSpeedAtMax = speedValue >= speedMax;

  const pitchMin = currentProviderConfig?.pitch?.min ?? -12;
  const pitchMax = currentProviderConfig?.pitch?.max ?? 12;
  const pitchStep = currentProviderConfig?.pitch?.step ?? 1;
  const clampPitch = useCallback(
    (value: number) => Math.min(Math.max(value, pitchMin), pitchMax),
    [pitchMax, pitchMin],
  );
  const pitchValue = clampPitch(ttsPitch ?? pitchMin);
  const isPitchAtMin = pitchValue <= pitchMin;
  const isPitchAtMax = pitchValue >= pitchMax;
  useEffect(() => {
    if (ttsSpeed === null || Number.isNaN(ttsSpeed)) {
      setTtsSpeedInput('');
    } else {
      setTtsSpeedInput(ttsSpeed.toFixed(1));
    }
    if (ttsPitch === null || Number.isNaN(ttsPitch)) {
      setTtsPitchInput('');
    } else {
      setTtsPitchInput(String(Math.round(ttsPitch)));
    }
  }, [ttsSpeed, ttsPitch]);

  const askProviderOptions =
    askConfigMeta?.providers?.map(item => ({
      value: item.provider,
      label: item.title || item.provider,
    })) || [];
  const resolvedAskProvider = (() => {
    const provider = (askProvider || '').trim().toLowerCase();
    if (!provider) {
      return askConfigMeta?.providers?.[0]?.provider || ASK_PROVIDER_LLM;
    }
    if (askConfigMeta?.providers?.length) {
      const exists = askConfigMeta.providers.some(p => p.provider === provider);
      return exists
        ? provider
        : askConfigMeta.providers[0]?.provider || provider;
    }
    return provider;
  })();
  const currentAskProviderMeta =
    askConfigMeta?.providers?.find(
      item => item.provider === resolvedAskProvider,
    ) || askConfigMeta?.providers?.[0];
  const askProviderFieldEntries = useMemo(
    () => Object.entries(currentAskProviderMeta?.json_schema?.properties || {}),
    [currentAskProviderMeta],
  );
  const askProviderRequiredFields = useMemo(
    () => new Set(currentAskProviderMeta?.json_schema?.required || []),
    [currentAskProviderMeta],
  );
  const getAskProviderDefaultConfig = useCallback(
    (provider: string) => {
      const config =
        askConfigMeta?.providers?.find(item => item.provider === provider)
          ?.default_config || {};
      return config && typeof config === 'object' && !Array.isArray(config)
        ? { ...config }
        : {};
    },
    [askConfigMeta],
  );
  const handleAskProviderChange = useCallback(
    (value: string) => {
      setAskProvider(value);
      setAskProviderConfig(getAskProviderDefaultConfig(value));
      setAskProviderObjectInputs({});
    },
    [getAskProviderDefaultConfig],
  );

  const applyMinimaxManualVoiceId = useCallback(() => {
    const normalizedVoiceId = minimaxManualVoiceId.trim();
    if (!isValidMiniMaxCustomVoiceId(normalizedVoiceId)) {
      toast({
        title: t('module.shifuSetting.minimaxManualVoiceInvalid'),
        variant: 'destructive',
      });
      return;
    }
    setTtsVoiceId(normalizedVoiceId);
    setMinimaxManualVoiceId('');
  }, [minimaxManualVoiceId, t, toast]);

  useEffect(() => {
    if (!askConfigMeta?.providers?.length) return;
    const provider = (askProvider || '').trim().toLowerCase();
    if (
      provider &&
      askConfigMeta.providers.some(item => item.provider === provider)
    ) {
      return;
    }
    const fallbackProvider = askConfigMeta.providers[0].provider;
    setAskProvider(fallbackProvider);
    setAskProviderConfig(getAskProviderDefaultConfig(fallbackProvider));
    setAskProviderObjectInputs({});
  }, [askConfigMeta, askProvider, getAskProviderDefaultConfig]);

  const normalizeAskTemperature = useCallback((value: number) => {
    const clamped = Math.min(
      Math.max(value, ASK_TEMPERATURE_MIN),
      ASK_TEMPERATURE_MAX,
    );
    return Number(clamped.toFixed(1));
  }, []);

  useEffect(() => {
    if (askTemperature === null || Number.isNaN(askTemperature)) {
      setAskTemperatureInput('');
    } else {
      setAskTemperatureInput(String(askTemperature));
    }
  }, [askTemperature]);

  const buildAskProviderConfigForSubmit = useCallback(() => {
    try {
      return buildAskProviderConfigBySchema({
        schema: currentAskProviderMeta?.json_schema,
        providerConfig: askProviderConfig as Record<string, unknown>,
        objectInputs: askProviderObjectInputs,
      });
    } catch (error) {
      if (error instanceof AskProviderSchemaValidationError) {
        const fieldSchema =
          currentAskProviderMeta?.json_schema?.properties?.[error.field];
        const fieldLabel = String(fieldSchema?.title || error.field);

        if (error.code === 'required') {
          throw new Error(
            t('module.shifuSetting.askProviderConfigRequired', {
              field: fieldLabel,
            }),
          );
        }

        throw new Error(
          t('module.shifuSetting.askProviderConfigInvalidJson', {
            field: fieldLabel,
          }),
        );
      }

      throw error;
    }
  }, [askProviderConfig, askProviderObjectInputs, currentAskProviderMeta, t]);

  const clampTemperature = useCallback((value: number) => {
    return Math.min(Math.max(value, 0), 2);
  }, []);

  // Sanitize and default selections when provider/config changes
  useEffect(() => {
    if (!ttsConfig || !resolvedProvider) return;
    const provider = ttsConfig.providers.find(p => p.name === resolvedProvider);
    if (!provider) return;

    if (provider.models?.length > 0) {
      const modelValues = new Set(provider.models.map(m => m.value));
      const fallbackModel = provider.models[0]?.value || '';
      if (ttsEnabled) {
        const nextModel = modelValues.has(ttsModel) ? ttsModel : fallbackModel;
        if (nextModel && nextModel !== ttsModel) {
          setTtsModel(nextModel);
        }
      } else if (ttsModel && !modelValues.has(ttsModel)) {
        setTtsModel('');
      }
    }

    if (provider.voices?.length > 0 || mergedTtsVoiceOptions.length > 0) {
      const selectableVoiceOptions = mergedTtsVoiceOptions.filter(
        option => !option.disabled,
      );
      const voiceValues = new Set(selectableVoiceOptions.map(v => v.value));
      const fallbackVoice = selectableVoiceOptions[0]?.value || '';
      const currentClonedVoice = isMiniMaxProvider(provider.name)
        ? minimaxClonedVoices.find(
            voice => (voice.voice_id || '').trim() === ttsVoiceId,
          )
        : undefined;
      const preserveCustomVoice =
        !currentClonedVoice &&
        shouldPreserveCustomMiniMaxVoice({
          providerName: provider.name,
          supportsCustomVoiceId: provider.supports_custom_voice_id,
          voiceId: ttsVoiceId,
          builtInVoices: provider.voices || [],
        });
      if (ttsEnabled) {
        const nextVoice =
          voiceValues.has(ttsVoiceId) || preserveCustomVoice
            ? ttsVoiceId
            : fallbackVoice;
        if (nextVoice && nextVoice !== ttsVoiceId) {
          setTtsVoiceId(nextVoice);
        }
      } else if (
        ttsVoiceId &&
        !voiceValues.has(ttsVoiceId) &&
        !preserveCustomVoice
      ) {
        setTtsVoiceId('');
      }
    }

    if (!provider.supports_emotion) {
      if (ttsEmotion) setTtsEmotion('');
      return;
    }
    if (provider.emotions?.length > 0) {
      const emotionValues = new Set(provider.emotions.map(e => e.value));
      const fallbackEmotion = provider.emotions[0]?.value || '';
      if (ttsEnabled) {
        const nextEmotion = emotionValues.has(ttsEmotion)
          ? ttsEmotion
          : fallbackEmotion;
        if (nextEmotion !== ttsEmotion) {
          setTtsEmotion(nextEmotion);
        }
      } else if (ttsEmotion && !emotionValues.has(ttsEmotion)) {
        setTtsEmotion('');
      }
    }
  }, [
    ttsConfig,
    resolvedProvider,
    ttsModel,
    ttsVoiceId,
    ttsEmotion,
    ttsEnabled,
    mergedTtsVoiceOptions,
    minimaxClonedVoices,
  ]);
  // Define the validation schema using Zod
  const shifuSchema = z.object({
    name: z
      .string()
      .min(1, t('module.shifuSetting.shifuNameEmpty'))
      .max(
        TITLE_MAX_LENGTH,
        t('module.shifuSetting.shifuNameMaxLength', {
          maxLength: TITLE_MAX_LENGTH,
        }),
      ),
    description: z
      .string()
      .min(0, t('module.shifuSetting.shifuDescriptionEmpty'))
      .max(500, t('module.shifuSetting.shifuDescriptionMaxLength')),
    model: z.string(),
    systemPrompt: z
      .string()
      .max(20000, t('module.shifuSetting.shifuPromptMaxLength')),
    price: z
      .string()
      .min(0.5, t('module.shifuSetting.shifuPriceEmpty'))
      .regex(/^\d+(\.\d{1,2})?$/, t('module.shifuSetting.shifuPriceFormat')),
    temperature: z
      .string()
      .regex(
        /^\d+(\.\d{1,2})?$/,
        t('module.shifuSetting.shifuTemperatureFormat'),
      ),
    temperature_min: z
      .number()
      .min(TEMPERATURE_MIN, t('module.shifuSetting.shifuTemperatureMin')),
    temperature_max: z
      .number()
      .max(TEMPERATURE_MAX, t('module.shifuSetting.shifuTemperatureMax')),
  });

  const form = useForm({
    resolver: zodResolver(shifuSchema),
    defaultValues: {
      name: '',
      description: '',
      model: '',
      systemPrompt: '',
      price: '',
      temperature: '',
    },
  });
  const isDirty = form.formState.isDirty;

  // Handle keyword addition
  const handleAddKeyword = () => {
    const keyword = (
      document.getElementById('keywordInput') as any
    )?.value.trim();
    if (keyword && !keywords.includes(keyword)) {
      setKeywords([...keywords, keyword]);
      (document.getElementById('keywordInput') as any).value = '';
    }
  };

  // Handle keyword removal
  const handleRemoveKeyword = keyword => {
    setKeywords(keywords.filter(k => k !== keyword));
  };

  // Handle image upload
  const handleImageUpload = async e => {
    const file = e.target.files[0];
    if (file) {
      // Validate file size
      if (file.size > 2 * 1024 * 1024) {
        setImageError(t('module.shifuSetting.fileSizeLimit'));
        setShifuImage(null);
        return;
      }

      // Validate file type
      if (!['image/jpeg', 'image/png'].includes(file.type)) {
        setImageError(t('module.shifuSetting.supportedFormats'));
        setShifuImage(null);
        return;
      }

      setShifuImage(file);
      setImageError('');

      // Upload the file
      try {
        setIsUploading(true);
        setUploadProgress(0);

        // Use the uploadFile function from file.ts
        const response = await uploadFile(
          file,
          '/api/shifu/upfile',
          undefined,
          undefined,
          progress => {
            setUploadProgress(progress);
          },
        );

        if (!response.ok) {
          throw new Error(`Upload failed: ${response.statusText}`);
        }

        const res = await response.json();
        if (res.code !== 0) {
          throw new Error(res.message);
        }
        setUploadedImageUrl(res.data); // Assuming the API returns the image URL in a 'url' field
      } catch (error) {
        console.error('Upload error:', error);
        setImageError(t('module.shifuSetting.uploadFailed'));
      } finally {
        setIsUploading(false);
      }
    }
  };

  // Handle form submission
  const onSubmit = useCallback(
    async (
      data: any,
      needClose = true,
      saveType: 'auto' | 'manual' = 'manual',
    ) => {
      try {
        const providerForSubmit =
          resolvedProvider || ttsConfig?.providers?.[0]?.name || '';
        const askProviderForSubmit =
          resolvedAskProvider ||
          askConfigMeta?.default?.provider ||
          ASK_PROVIDER_LLM;
        const askModeForSubmit = ASK_PROVIDER_MODE_PROVIDER_ONLY;
        const askTemperatureForSubmit = normalizeAskTemperature(
          Number(askTemperatureInput || askTemperature || 0),
        );
        const askConfigForSubmit = buildAskProviderConfigForSubmit();

        if (ttsEnabled && !providerForSubmit) {
          if (!ttsProviderToastShownRef.current && saveType === 'manual') {
            toast({
              title: t('module.shifuSetting.ttsProviderRequiredTitle'),
              description: t('module.shifuSetting.ttsProviderRequiredDesc'),
              variant: 'destructive',
            });
            ttsProviderToastShownRef.current = true;
          }
          return;
        }

        const payload = {
          description: data.description,
          shifu_bid: shifuId,
          keywords: keywords,
          model: data.model,
          name: data.name,
          price: Number(data.price),
          avatar: uploadedImageUrl,
          temperature: Number(data.temperature),
          system_prompt: data.systemPrompt,
          ask_enabled_status: ASK_MODE_ENABLE,
          ask_model: askModel,
          ask_temperature: askTemperatureForSubmit,
          ask_system_prompt: '',
          ask_provider_config: {
            provider: askProviderForSubmit,
            mode: askModeForSubmit,
            config: askConfigForSubmit,
          },
          // TTS Configuration
          tts_enabled: ttsEnabled,
          tts_provider: providerForSubmit,
          tts_model: ttsModel,
          tts_voice_id: ttsVoiceId,
          tts_speed: speedValue,
          tts_pitch: pitchValue,
          tts_emotion: ttsEmotion,
          // Language Output Configuration
          use_learner_language: useLearnerLanguage,
        };
        await api.saveShifuDetail({
          ...payload,
        });
        trackEvent('creator_shifu_setting_save', {
          ...payload,
          save_type: saveType,
        });
        if (onSave) {
          onSave();
        }
        if (needClose) {
          updateOpen(false);
        }
      } catch (error) {
        if (!currentShifu?.readonly && error instanceof Error) {
          toast({
            title: error.message || t('common.core.unknownError'),
            variant: 'destructive',
          });
        }
        if (currentShifu?.readonly) {
          updateOpen(false);
        }
      }
    },
    [
      shifuId,
      keywords,
      uploadedImageUrl,
      onSave,
      currentShifu?.readonly,
      trackEvent,
      ttsEnabled,
      resolvedProvider,
      ttsConfig,
      ttsModel,
      ttsVoiceId,
      speedValue,
      pitchValue,
      ttsEmotion,
      useLearnerLanguage,
      askConfigMeta,
      askModel,
      askTemperature,
      askTemperatureInput,
      buildAskProviderConfigForSubmit,
      normalizeAskTemperature,
      resolvedAskProvider,
      toast,
      t,
      updateOpen,
    ],
  );

  const init = async () => {
    ttsProviderToastShownRef.current = false;
    const result = normalizeShifuDetail(
      (await api.getShifuDetail({
        shifu_bid: shifuId,
      })) as Shifu,
    );

    if (result) {
      form.reset({
        name: result.name,
        description: result.description,
        price: (result.price ?? 0).toFixed(2),
        model: result.model || '',
        temperature: result.temperature + '',
        systemPrompt: result.system_prompt || '',
      });
      const rawAskProviderConfig =
        result.ask_provider_config &&
        typeof result.ask_provider_config === 'object' &&
        !Array.isArray(result.ask_provider_config)
          ? result.ask_provider_config
          : {};
      const rawAskProviderInnerConfig =
        rawAskProviderConfig.config &&
        typeof rawAskProviderConfig.config === 'object' &&
        !Array.isArray(rawAskProviderConfig.config)
          ? rawAskProviderConfig.config
          : {};
      setAskModel(result.ask_model || '');
      setAskTemperature(result.ask_temperature ?? ASK_TEMPERATURE_MIN);
      setAskTemperatureInput(
        String(result.ask_temperature ?? ASK_TEMPERATURE_MIN),
      );
      setAskProvider(
        (rawAskProviderConfig.provider || ASK_PROVIDER_LLM).toLowerCase(),
      );
      setAskProviderConfig(rawAskProviderInnerConfig);
      setAskProviderObjectInputs({});
      setAskPreviewLoading(false);
      setAskPreviewQuery('');
      setAskPreviewResult('');
      setAskPreviewMeta(null);
      setKeywords(result.keywords || []);
      setUploadedImageUrl(result.avatar || '');
      // Set TTS Configuration
      setTtsEnabled(result.tts_enabled || false);
      setTtsProvider((result.tts_provider || '').toLowerCase());
      setTtsModel(result.tts_model || '');
      setTtsVoiceId(result.tts_voice_id || '');
      setTtsSpeed(result.tts_speed ?? 1.0);
      setTtsSpeedInput(
        result.tts_speed === null || result.tts_speed === undefined
          ? ''
          : String(result.tts_speed),
      );
      setTtsPitch(result.tts_pitch ?? 0);
      setTtsPitchInput(
        result.tts_pitch === null || result.tts_pitch === undefined
          ? ''
          : String(result.tts_pitch),
      );
      setTtsEmotion(result.tts_emotion || '');
      // Set Language Output Configuration
      setUseLearnerLanguage(result.use_learner_language ?? false);
    }
  };

  const handleTtsPreview = useCallback(
    async (options: TtsPreviewOptions = {}) => {
      const targetKey = options.targetKey || TTS_PREVIEW_CURRENT_TARGET;
      const demoAudioUrl = (options.demoAudioUrl || '').trim();
      const previewVoiceId = (options.voiceId ?? ttsVoiceId ?? '').trim();
      const sameTargetActive =
        (ttsPreviewPlaying || ttsPreviewLoading) &&
        ttsPreviewTarget === targetKey;

      if (sameTargetActive) {
        stopTtsPreview();
        return;
      }
      if (ttsPreviewPlaying || ttsPreviewLoading) {
        stopTtsPreview();
      }

      if (!debugAllowed && !demoAudioUrl) {
        toast({
          title: t('module.shifuSetting.debugDisabledBySoftLimit'),
          variant: 'destructive',
        });
        return;
      }

      const sessionId = ttsPreviewSessionRef.current + 1;
      ttsPreviewSessionRef.current = sessionId;
      requestExclusive(stopTtsPreview);
      setTtsPreviewTarget(targetKey);
      setTtsPreviewLoading(true);
      setTtsPreviewPlaying(true);
      ttsPreviewIsPlayingRef.current = true;
      ttsPreviewIsStreamingRef.current = !demoAudioUrl;
      ttsPreviewWaitingRef.current = !demoAudioUrl;
      ttsPreviewSegmentsRef.current = [];
      ttsPreviewSegmentIndexRef.current = 0;
      closeTtsPreviewStream();

      if (demoAudioUrl) {
        const audio = new Audio(demoAudioUrl);
        ttsPreviewHtmlAudioRef.current = audio;
        audio.onplaying = () => {
          if (ttsPreviewSessionRef.current !== sessionId) {
            return;
          }
          setTtsPreviewLoading(false);
          setTtsPreviewPlaying(true);
          ttsPreviewIsPlayingRef.current = true;
        };
        audio.onended = () => {
          if (ttsPreviewSessionRef.current === sessionId) {
            stopTtsPreview();
          }
        };
        audio.onerror = () => {
          if (ttsPreviewSessionRef.current !== sessionId) {
            return;
          }
          toast({
            title: t('module.shifuSetting.minimaxClonePreviewFailed'),
            variant: 'destructive',
          });
          stopTtsPreview();
        };

        try {
          await audio.play();
          if (ttsPreviewSessionRef.current === sessionId) {
            setTtsPreviewLoading(false);
            setTtsPreviewPlaying(true);
          }
        } catch {
          if (ttsPreviewSessionRef.current === sessionId) {
            toast({
              title: t('module.shifuSetting.minimaxClonePreviewFailed'),
              variant: 'destructive',
            });
            stopTtsPreview();
          }
        }
        return;
      }

      const baseUrl = getResolvedBaseURL();
      const token = useUserStore.getState().getToken();
      const traceHeaders = buildTraceHeaders({
        'Content-Type': 'application/json',
        ...(token
          ? {
              Authorization: `Bearer ${token}`,
              Token: token,
            }
          : {}),
      });
      const source = new SSE(`${baseUrl}/api/shifu/tts/preview`, {
        headers: traceHeaders.headers,
        payload: JSON.stringify({
          provider: resolvedProvider,
          model: ttsModel || '',
          voice_id: previewVoiceId,
          speed: speedValue,
          pitch: pitchValue,
          emotion: ttsEmotion || '',
        }),
        method: 'POST',
      });

      source.addEventListener('message', event => {
        const raw = event?.data;
        if (!raw) return;
        const payload = String(raw).trim();
        if (!payload) return;

        try {
          const response = JSON.parse(payload);
          if (ttsPreviewSessionRef.current !== sessionId) {
            return;
          }

          if (response?.type === 'audio_segment') {
            const segmentPayload = response.content ?? response.data;
            if (!segmentPayload) return;
            const mappedSegment = normalizeAudioSegmentPayload(segmentPayload);
            if (!mappedSegment) {
              return;
            }

            const updatedSegments = mergeAudioSegmentByUniqueKey(
              'tts-preview',
              ttsPreviewSegmentsRef.current,
              mappedSegment,
            );
            if (updatedSegments !== ttsPreviewSegmentsRef.current) {
              ttsPreviewSegmentsRef.current = updatedSegments;
            }

            if (ttsPreviewWaitingRef.current) {
              playPreviewSegment(ttsPreviewSegmentIndexRef.current, sessionId);
            }
            return;
          }

          if (response?.type === 'audio_complete') {
            ttsPreviewIsStreamingRef.current = false;
            setTtsPreviewLoading(false);
            closeTtsPreviewStream();
            if (ttsPreviewSegmentsRef.current.length === 0) {
              stopTtsPreview();
            }
          }
        } catch (error) {
          console.warn('TTS preview stream parse error:', error);
        }
      });

      source.addEventListener('error', error => {
        if (ttsPreviewSessionRef.current !== sessionId) {
          return;
        }
        console.error('TTS preview stream failed:', error);
        stopTtsPreview();
      });

      source.stream();
      ttsPreviewStreamRef.current = source;
    },
    [
      resolvedProvider,
      ttsModel,
      ttsVoiceId,
      speedValue,
      pitchValue,
      ttsEmotion,
      ttsPreviewPlaying,
      ttsPreviewLoading,
      ttsPreviewTarget,
      closeTtsPreviewStream,
      playPreviewSegment,
      requestExclusive,
      stopTtsPreview,
      debugAllowed,
      t,
      toast,
    ],
  );

  // Cleanup TTS preview audio on unmount
  useEffect(() => {
    return () => {
      cleanupTtsPreview();
    };
  }, [cleanupTtsPreview]);

  useEffect(() => {
    if (!open) {
      return;
    }
    init();
  }, [shifuId, open]);

  const submitForm = useCallback(
    async (needClose = true, saveType: 'auto' | 'manual' = 'manual') => {
      if (currentShifu?.readonly) {
        updateOpen(false);
        return true;
      }
      const isNameValid = await form.trigger('name');
      const isPriceValid = await form.trigger('price');
      if (!isPriceValid) {
        if (needClose) {
          updateOpen(true);
        }
        return false;
      }
      const priceValue = parseFloat(form.getValues('price') || '0');
      if (!Number.isNaN(priceValue) && priceValue < MIN_SHIFU_PRICE) {
        form.setError('price', {
          type: 'manual',
          message: t('server.shifu.shifuPriceTooLow', {
            min_shifu_price: MIN_SHIFU_PRICE,
          }),
        });
        if (needClose) {
          updateOpen(true);
        }
        return false;
      }
      if (!isNameValid) {
        if (needClose) {
          updateOpen(true);
        }
        return false;
      }
      await onSubmit(form.getValues(), needClose, saveType);
      return true;
    },
    [form, onSubmit, updateOpen, t, currentShifu?.readonly],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    if (!isDirty) {
      return;
    }
    const timer = setTimeout(() => {
      submitForm(false, 'auto');
    }, 3000);
    return () => clearTimeout(timer);
  }, [open, submitForm, isDirty]);

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (isOnboardingOpen && !nextOpen) {
        updateOpen(true);
        return;
      }
      if (!nextOpen) {
        submitForm(true, 'manual');
        return;
      }
      updateOpen(true);
    },
    [isOnboardingOpen, submitForm, updateOpen],
  );

  const adjustTemperature = (delta: number) => {
    const currentValue = parseFloat(form.getValues('temperature') || '0');
    const safeValue = Number.isNaN(currentValue) ? 0 : currentValue;
    const nextValue = clampTemperature(
      parseFloat((safeValue + delta).toFixed(1)),
    );
    form.setValue('temperature', nextValue.toFixed(1), {
      shouldDirty: true,
      shouldValidate: true,
    });
  };

  const adjustAskTemperature = (delta: number) => {
    const currentValue = Number(askTemperatureInput || askTemperature || 0);
    const safeValue = Number.isNaN(currentValue) ? 0 : currentValue;
    const nextValue = normalizeAskTemperature(
      parseFloat((safeValue + delta).toFixed(1)),
    );
    setAskTemperature(nextValue);
    setAskTemperatureInput(String(nextValue));
  };

  const handleAskPreview = useCallback(async () => {
    if (currentShifu?.readonly || askPreviewLoading) {
      return;
    }
    if (!debugAllowed) {
      toast({
        title: t('module.shifuSetting.debugDisabledBySoftLimit'),
        variant: 'destructive',
      });
      return;
    }
    const query = askPreviewQuery.trim();
    if (!query) {
      toast({
        title: t('module.shifuSetting.askPreviewQuestionRequired'),
        variant: 'destructive',
      });
      return;
    }

    let askConfigForSubmit: Record<string, unknown> = {};
    try {
      askConfigForSubmit = buildAskProviderConfigForSubmit();
    } catch (error) {
      toast({
        title:
          error instanceof Error
            ? error.message
            : t('common.core.unknownError'),
        variant: 'destructive',
      });
      return;
    }

    const askProviderForSubmit =
      resolvedAskProvider ||
      askConfigMeta?.default?.provider ||
      ASK_PROVIDER_LLM;
    const askModeForSubmit = ASK_PROVIDER_MODE_PROVIDER_ONLY;
    const askTemperatureForSubmit = normalizeAskTemperature(
      Number(askTemperatureInput || askTemperature || 0),
    );

    setAskPreviewLoading(true);
    try {
      const response = (await api.askPreview({
        query,
        ask_model: askModel,
        ask_temperature: askTemperatureForSubmit,
        ask_system_prompt: '',
        ask_provider_config: {
          provider: askProviderForSubmit,
          mode: askModeForSubmit,
          config: askConfigForSubmit,
        },
      })) as {
        answer?: string;
        provider?: string;
        requested_provider?: string;
        fallback_used?: boolean;
      };

      const answer = String(response?.answer || '').trim();
      setAskPreviewResult(answer);
      setAskPreviewMeta({
        provider: String(response?.provider || ''),
        requestedProvider: String(response?.requested_provider || ''),
        fallbackUsed: Boolean(response?.fallback_used),
      });
    } catch {
      setAskPreviewResult('');
      setAskPreviewMeta(null);
    } finally {
      setAskPreviewLoading(false);
    }
  }, [
    askConfigMeta?.default?.provider,
    askModel,
    askPreviewLoading,
    askPreviewQuery,
    askTemperature,
    askTemperatureInput,
    buildAskProviderConfigForSubmit,
    currentShifu?.readonly,
    debugAllowed,
    normalizeAskTemperature,
    resolvedAskProvider,
    t,
    toast,
  ]);

  return (
    <>
      <Sheet
        open={open}
        modal={!isOnboardingOpen}
        onOpenChange={handleOpenChange}
      >
        <SheetTrigger asChild>
          <div
            className='flex items-center justify-center rounded-lg cursor-pointer'
            {...buildOnboardingTargetProps(
              triggerTargetId || ONBOARDING_TARGET_IDS.editorSettingsEntry,
            )}
          >
            <Settings size={16} />
          </div>
        </SheetTrigger>
        <SheetContent
          side='right'
          hideOverlay={isOnboardingOpen}
          onInteractOutside={event => {
            if (isOnboardingOpen) {
              event.preventDefault();
            }
          }}
          className='w-full sm:w-[420px] md:w-[480px] h-full flex flex-col p-0'
        >
          <SheetHeader className='px-6 pt-[19px] pb-4'>
            <SheetTitle className='text-lg font-medium'>
              {t('module.shifuSetting.title')}
            </SheetTitle>
          </SheetHeader>
          <div className='h-px w-full bg-border' />
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(data =>
                onSubmit(data, true, 'manual'),
              )}
              className='flex-1 flex flex-col overflow-hidden'
            >
              <div className='flex-1 overflow-y-auto px-6 pt-6'>
                <FormField
                  control={form.control}
                  name='name'
                  render={({ field }) => (
                    <FormItem className='space-y-2 mb-4'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        {t('module.shifuSetting.shifuName')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          disabled={currentShifu?.readonly}
                          maxLength={TITLE_MAX_LENGTH}
                          placeholder={t('module.shifuSetting.placeholder')}
                        />
                      </FormControl>
                      {/* <div className='text-xs text-muted-foreground text-right'>
                      {(field.value?.length ?? 0)}/50
                    </div> */}
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='description'
                  render={({ field }) => (
                    <FormItem className='space-y-2 mb-4'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        {t('module.shifuSetting.shifuDescription')}
                      </FormLabel>
                      <FormControl>
                        <Textarea
                          {...field}
                          maxLength={500}
                          placeholder={t('module.shifuSetting.placeholder')}
                          rows={4}
                          disabled={currentShifu?.readonly}
                        />
                      </FormControl>
                      {/* <div className='text-xs text-muted-foreground text-right'>
                      {(field.value?.length ?? 0)}/300
                    </div> */}
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className='space-y-3 mb-4'>
                  <p className='text-sm font-medium text-foreground'>
                    {t('module.shifuSetting.shifuAvatar')}
                  </p>
                  <span className='text-xs text-muted-foreground'>
                    {t('module.shifuSetting.imageFormatHint')}
                  </span>
                  <div className='flex flex-col gap-3'>
                    {uploadedImageUrl ? (
                      <div className='relative w-24 h-24 bg-gray-100 rounded-lg overflow-hidden'>
                        <img
                          src={uploadedImageUrl}
                          alt={t('module.shifuSetting.shifuAvatar')}
                          className='w-full h-full object-cover'
                        />
                        <button
                          type='button'
                          onClick={() =>
                            document.getElementById('imageUpload')?.click()
                          }
                          className='absolute inset-0 flex items-center justify-center bg-black/30 text-white opacity-0 transition-opacity hover:opacity-100'
                        >
                          <Plus className='h-5 w-5' />
                        </button>
                      </div>
                    ) : (
                      <div
                        className='border-2 border-dashed border-muted-foreground/30 rounded-lg w-24 h-24 flex flex-col items-center justify-center cursor-pointer bg-muted/20'
                        onClick={() =>
                          document.getElementById('imageUpload')?.click()
                        }
                      >
                        <Plus className='h-6 w-6 mb-1 text-muted-foreground' />
                        <p className='text-xs text-muted-foreground'>
                          {t('module.shifuSetting.upload')}
                        </p>
                      </div>
                    )}
                    <input
                      id='imageUpload'
                      type='file'
                      accept='image/jpeg,image/png'
                      onChange={handleImageUpload}
                      className='hidden'
                      disabled={currentShifu?.readonly}
                    />

                    {isUploading && (
                      <div className='space-y-2 mb-4'>
                        <div className='w-full bg-muted rounded-full h-2'>
                          <div
                            className='bg-primary h-2 rounded-full'
                            style={{ width: `${uploadProgress}%` }}
                          ></div>
                        </div>
                        <p className='text-xs text-muted-foreground text-center'>
                          {t('module.shifuSetting.uploading')} {uploadProgress}%
                        </p>
                      </div>
                    )}
                    {imageError && (
                      <p className='text-xs text-destructive'>{imageError}</p>
                    )}
                    {!imageError &&
                      shifuImage &&
                      !isUploading &&
                      !uploadedImageUrl && (
                        <p className='text-xs text-emerald-600'>
                          {t('module.shifuSetting.selected')}:{' '}
                          {shifuImage?.name}
                        </p>
                      )}
                  </div>
                </div>

                <FormField
                  control={form.control}
                  name='model'
                  render={({ field }) => (
                    <FormItem className='space-y-2 mb-4'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        {t('common.core.selectModel')}
                      </FormLabel>
                      <p className='text-xs text-muted-foreground'>
                        {selectModelHint}
                      </p>
                      <FormControl>
                        <ModelList
                          disabled={currentShifu?.readonly}
                          className='h-9'
                          value={field.value ?? ''}
                          onChange={field.onChange}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='temperature'
                  render={({ field }) => (
                    <FormItem className='space-y-2 mb-4'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        {t('module.shifuSetting.shifuTemperature')}
                      </FormLabel>
                      <p className='text-xs text-muted-foreground'>
                        {t('module.shifuSetting.temperatureHint')}
                        <br />
                        {t('module.shifuSetting.temperatureHint2')}
                      </p>
                      <div className='flex items-center gap-2'>
                        <FormControl className='flex-1'>
                          <Input
                            {...field}
                            value={field.value}
                            onChange={field.onChange}
                            disabled={currentShifu?.readonly}
                            type='text'
                            inputMode='decimal'
                            placeholder={t('module.shifuSetting.number')}
                            className='h-9'
                          />
                        </FormControl>
                        {currentShifu?.readonly ? null : (
                          <div className='flex items-center gap-2'>
                            <Button
                              type='button'
                              variant='outline'
                              size='icon'
                              onClick={() => adjustTemperature(-0.1)}
                              className='h-9 w-9'
                            >
                              <Minus className='h-4 w-4' />
                            </Button>
                            <Button
                              type='button'
                              variant='outline'
                              size='icon'
                              onClick={() => adjustTemperature(0.1)}
                              className='h-9 w-9'
                            >
                              <Plus className='h-4 w-4' />
                            </Button>
                          </div>
                        )}
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='systemPrompt'
                  render={({ field }) => (
                    <FormItem className='space-y-2 mb-4'>
                      <div className='flex items-center gap-2'>
                        <FormLabel className='text-sm font-medium text-foreground'>
                          {t('module.shifuSetting.shifuPrompt')}
                        </FormLabel>
                      </div>
                      <p className='text-xs text-muted-foreground'>
                        {t('module.shifuSetting.shifuPromptHint')}
                      </p>
                      <FormControl>
                        <Textarea
                          disabled={currentShifu?.readonly}
                          {...field}
                          maxLength={20000}
                          placeholder={t(
                            'module.shifuSetting.shifuPromptPlaceholder',
                          )}
                          minRows={3}
                          maxRows={30}
                        />
                      </FormControl>
                      {/* <div className='text-xs text-muted-foreground text-right'>
                      {field.value?.length ?? 0}/10000
                    </div> */}
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div>
                  <AskSettingsSection
                    readonly={currentShifu?.readonly || !debugAllowed}
                    askProviderOptions={askProviderOptions}
                    resolvedAskProvider={resolvedAskProvider}
                    askProviderLlmValue={ASK_PROVIDER_LLM}
                    askModel={askModel}
                    onAskModelChange={setAskModel}
                    askTemperature={askTemperature}
                    askTemperatureInput={askTemperatureInput}
                    setAskTemperature={setAskTemperature}
                    setAskTemperatureInput={setAskTemperatureInput}
                    normalizeAskTemperature={normalizeAskTemperature}
                    adjustAskTemperature={adjustAskTemperature}
                    onAskProviderChange={handleAskProviderChange}
                    askProviderFieldEntries={askProviderFieldEntries}
                    askProviderRequiredFields={askProviderRequiredFields}
                    askProviderConfig={askProviderConfig}
                    setAskProviderConfig={setAskProviderConfig}
                    askProviderObjectInputs={askProviderObjectInputs}
                    setAskProviderObjectInputs={setAskProviderObjectInputs}
                    askPreviewLoading={askPreviewLoading}
                    askPreviewQuery={askPreviewQuery}
                    setAskPreviewQuery={setAskPreviewQuery}
                    handleAskPreview={handleAskPreview}
                    askPreviewMeta={askPreviewMeta}
                    askPreviewResult={askPreviewResult}
                  />
                </div>

                {/* Language Output Configuration Section */}
                <div className='mb-6'>
                  <div className='flex items-start justify-between'>
                    <div className='space-y-1'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        {t('module.shifuSetting.useLearnerLanguageTitle')}
                      </FormLabel>
                      <p className='text-xs text-muted-foreground'>
                        {t('module.shifuSetting.useLearnerLanguageDescription')}
                      </p>
                    </div>
                    <Switch
                      checked={useLearnerLanguage}
                      onCheckedChange={setUseLearnerLanguage}
                      disabled={currentShifu?.readonly}
                    />
                  </div>
                </div>

                {/* TTS Configuration Section */}
                <div className='mb-6'>
                  <div
                    className='flex items-start justify-between mb-4'
                    {...buildOnboardingTargetProps(
                      ONBOARDING_TARGET_IDS.editorCourseListenMode,
                    )}
                  >
                    <div className='space-y-1'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        {t('module.shifuSetting.ttsTitle')}
                      </FormLabel>
                      <p className='text-xs text-muted-foreground'>
                        {t('module.shifuSetting.ttsDescription')}
                      </p>
                    </div>
                    <Switch
                      checked={ttsEnabled}
                      onCheckedChange={setTtsEnabled}
                      disabled={currentShifu?.readonly}
                    />
                  </div>

                  {ttsEnabled && (
                    <>
                      {/* Provider Selection */}
                      <div className='space-y-2 mb-4'>
                        <FormLabel className='text-sm font-medium text-foreground'>
                          {t('module.shifuSetting.ttsProvider')}
                        </FormLabel>
                        <p className='text-xs text-muted-foreground'>
                          {t('module.shifuSetting.ttsProviderHint')}
                        </p>
                        <Select
                          value={ttsProvider}
                          onValueChange={value => {
                            setTtsProvider(value);
                            const newProviderConfig = ttsConfig?.providers.find(
                              p => p.name === value,
                            );
                            if (newProviderConfig) {
                              const defaultModel =
                                newProviderConfig.models?.[0]?.value || '';
                              const defaultVoice =
                                newProviderConfig.voices?.[0]?.value || '';
                              const defaultEmotion =
                                newProviderConfig.supports_emotion &&
                                newProviderConfig.emotions?.length
                                  ? newProviderConfig.emotions[0]?.value || ''
                                  : '';
                              setTtsModel(defaultModel);
                              setTtsVoiceId(defaultVoice);
                              setTtsEmotion(defaultEmotion);
                              setTtsSpeed(newProviderConfig.speed.default);
                              setTtsPitch(newProviderConfig.pitch.default);
                              return;
                            }
                            setTtsModel('');
                            setTtsVoiceId('');
                            setTtsEmotion('');
                          }}
                          disabled={currentShifu?.readonly}
                        >
                          <SelectTrigger className='h-9'>
                            <SelectValue
                              placeholder={t(
                                'module.shifuSetting.ttsSelectProvider',
                              )}
                            />
                          </SelectTrigger>
                          <SelectContent>
                            {ttsProviderOptions.map(option => (
                              <SelectItem
                                key={option.value}
                                value={option.value}
                              >
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      {/* Model Selection (only for providers with model options) */}
                      {ttsModelOptions.length > 1 && (
                        <div className='space-y-2 mb-4'>
                          <FormLabel className='text-sm font-medium text-foreground'>
                            {t('module.shifuSetting.ttsModel')}
                          </FormLabel>
                          <Select
                            value={ttsModel}
                            onValueChange={setTtsModel}
                            disabled={currentShifu?.readonly}
                          >
                            <SelectTrigger className='h-9'>
                              <SelectValue
                                placeholder={t(
                                  'module.shifuSetting.ttsSelectModel',
                                )}
                              />
                            </SelectTrigger>
                            <SelectContent>
                              {ttsModelOptions.map(option => (
                                <SelectItem
                                  key={option.value || 'default'}
                                  value={option.value || 'default'}
                                >
                                  {option.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )}

                      {/* Voice Selection */}
                      <div className='space-y-2 mb-4'>
                        <FormLabel className='text-sm font-medium text-foreground'>
                          {t('module.shifuSetting.ttsVoice')}
                        </FormLabel>
                        <Select
                          value={ttsVoiceId}
                          onValueChange={value => {
                            setTtsVoiceId(value);
                            if (resolvedProvider === 'volcengine') {
                              const selectedVoice = ttsVoiceOptions.find(
                                option => option.value === value,
                              );
                              const inferredResourceId =
                                selectedVoice?.resource_id;
                              if (
                                inferredResourceId &&
                                inferredResourceId !== ttsModel
                              ) {
                                setTtsModel(inferredResourceId);
                              }
                            }
                          }}
                          disabled={currentShifu?.readonly}
                        >
                          <SelectTrigger className='h-9'>
                            <SelectValue
                              placeholder={t(
                                'module.shifuSetting.ttsSelectVoice',
                              )}
                            />
                          </SelectTrigger>
                          <SelectContent>
                            {isMiniMaxTtsProvider ? (
                              <>
                                {builtInTtsVoiceOptions.length > 0 ? (
                                  <SelectGroup>
                                    <SelectLabel>
                                      {t(
                                        'module.shifuSetting.minimaxVoiceGroupBuiltIn',
                                      )}
                                    </SelectLabel>
                                    {builtInTtsVoiceOptions.map(option => (
                                      <SelectItem
                                        key={option.value}
                                        value={option.value}
                                        disabled={option.disabled}
                                      >
                                        <span className='truncate'>
                                          {option.label}
                                        </span>
                                      </SelectItem>
                                    ))}
                                  </SelectGroup>
                                ) : null}
                                {clonedTtsVoiceOptions.length > 0 ? (
                                  <>
                                    {builtInTtsVoiceOptions.length > 0 ? (
                                      <SelectSeparator />
                                    ) : null}
                                    <SelectGroup>
                                      <SelectLabel>
                                        {t(
                                          'module.shifuSetting.minimaxVoiceGroupCloned',
                                        )}
                                      </SelectLabel>
                                      {clonedTtsVoiceOptions.map(option => (
                                        <SelectItem
                                          key={option.value}
                                          value={option.value}
                                          disabled={option.disabled}
                                        >
                                          <span className='truncate'>
                                            {option.label}
                                          </span>
                                        </SelectItem>
                                      ))}
                                    </SelectGroup>
                                  </>
                                ) : null}
                                {manualTtsVoiceOptions.length > 0 ? (
                                  <>
                                    {builtInTtsVoiceOptions.length > 0 ||
                                    clonedTtsVoiceOptions.length > 0 ? (
                                      <SelectSeparator />
                                    ) : null}
                                    <SelectGroup>
                                      <SelectLabel>
                                        {t(
                                          'module.shifuSetting.minimaxVoiceGroupManual',
                                        )}
                                      </SelectLabel>
                                      {manualTtsVoiceOptions.map(option => (
                                        <SelectItem
                                          key={option.value}
                                          value={option.value}
                                          disabled={option.disabled}
                                        >
                                          <span className='flex min-w-0 items-center justify-between gap-2'>
                                            <span className='truncate'>
                                              {option.label}
                                            </span>
                                            <Badge
                                              variant='secondary'
                                              className='shrink-0'
                                            >
                                              {t(
                                                'module.shifuSetting.minimaxManualVoiceBadge',
                                              )}
                                            </Badge>
                                          </span>
                                        </SelectItem>
                                      ))}
                                    </SelectGroup>
                                  </>
                                ) : null}
                              </>
                            ) : (
                              mergedTtsVoiceOptions.map(option => (
                                <SelectItem
                                  key={option.value}
                                  value={option.value}
                                  disabled={option.disabled}
                                >
                                  <span className='truncate'>
                                    {option.label}
                                  </span>
                                </SelectItem>
                              ))
                            )}
                          </SelectContent>
                        </Select>

                        {isMiniMaxTtsProvider &&
                          currentProviderConfig?.supports_custom_voice_id && (
                            <div className='flex gap-2'>
                              <Input
                                value={minimaxManualVoiceId}
                                onChange={event =>
                                  setMinimaxManualVoiceId(event.target.value)
                                }
                                placeholder={t(
                                  'module.shifuSetting.minimaxManualVoicePlaceholder',
                                )}
                                disabled={currentShifu?.readonly}
                                className='h-9 flex-1'
                              />
                              <Button
                                type='button'
                                variant='outline'
                                size='sm'
                                onClick={applyMinimaxManualVoiceId}
                                disabled={currentShifu?.readonly}
                              >
                                {t(
                                  'module.shifuSetting.minimaxManualVoiceApply',
                                )}
                              </Button>
                            </div>
                          )}

                        {supportsMiniMaxVoiceCloning && (
                          <div className='space-y-2 rounded-md border p-3'>
                            <div className='flex items-center justify-between gap-2'>
                              <div className='min-w-0'>
                                <p className='text-sm font-medium'>
                                  {t(
                                    'module.shifuSetting.minimaxCloneSectionTitle',
                                  )}
                                </p>
                                <p className='truncate text-xs text-muted-foreground'>
                                  {minimaxCloneCost?.estimated_credits &&
                                  minimaxCloneCost.estimated_credits !== '0'
                                    ? t(
                                        'module.shifuSetting.minimaxCloneCostCredits',
                                        {
                                          credits:
                                            minimaxCloneCost.estimated_credits,
                                        },
                                      )
                                    : t(
                                        'module.shifuSetting.minimaxCloneCostFree',
                                      )}
                                </p>
                              </div>
                              <Button
                                type='button'
                                variant='outline'
                                size='sm'
                                onClick={() => setMinimaxCloneDialogOpen(true)}
                                disabled={currentShifu?.readonly}
                              >
                                <Mic className='mr-2 h-4 w-4' />
                                {t('module.shifuSetting.minimaxCloneCreate')}
                              </Button>
                            </div>

                            {minimaxClonedVoices.length === 0 ? (
                              <p className='text-xs text-muted-foreground'>
                                {t('module.shifuSetting.minimaxCloneEmpty')}
                              </p>
                            ) : (
                              <div className='space-y-2'>
                                {minimaxClonedVoices.map(voice => {
                                  const previewTarget = `clone:${voice.voice_bid}`;
                                  const previewLoading =
                                    ttsPreviewTarget === previewTarget &&
                                    ttsPreviewLoading;
                                  const previewPlaying =
                                    ttsPreviewTarget === previewTarget &&
                                    ttsPreviewPlaying;
                                  const ready = voice.status === 'ready';
                                  const canPreview =
                                    ready &&
                                    (debugAllowed ||
                                      Boolean(
                                        (
                                          voice.minimax_demo_audio_url || ''
                                        ).trim(),
                                      ));

                                  return (
                                    <div
                                      key={voice.voice_bid}
                                      className='flex items-center justify-between gap-2 text-sm'
                                    >
                                      <div className='min-w-0'>
                                        <p className='truncate'>
                                          {voice.display_name || voice.voice_id}
                                        </p>
                                        <p className='truncate text-xs text-muted-foreground'>
                                          {voice.voice_id}
                                        </p>
                                      </div>
                                      <div className='flex shrink-0 items-center gap-1'>
                                        <Badge variant='secondary'>
                                          {t(
                                            `module.shifuSetting.minimaxCloneStatus.${voice.status}`,
                                          )}
                                        </Badge>
                                        <Button
                                          type='button'
                                          variant='ghost'
                                          size='icon'
                                          className='h-7 w-7'
                                          onClick={() =>
                                            handleTtsPreview({
                                              voiceId: voice.voice_id,
                                              targetKey: previewTarget,
                                              demoAudioUrl:
                                                voice.minimax_demo_audio_url ||
                                                '',
                                            })
                                          }
                                          disabled={!canPreview}
                                          title={
                                            canPreview
                                              ? t(
                                                  'module.shifuSetting.minimaxClonePreview',
                                                )
                                              : t(
                                                  'module.shifuSetting.minimaxClonePreviewUnavailable',
                                                )
                                          }
                                        >
                                          {previewLoading ? (
                                            <Loader2 className='h-4 w-4 animate-spin' />
                                          ) : previewPlaying ? (
                                            <Square className='h-4 w-4' />
                                          ) : (
                                            <Volume2 className='h-4 w-4' />
                                          )}
                                        </Button>
                                        {voice.status === 'failed' && (
                                          <Button
                                            type='button'
                                            variant='ghost'
                                            size='icon'
                                            className='h-7 w-7'
                                            onClick={() =>
                                              retryMiniMaxVoice(voice.voice_bid)
                                            }
                                            disabled={currentShifu?.readonly}
                                          >
                                            <RotateCw className='h-4 w-4' />
                                          </Button>
                                        )}
                                        <Button
                                          type='button'
                                          variant='ghost'
                                          size='icon'
                                          className='h-7 w-7'
                                          onClick={() =>
                                            deleteMiniMaxVoice(voice)
                                          }
                                          disabled={currentShifu?.readonly}
                                        >
                                          <Trash2 className='h-4 w-4' />
                                        </Button>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Speed Adjustment */}
                      <div className='space-y-2 mb-4'>
                        <FormLabel className='text-sm font-medium text-foreground'>
                          {t('module.shifuSetting.ttsSpeed')}
                        </FormLabel>
                        <p className='text-xs text-muted-foreground'>
                          {t('module.shifuSetting.ttsSpeedHint')} (
                          {currentProviderConfig?.speed.min} -{' '}
                          {currentProviderConfig?.speed.max})
                        </p>
                        <div className='flex items-center gap-2'>
                          <Input
                            type='text'
                            inputMode='decimal'
                            value={ttsSpeedInput}
                            onChange={e => {
                              setTtsSpeedInput(e.target.value);
                            }}
                            onBlur={() => {
                              const parsed = Number(ttsSpeedInput);
                              const clamped = Number.isFinite(parsed)
                                ? normalizeSpeed(parsed)
                                : speedValue;
                              setTtsSpeed(clamped);
                              setTtsSpeedInput(clamped.toFixed(1));
                            }}
                            disabled={currentShifu?.readonly}
                            className='h-9 flex-1'
                          />
                          {!currentShifu?.readonly && (
                            <div className='flex items-center gap-2'>
                              <Button
                                type='button'
                                variant='outline'
                                size='icon'
                                disabled={isSpeedAtMin}
                                onClick={() =>
                                  setTtsSpeed(() => {
                                    const next = normalizeSpeed(
                                      speedValue - speedStep,
                                    );
                                    setTtsSpeedInput(next.toFixed(1));
                                    return next;
                                  })
                                }
                                className='h-9 w-9'
                              >
                                <Minus className='h-4 w-4' />
                              </Button>
                              <Button
                                type='button'
                                variant='outline'
                                size='icon'
                                disabled={isSpeedAtMax}
                                onClick={() =>
                                  setTtsSpeed(() => {
                                    const next = normalizeSpeed(
                                      speedValue + speedStep,
                                    );
                                    setTtsSpeedInput(next.toFixed(1));
                                    return next;
                                  })
                                }
                                className='h-9 w-9'
                              >
                                <Plus className='h-4 w-4' />
                              </Button>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Pitch Adjustment */}
                      <div className='space-y-2 mb-4'>
                        <FormLabel className='text-sm font-medium text-foreground'>
                          {t('module.shifuSetting.ttsPitch')}
                        </FormLabel>
                        <p className='text-xs text-muted-foreground'>
                          {t('module.shifuSetting.ttsPitchHint')} (
                          {currentProviderConfig?.pitch.min} -{' '}
                          {currentProviderConfig?.pitch.max})
                        </p>
                        <div className='flex items-center gap-2'>
                          <Input
                            type='text'
                            inputMode='decimal'
                            value={ttsPitchInput}
                            onChange={e => {
                              const raw = e.target.value;
                              setTtsPitchInput(raw);
                            }}
                            onBlur={() => {
                              const parsed = Number(ttsPitchInput);
                              const clamped = Number.isFinite(parsed)
                                ? clampPitch(parsed)
                                : pitchValue;
                              const rounded = Math.round(clamped);
                              setTtsPitch(rounded);
                              setTtsPitchInput(String(rounded));
                            }}
                            disabled={currentShifu?.readonly}
                            className='h-9 flex-1'
                          />
                          {!currentShifu?.readonly && (
                            <div className='flex items-center gap-2'>
                              <Button
                                type='button'
                                variant='outline'
                                size='icon'
                                disabled={isPitchAtMin}
                                onClick={() =>
                                  setTtsPitch(() => {
                                    const next = Math.max(
                                      pitchMin,
                                      pitchValue - pitchStep,
                                    );
                                    setTtsPitchInput(String(next));
                                    return next;
                                  })
                                }
                                className='h-9 w-9'
                              >
                                <Minus className='h-4 w-4' />
                              </Button>
                              <Button
                                type='button'
                                variant='outline'
                                size='icon'
                                disabled={isPitchAtMax}
                                onClick={() =>
                                  setTtsPitch(() => {
                                    const next = Math.min(
                                      pitchMax,
                                      pitchValue + pitchStep,
                                    );
                                    setTtsPitchInput(String(next));
                                    return next;
                                  })
                                }
                                className='h-9 w-9'
                              >
                                <Plus className='h-4 w-4' />
                              </Button>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Emotion Selection - only show if provider supports emotion */}
                      {currentProviderConfig?.supports_emotion &&
                        ttsEmotionOptions.length > 0 && (
                          <div className='space-y-2 mb-4'>
                            <FormLabel className='text-sm font-medium text-foreground'>
                              {t('module.shifuSetting.ttsEmotion')}
                            </FormLabel>
                            <Select
                              value={ttsEmotion}
                              onValueChange={setTtsEmotion}
                              disabled={currentShifu?.readonly}
                            >
                              <SelectTrigger className='h-9'>
                                <SelectValue
                                  placeholder={t(
                                    'module.shifuSetting.ttsSelectEmotion',
                                  )}
                                />
                              </SelectTrigger>
                              <SelectContent>
                                {ttsEmotionOptions.map((option, idx) => (
                                  <SelectItem
                                    key={`${option.value || 'default'}-${idx}`}
                                    value={option.value || 'default'}
                                  >
                                    {option.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )}

                      {/* TTS Preview Button */}
                      <div className='pt-2'>
                        <Button
                          type='button'
                          variant='outline'
                          onClick={() => handleTtsPreview()}
                          disabled={
                            (ttsPreviewLoading &&
                              ttsPreviewTarget ===
                                TTS_PREVIEW_CURRENT_TARGET) ||
                            !debugAllowed
                          }
                          className='w-full'
                          title={
                            debugAllowed
                              ? undefined
                              : t(
                                  'module.shifuSetting.debugDisabledBySoftLimit',
                                )
                          }
                        >
                          {ttsPreviewLoading &&
                          ttsPreviewTarget === TTS_PREVIEW_CURRENT_TARGET ? (
                            <>
                              <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                              {t('module.shifuSetting.ttsPreviewLoading')}
                            </>
                          ) : ttsPreviewPlaying &&
                            ttsPreviewTarget === TTS_PREVIEW_CURRENT_TARGET ? (
                            <>
                              <Square className='mr-2 h-4 w-4' />
                              {t('module.shifuSetting.ttsPreviewStop')}
                            </>
                          ) : (
                            <>
                              <Volume2 className='mr-2 h-4 w-4' />
                              {t('module.shifuSetting.ttsPreview')}
                            </>
                          )}
                        </Button>
                      </div>
                    </>
                  )}
                </div>

                <div className='space-y-2 mb-4'>
                  <span className='text-sm font-medium text-foreground'>
                    {t('module.shifuSetting.keywords')}
                  </span>
                  <div className='flex flex-wrap gap-2'>
                    {keywords.map((keyword, index) => (
                      <Badge
                        key={index}
                        variant='secondary'
                        className='flex items-center gap-1'
                      >
                        {keyword}
                        <button
                          type='button'
                          disabled={currentShifu?.readonly}
                          onClick={() => handleRemoveKeyword(keyword)}
                          className='text-xs ml-1 hover:text-destructive'
                        >
                          ×
                        </button>
                      </Badge>
                    ))}
                  </div>
                  <div className='flex gap-2'>
                    <Input
                      id='keywordInput'
                      disabled={currentShifu?.readonly}
                      placeholder={t('module.shifuSetting.inputKeywords')}
                      className='flex-1 h-9'
                    />
                    {!currentShifu?.readonly && (
                      <Button
                        type='button'
                        onClick={handleAddKeyword}
                        variant='outline'
                        size='sm'
                      >
                        {t('module.shifuSetting.addKeyword')}
                      </Button>
                    )}
                  </div>
                </div>

                <FormField
                  control={form.control}
                  name='price'
                  render={({ field }) => (
                    <FormItem className='space-y-2 mb-4'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        <span className='flex items-center gap-2'>
                          <span>
                            {t('module.shifuSetting.price')}
                            {/* {currencySymbol ? (
                          <span className='text-muted-foreground text-sm pl-1'>
                            （{t('module.shifuSetting.priceUnit')}：{currencySymbol}）
                          </span>
                        ) : null} */}
                          </span>
                        </span>
                      </FormLabel>
                      <p className='text-xs text-muted-foreground'>
                        {t('module.shifuSetting.priceUnit')}: {currencySymbol}
                      </p>
                      <FormControl>
                        <Input
                          disabled={currentShifu?.readonly}
                          className='h-9'
                          {...field}
                          placeholder={t('module.shifuSetting.number')}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <div className='h-px w-full bg-border' />
            </form>
          </Form>
        </SheetContent>
      </Sheet>
      <MiniMaxVoiceCloneDialog
        open={minimaxCloneDialogOpen}
        onOpenChange={setMinimaxCloneDialogOpen}
        shifuId={shifuId}
        cloneCost={minimaxCloneCost}
        onRefreshCost={refreshMinimaxVoiceData}
        onVoiceChange={voice => {
          setMinimaxClonedVoices(prev => {
            const next = prev.filter(
              item => item.voice_bid !== voice.voice_bid,
            );
            return [voice, ...next];
          });
        }}
        onVoiceReady={voice => {
          setTtsVoiceId(voice.voice_id);
          setMinimaxClonedVoices(prev => {
            const next = prev.filter(
              item => item.voice_bid !== voice.voice_bid,
            );
            return [voice, ...next];
          });
        }}
      />
    </>
  );
}
