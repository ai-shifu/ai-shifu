import React, { useCallback, useEffect, useRef, useState } from 'react';
import { SSE } from 'sse.js';
import { v4 as uuidv4 } from 'uuid';
import {
  Copy,
  Check,
  SlidersVertical,
  Plus,
  Minus,
  CircleHelp,
  Settings,
  Volume2,
  Loader2,
  Square,
} from 'lucide-react';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { uploadFile } from '@/lib/file';
import { getResolvedBaseURL } from '@/c-utils/envUtils';
import {
  type AudioSegment,
  mergeAudioSegment,
  normalizeAudioSegmentPayload,
} from '@/c-utils/audio-utils';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
  SheetTrigger,
} from '@/components/ui/Sheet';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
import { Badge } from '@/components/ui/Badge';
import { Textarea } from '@/components/ui/Textarea';
import { Switch } from '@/components/ui/Switch';
import {
  Select,
  SelectContent,
  SelectItem,
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
  archived?: boolean;
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
const TEMPERATURE_STEP = 0.1;
const FLOAT_EPSILON = 1e-6;
type CopyingState = {
  previewUrl: boolean;
  url: boolean;
};

const defaultCopyingState: CopyingState = {
  previewUrl: false,
  url: false,
};

export default function ShifuSettingDialog({
  shifuId,
  onSave,
}: {
  shifuId: string;
  onSave: () => void;
}) {
  const [open, setOpen] = useState(false);
  const { t } = useTranslation();
  const { currentShifu, models, actions } = useShifu();
  const currentUserId = useUserStore(state => state.userInfo?.user_id || '');
  const { toast } = useToast();
  const defaultLlmModel = useEnvStore(state => state.defaultLlmModel);
  const currencySymbol = useEnvStore(state => state.currencySymbol);
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
  const [copying, setCopying] = useState<CopyingState>(defaultCopyingState);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [archiveDialogOpen, setArchiveDialogOpen] = useState(false);
  const copyTimeoutRef = useRef<
    Record<keyof CopyingState, ReturnType<typeof setTimeout> | null>
  >({
    previewUrl: null,
    url: null,
  });
  const { trackEvent } = useTracking();
  const canManageArchive =
    !!currentShifu?.bid &&
    (currentShifu?.can_manage_archive ??
      (currentShifu?.created_user_bid
        ? currentShifu.created_user_bid === currentUserId
        : !currentShifu?.readonly));
  const handleArchiveToggle = useCallback(async () => {
    if (!currentShifu?.bid || !canManageArchive) {
      return;
    }
    setArchiveLoading(true);
    try {
      if (currentShifu.archived) {
        await api.unarchiveShifu({ shifu_bid: currentShifu.bid });
        toast({
          title: t('module.shifuSetting.unarchiveSuccess'),
        });
      } else {
        await api.archiveShifu({ shifu_bid: currentShifu.bid });
        toast({
          title: t('module.shifuSetting.archiveSuccess'),
        });
      }
      await actions.loadShifu(currentShifu.bid, { silent: true });
      onSave?.();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('common.core.unknownError');
      toast({
        title: message,
        variant: 'destructive',
      });
    } finally {
      setArchiveLoading(false);
      setArchiveDialogOpen(false);
    }
  }, [actions, canManageArchive, currentShifu, onSave, t, toast]);
  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
  // TTS Configuration state
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [ttsProvider, setTtsProvider] = useState('default');
  const [ttsModel, setTtsModel] = useState('');
  const [ttsVoiceId, setTtsVoiceId] = useState('');
  const [ttsSpeed, setTtsSpeed] = useState<number | null>(1.0);
  const [ttsSpeedInput, setTtsSpeedInput] = useState<string>('1.0');
  const [ttsPitch, setTtsPitch] = useState<number | null>(0);
  const [ttsPitchInput, setTtsPitchInput] = useState<string>('0');
  const [ttsEmotion, setTtsEmotion] = useState('');
  const ttsProviderToastShownRef = useRef(false);

  // Language Output Configuration state
  const [useLearnerLanguage, setUseLearnerLanguage] = useState(false);

  // TTS Preview state
  const [ttsPreviewLoading, setTtsPreviewLoading] = useState(false);
  const [ttsPreviewPlaying, setTtsPreviewPlaying] = useState(false);
  const ttsPreviewSessionRef = useRef(0);
  const ttsPreviewStreamRef = useRef<any>(null);
  const ttsPreviewAudioContextRef = useRef<AudioContext | null>(null);
  const ttsPreviewSourceRef = useRef<AudioBufferSourceNode | null>(null);
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
  interface TTSProviderConfig {
    name: string;
    label: string;
    speed: { min: number; max: number; step: number; default: number };
    pitch: { min: number; max: number; step: number; default: number };
    supports_emotion: boolean;
    models: { value: string; label: string }[];
    voices: { value: string; label: string; resource_id?: string }[];
    emotions: { value: string; label: string }[];
  }
  const [ttsConfig, setTtsConfig] = useState<{
    providers: TTSProviderConfig[];
    default_provider: string;
  } | null>(null);

  // Fetch TTS config from backend
  useEffect(() => {
    const fetchTtsConfig = async () => {
      try {
        const config = await api.ttsConfig({});
        setTtsConfig(config);
      } catch (error) {
        console.error('Failed to fetch TTS config:', error);
      }
    };
    fetchTtsConfig();
  }, []);

  const normalizedProvider = ttsProvider === 'default' ? '' : ttsProvider;
  const resolvedProvider =
    normalizedProvider || ttsConfig?.default_provider || '';

  // Get current provider config
  const currentProviderConfig =
    ttsConfig?.providers.find(p => p.name === resolvedProvider) ||
    ttsConfig?.providers[0];

  // Get provider options for dropdown
  const ttsProviderOptions = [
    { value: 'default', label: t('module.shifuSetting.ttsProviderDefault') },
    ...(ttsConfig?.providers.map(p => ({ value: p.name, label: p.label })) ||
      []),
  ];

  // Get models for current provider
  const ttsModelOptions = currentProviderConfig?.models || [];

  // Get voices for current provider
  const ttsVoiceOptions = currentProviderConfig?.voices || [];

  // Get emotions for current provider
  const ttsEmotionOptions =
    currentProviderConfig?.supports_emotion &&
    currentProviderConfig?.emotions?.length > 0
      ? [
          { value: '', label: t('module.shifuSetting.ttsEmotionDefault') },
          ...currentProviderConfig.emotions,
        ]
      : [];
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
  const clampTemperature = useCallback((value: number) => {
    return Math.min(Math.max(value, 0), 2);
  }, []);

  // Sanitize persisted selections when provider/config changes
  useEffect(() => {
    if (!ttsConfig || !resolvedProvider) return;
    const provider = ttsConfig.providers.find(p => p.name === resolvedProvider);
    if (!provider) return;

    if (ttsModel && provider.models?.length > 0) {
      const modelValues = new Set(provider.models.map(m => m.value));
      if (!modelValues.has(ttsModel)) {
        setTtsModel('');
      }
    }

    if (ttsVoiceId && provider.voices?.length > 0) {
      const voiceValues = new Set(provider.voices.map(v => v.value));
      if (!voiceValues.has(ttsVoiceId)) {
        setTtsVoiceId('');
      }
    }

    if (!provider.supports_emotion) {
      if (ttsEmotion) setTtsEmotion('');
    } else if (ttsEmotion && provider.emotions?.length > 0) {
      const emotionValues = new Set(provider.emotions.map(e => e.value));
      if (!emotionValues.has(ttsEmotion)) {
        setTtsEmotion('');
      }
    }
  }, [ttsConfig, resolvedProvider, ttsModel, ttsVoiceId, ttsEmotion]);
  // Define the validation schema using Zod
  const shifuSchema = z.object({
    previewUrl: z.string(),
    url: z.string(),
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
      previewUrl: '',
      url: '',
      name: '',
      description: '',
      model: '',
      systemPrompt: '',
      price: '',
      temperature: '',
    },
  });
  const isDirty = form.formState.isDirty;
  const temperatureValue = parseFloat(form.watch('temperature') || '0');
  const safeTemperature = Number.isFinite(temperatureValue)
    ? temperatureValue
    : TEMPERATURE_MIN;
  const isTempAtMin = safeTemperature <= TEMPERATURE_MIN + FLOAT_EPSILON;
  const isTempAtMax = safeTemperature >= TEMPERATURE_MAX - FLOAT_EPSILON;

  const [formSnapshot, setFormSnapshot] = useState(form.getValues());

  useEffect(() => {
    return () => {
      Object.values(copyTimeoutRef.current).forEach(timeout => {
        if (timeout) {
          clearTimeout(timeout);
        }
      });
    };
  }, []);

  // Handle copy to clipboard
  const handleCopy = (field: keyof CopyingState) => {
    const existingTimeout = copyTimeoutRef.current[field];
    if (existingTimeout) {
      clearTimeout(existingTimeout);
      copyTimeoutRef.current[field] = null;
    }
    navigator.clipboard.writeText(form.getValues(field));
    setCopying(prev => ({ ...prev, [field]: true }));

    copyTimeoutRef.current[field] = setTimeout(() => {
      setCopying(prev => ({ ...prev, [field]: false }));
      copyTimeoutRef.current[field] = null;
    }, 2000);
  };

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
          normalizedProvider ||
          ttsConfig?.default_provider ||
          ttsConfig?.providers?.[0]?.name ||
          '';

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
          setOpen(false);
        }
      } catch {
        if (currentShifu?.readonly) {
          setOpen(false);
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
      normalizedProvider,
      ttsConfig,
      ttsModel,
      ttsVoiceId,
      speedValue,
      pitchValue,
      ttsEmotion,
      useLearnerLanguage,
      toast,
      t,
    ],
  );

  const init = async () => {
    ttsProviderToastShownRef.current = false;
    const result = (await api.getShifuDetail({
      shifu_bid: shifuId,
    })) as Shifu;

    if (result) {
      form.reset({
        name: result.name,
        description: result.description,
        price: (result.price ?? 0).toFixed(2),
        model: result.model || '',
        previewUrl: result.preview_url,
        url: result.url,
        temperature: result.temperature + '',
        systemPrompt: result.system_prompt || '',
      });
      setKeywords(result.keywords || []);
      setUploadedImageUrl(result.avatar || '');
      // Set TTS Configuration
      setTtsEnabled(result.tts_enabled || false);
      setTtsProvider(
        result.tts_provider && result.tts_provider !== 'default'
          ? result.tts_provider
          : 'default',
      );
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

  // TTS Preview handler
  const handleTtsPreview = useCallback(async () => {
    // Stop if already playing
    if (ttsPreviewPlaying || ttsPreviewLoading) {
      stopTtsPreview();
      return;
    }

    const sessionId = ttsPreviewSessionRef.current + 1;
    ttsPreviewSessionRef.current = sessionId;
    requestExclusive(stopTtsPreview);
    setTtsPreviewLoading(true);
    setTtsPreviewPlaying(true);
    ttsPreviewIsPlayingRef.current = true;
    ttsPreviewIsStreamingRef.current = true;
    ttsPreviewWaitingRef.current = true;
    ttsPreviewSegmentsRef.current = [];
    ttsPreviewSegmentIndexRef.current = 0;
    closeTtsPreviewStream();

    const baseUrl = getResolvedBaseURL();
    const source = new SSE(`${baseUrl}/api/shifu/tts/preview`, {
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': uuidv4().replace(/-/g, ''),
      },
      payload: JSON.stringify({
        provider: normalizedProvider,
        model: ttsModel || '',
        voice_id: ttsVoiceId || '',
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

          const updatedSegments = mergeAudioSegment(
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
  }, [
    normalizedProvider,
    ttsModel,
    ttsVoiceId,
    ttsSpeed,
    ttsPitch,
    speedValue,
    pitchValue,
    ttsEmotion,
    ttsPreviewPlaying,
    ttsPreviewLoading,
    closeTtsPreviewStream,
    playPreviewSegment,
    requestExclusive,
    stopTtsPreview,
  ]);

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

  useEffect(() => {
    const subscription = form.watch((value: any) => {
      setFormSnapshot(value);
    });
    return () => subscription.unsubscribe();
  }, [form]);

  const submitForm = useCallback(
    async (needClose = true, saveType: 'auto' | 'manual' = 'manual') => {
      if (currentShifu?.readonly) {
        setOpen(false);
        return true;
      }
      const isNameValid = await form.trigger('name');
      const isPriceValid = await form.trigger('price');
      if (!isPriceValid) {
        if (needClose) {
          setOpen(true);
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
          setOpen(true);
        }
        return false;
      }
      if (!isNameValid) {
        if (needClose) {
          setOpen(true);
        }
        return false;
      }
      await onSubmit(form.getValues(), needClose, saveType);
      return true;
    },
    [form, onSubmit, setOpen, t, currentShifu?.readonly],
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
      if (!nextOpen) {
        submitForm(true, 'manual');
        return;
      }
      setOpen(true);
    },
    [submitForm, setOpen],
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

  return (
    <>
      <AlertDialog
        open={archiveDialogOpen}
        onOpenChange={setArchiveDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {currentShifu?.archived
                ? t('module.shifuSetting.unarchiveTitle')
                : t('module.shifuSetting.archiveTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {currentShifu?.archived
                ? t('module.shifuSetting.unarchiveConfirm')
                : t('module.shifuSetting.archiveConfirm')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={archiveLoading}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={archiveLoading}
              onClick={handleArchiveToggle}
            >
              {t('common.core.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <Sheet
        open={open}
        onOpenChange={handleOpenChange}
      >
        <SheetTrigger asChild>
          <div className='flex items-center justify-center rounded-lg cursor-pointer'>
            <Settings size={16} />
          </div>
        </SheetTrigger>
        <SheetContent
          side='right'
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
              <div className='flex-1 overflow-y-auto px-6'>
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
                  name='previewUrl'
                  render={({ field }) => (
                    <FormItem className='space-y-2 mb-4'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        {t('module.shifuSetting.previewUrl')}
                      </FormLabel>
                      <FormControl>
                        <div className='flex items-center gap-2'>
                          <input
                            type='hidden'
                            {...field}
                          />
                          <span
                            className='flex-1 text-sm underline whitespace-nowrap overflow-hidden text-ellipsis'
                            style={{
                              color: 'var(--base-muted-foreground, #737373)',
                            }}
                            title={field.value}
                          >
                            {field.value}
                          </span>
                          <button
                            type='button'
                            onClick={() => handleCopy('previewUrl')}
                            className='flex items-center justify-center text-muted-foreground hover:text-foreground focus:outline-none'
                            style={{ width: 20, height: 20 }}
                          >
                            {copying.previewUrl ? (
                              <Check className='w-[14px] h-[14px]' />
                            ) : (
                              <Copy className='w-[14px] h-[14px]' />
                            )}
                          </button>
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='url'
                  render={({ field }) => (
                    <FormItem className='space-y-2 mb-4'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        {t('module.shifuSetting.learningUrl')}
                      </FormLabel>
                      <FormControl>
                        <div className='flex items-center gap-2'>
                          <input
                            type='hidden'
                            {...field}
                          />
                          <span
                            className='flex-1 text-sm underline whitespace-nowrap overflow-hidden text-ellipsis'
                            style={{
                              color: 'var(--base-muted-foreground, #737373)',
                            }}
                            title={field.value}
                          >
                            {field.value}
                          </span>
                          <button
                            type='button'
                            onClick={() => handleCopy('url')}
                            className='flex items-center justify-center text-muted-foreground hover:text-foreground focus:outline-none'
                            style={{ width: 20, height: 20 }}
                          >
                            {copying.url ? (
                              <Check className='w-[14px] h-[14px]' />
                            ) : (
                              <Copy className='w-[14px] h-[14px]' />
                            )}
                          </button>
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

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
                        {/* <a
                        href='https://markdownflow.ai/docs/zh/specification/how-it-works/#2'
                        target='_blank'
                        rel='noopener noreferrer'
                      >
                        <CircleHelp className='h-4 w-4 text-muted-foreground' />
                      </a> */}
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
                  <div className='flex items-start justify-between mb-4'>
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
                            // Reset voice, model, and params when provider changes
                            setTtsVoiceId('');
                            setTtsModel('');
                            setTtsEmotion('');
                            // Reset speed and pitch to new provider's defaults
                            const providerKey =
                              value === 'default'
                                ? ttsConfig?.default_provider || ''
                                : value;
                            const newProviderConfig = ttsConfig?.providers.find(
                              p => p.name === providerKey,
                            );
                            if (newProviderConfig) {
                              setTtsSpeed(newProviderConfig.speed.default);
                              setTtsPitch(newProviderConfig.pitch.default);
                            }
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
                            {ttsVoiceOptions.map(option => (
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
                          onClick={handleTtsPreview}
                          disabled={ttsPreviewLoading}
                          className='w-full'
                        >
                          {ttsPreviewLoading ? (
                            <>
                              <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                              {t('module.shifuSetting.ttsPreviewLoading')}
                            </>
                          ) : ttsPreviewPlaying ? (
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
          {canManageArchive && (
            <div className='flex justify-end mt-6 mb-6 pr-4'>
              <Button
                type='button'
                variant='outline'
                className='border border-destructive text-destructive hover:bg-destructive/5 px-4 py-2 h-10 rounded-lg'
                onClick={() => setArchiveDialogOpen(true)}
                disabled={archiveLoading}
              >
                {archiveLoading
                  ? t('common.core.submitting')
                  : currentShifu?.archived
                    ? t('module.shifuSetting.unarchive')
                    : t('module.shifuSetting.archive')}
              </Button>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
