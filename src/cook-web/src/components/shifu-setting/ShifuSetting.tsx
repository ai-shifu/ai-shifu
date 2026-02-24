import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { SSE } from 'sse.js';
import { v4 as uuidv4 } from 'uuid';
import {
  Copy,
  Check,
  Plus,
  Minus,
  Settings,
  Volume2,
  Loader2,
  Square,
  ChevronDown,
} from 'lucide-react';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import useSWR from 'swr';
import { uploadFile } from '@/lib/file';
import { getResolvedBaseURL } from '@/c-utils/envUtils';
import { normalizeShifuDetail } from '@/lib/shifu-normalize';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
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
  SheetTrigger,
} from '@/components/ui/Sheet';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Button } from '@/components/ui/Button';
import { RadioGroup, RadioGroupItem } from '@/components/ui/RadioGroup';
import { ScrollArea } from '@/components/ui/ScrollArea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
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
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/Form';
import { Trans, useTranslation } from 'react-i18next';
import api from '@/api';
import useExclusiveAudio from '@/hooks/useExclusiveAudio';
import {
  createAudioContext,
  decodeAudioBufferFromBase64,
  playAudioBuffer,
  resumeAudioContext,
} from '@/lib/audio-playback';
import { useToast } from '@/hooks/useToast';
import { cn } from '@/lib/utils';

import ModelList from '@/components/model-list';
import { useEnvStore } from '@/c-store';
import { TITLE_MAX_LENGTH } from '@/c-constants/uiConstants';
import { useShifu, useUserStore } from '@/store';
import { useTracking } from '@/c-common/hooks/useTracking';
import { canManageArchive as canManageArchiveForShifu } from '@/lib/shifu-permissions';
import { isValidEmail } from '@/lib/validators';

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
type CopyingState = {
  previewUrl: boolean;
  url: boolean;
};

const defaultCopyingState: CopyingState = {
  previewUrl: false,
  url: false,
};

type SharedPermission = {
  user_id: string;
  identifier: string;
  nickname?: string;
  permission: 'view' | 'edit' | 'publish';
};

const MAX_SHARED_PERMISSION_COUNT = 10;
const INVALID_CONTACT_SAMPLE_LIMIT = 5;
// Keep phone validation aligned with backend bulk rules (11 digits only).
const PERMISSION_PHONE_PATTERN = /^\d{11}$/;
const PHONE_EXTRACT_PATTERN = /(?:^|\D)(\d{11})(?!\d)/g;
const PHONE_TOKEN_PATTERN = /\d{11}/;
const PHONE_TOKEN_SPLIT_PATTERN = /[\s,;\n\uFF0C\uFF1B]+/;
const EMAIL_EXTRACT_PATTERN = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const EMAIL_CANDIDATE_PATTERN = /[^\s,\uFF0C;\uFF1B]+@[^\s,\uFF0C;\uFF1B]+/g;

const unique = (items: string[]): string[] => Array.from(new Set(items));

const normalizeEmailCandidate = (value: string): string =>
  value.replace(/^[,\uFF0C;\uFF1B.\u3002]+|[,\uFF0C;\uFF1B.\u3002]+$/g, '');

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
  const currentUser = useUserStore(state => state.userInfo);
  const currentUserId = currentUser?.user_id || '';
  const { toast } = useToast();
  const defaultLlmModel = useEnvStore(state => state.defaultLlmModel);
  const currencySymbol = useEnvStore(state => state.currencySymbol);
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const defaultLoginMethod = useEnvStore(state => state.defaultLoginMethod);
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
  const canManageArchive = canManageArchiveForShifu(
    currentShifu,
    currentUserId,
  );
  const canManagePermissions =
    Boolean(currentShifu?.created_user_bid) &&
    currentShifu?.created_user_bid === currentUserId;
  const [permissionDialogOpen, setPermissionDialogOpen] = useState(false);
  const [permissionInput, setPermissionInput] = useState('');
  const [permissionError, setPermissionError] = useState('');
  const [permissionLevel, setPermissionLevel] =
    useState<SharedPermission['permission']>('view');
  const [grantLoading, setGrantLoading] = useState(false);
  const [grantConfirmOpen, setGrantConfirmOpen] = useState(false);
  const [pendingGrantContacts, setPendingGrantContacts] = useState<string[]>(
    [],
  );
  const [pendingGrantPermission, setPendingGrantPermission] =
    useState<SharedPermission['permission']>('view');
  const [permissionEditMode, setPermissionEditMode] = useState(false);
  const [permissionEdits, setPermissionEdits] = useState<
    Record<string, SharedPermission['permission']>
  >({});
  const [permissionRemovals, setPermissionRemovals] = useState<Set<string>>(
    new Set(),
  );
  const [permissionConfirmOpen, setPermissionConfirmOpen] = useState(false);
  const [permissionSaveLoading, setPermissionSaveLoading] = useState(false);

  const contactType = useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );

  const permissionKey = useMemo(() => {
    if (!permissionDialogOpen || !currentShifu?.bid || !canManagePermissions) {
      return null;
    }
    return ['shifu-permissions', currentShifu.bid, contactType] as const;
  }, [
    canManagePermissions,
    contactType,
    currentShifu?.bid,
    permissionDialogOpen,
  ]);

  const {
    data: permissionData,
    error: permissionLoadError,
    isLoading: permissionLoading,
    mutate: refreshPermissionList,
  } = useSWR(
    permissionKey,
    async ([, shifuBid, contactTypeValue]) =>
      (await api.listShifuPermissions({
        shifu_bid: shifuBid,
        contact_type: contactTypeValue,
      })) as { items?: SharedPermission[] },
    { revalidateOnFocus: false },
  );

  const permissionList = useMemo(
    () => permissionData?.items || [],
    [permissionData],
  );

  useEffect(() => {
    if (!permissionLoadError || !permissionDialogOpen) {
      return;
    }
    const message =
      permissionLoadError instanceof Error
        ? permissionLoadError.message
        : t('common.core.unknownError');
    toast({ title: message, variant: 'destructive' });
  }, [permissionDialogOpen, permissionLoadError, t, toast]);

  const contactLabel =
    contactType === 'email'
      ? t('module.shifuSetting.permissionEmailLabel')
      : t('module.shifuSetting.permissionPhoneLabel');
  const contactPlaceholder =
    contactType === 'email'
      ? t('module.shifuSetting.permissionEmailPlaceholder')
      : t('module.shifuSetting.permissionPhonePlaceholder');
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

  const permissionOptions = useMemo(
    () => [
      { value: 'view', label: t('module.shifuSetting.permissionReadOnly') },
      { value: 'edit', label: t('module.shifuSetting.permissionEdit') },
      { value: 'publish', label: t('module.shifuSetting.permissionPublish') },
    ],
    [t],
  );

  // Extract phone/email identifiers from free-form input and align with backend rules.
  const parseContacts = useCallback(
    (value: string) => {
      if (!value.trim()) {
        return { contacts: [], invalidContacts: [] };
      }

      if (contactType === 'phone') {
        const matches = Array.from(value.matchAll(PHONE_EXTRACT_PATTERN)).map(
          match => match[1],
        );
        const contacts = unique(matches).filter(phone =>
          PERMISSION_PHONE_PATTERN.test(phone),
        );
        const tokens = value
          .split(PHONE_TOKEN_SPLIT_PATTERN)
          .filter(token => token.length > 0);
        const invalidContacts = unique(
          tokens
            .filter(
              token => /\d/.test(token) && !PHONE_TOKEN_PATTERN.test(token),
            )
            .map(token => token.replace(/\D/g, ''))
            .filter(
              candidate =>
                candidate.length > 0 &&
                !PERMISSION_PHONE_PATTERN.test(candidate),
            ),
        );
        return { contacts, invalidContacts };
      }

      const emailMatches = Array.from(
        value.matchAll(EMAIL_EXTRACT_PATTERN),
      ).map(match => match[0].toLowerCase());
      const contacts = unique(emailMatches);
      const candidateMatches = Array.from(
        value.matchAll(EMAIL_CANDIDATE_PATTERN),
      ).map(match => normalizeEmailCandidate(match[0]).toLowerCase());
      const invalidContacts = unique(candidateMatches).filter(
        candidate => candidate && !isValidEmail(candidate),
      );
      return { contacts, invalidContacts };
    },
    [contactType],
  );

  const handleGrantPermissions = useCallback(async () => {
    if (!currentShifu?.bid || !canManagePermissions) {
      return;
    }
    const { contacts, invalidContacts } = parseContacts(permissionInput);
    if (invalidContacts.length > 0) {
      const sample = invalidContacts
        .slice(0, INVALID_CONTACT_SAMPLE_LIMIT)
        .join(', ');
      const messageContacts =
        invalidContacts.length > INVALID_CONTACT_SAMPLE_LIMIT
          ? `${sample}...`
          : sample;
      setPermissionError(
        contactType === 'email'
          ? t('module.shifuSetting.permissionEmailInvalid', {
              values: messageContacts,
            })
          : t('module.shifuSetting.permissionPhoneInvalid', {
              values: messageContacts,
            }),
      );
      return;
    }
    if (contacts.length === 0) {
      setPermissionError(t('module.shifuSetting.permissionContactRequired'));
      return;
    }
    const normalizedExisting = new Set(
      permissionList.map(item =>
        contactType === 'email'
          ? (item.identifier || '').toLowerCase()
          : item.identifier || '',
      ),
    );
    const normalizedContacts = contacts.map(contact =>
      contactType === 'email' ? contact.toLowerCase() : contact,
    );
    const ownerEmail =
      typeof currentUser?.email === 'string'
        ? currentUser.email.toLowerCase()
        : '';
    const ownerPhoneCandidate =
      typeof currentUser?.phone === 'string'
        ? currentUser.phone
        : typeof currentUser?.mobile === 'string'
          ? currentUser.mobile
          : typeof currentUser?.user_mobile === 'string'
            ? currentUser.user_mobile
            : '';
    const ownerPhone = ownerPhoneCandidate.replace(/\D/g, '');
    const ownerContact = contactType === 'email' ? ownerEmail : ownerPhone;
    if (ownerContact && normalizedContacts.includes(ownerContact)) {
      setPermissionError(t('module.shifuSetting.permissionOwnerNotAllowed'));
      return;
    }
    const existingContacts = contacts.filter((contact, index) =>
      normalizedExisting.has(normalizedContacts[index]),
    );
    const newContacts = contacts.filter(
      (_contact, index) => !normalizedExisting.has(normalizedContacts[index]),
    );

    if (existingContacts.length > 0) {
      const sample = existingContacts
        .slice(0, INVALID_CONTACT_SAMPLE_LIMIT)
        .join(', ');
      const messageContacts =
        existingContacts.length > INVALID_CONTACT_SAMPLE_LIMIT
          ? `${sample}...`
          : sample;
      setPermissionError(
        t('module.shifuSetting.permissionDuplicate', {
          values: messageContacts,
        }),
      );
      return;
    }

    if (
      permissionList.length + newContacts.length >
      MAX_SHARED_PERMISSION_COUNT
    ) {
      setPermissionError(
        t('module.shifuSetting.permissionLimit', {
          count: MAX_SHARED_PERMISSION_COUNT,
        }),
      );
      return;
    }

    setPermissionError('');
    setPendingGrantContacts(newContacts);
    setPendingGrantPermission(permissionLevel);
    setGrantConfirmOpen(true);
  }, [
    canManagePermissions,
    contactType,
    currentShifu?.bid,
    parseContacts,
    permissionInput,
    permissionLevel,
    permissionList,
    t,
    currentUser,
  ]);

  const handleConfirmGrantPermissions = useCallback(async () => {
    if (
      !currentShifu?.bid ||
      !canManagePermissions ||
      pendingGrantContacts.length === 0
    ) {
      setGrantConfirmOpen(false);
      return;
    }
    setPermissionError('');
    setGrantLoading(true);
    try {
      await api.grantShifuPermissions({
        shifu_bid: currentShifu.bid,
        contact_type: contactType,
        contacts: pendingGrantContacts,
        permission: pendingGrantPermission,
      });
      toast({ title: t('module.shifuSetting.permissionGrantSuccess') });
      setPermissionInput('');
      await refreshPermissionList();
      setPermissionDialogOpen(false);
      setGrantConfirmOpen(false);
      setPendingGrantContacts([]);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('common.core.unknownError');
      toast({ title: message, variant: 'destructive' });
    } finally {
      setGrantLoading(false);
    }
  }, [
    canManagePermissions,
    contactType,
    currentShifu?.bid,
    pendingGrantContacts,
    pendingGrantPermission,
    refreshPermissionList,
    t,
    toast,
  ]);

  const pendingGrantPermissionLabel = useMemo(() => {
    const match = permissionOptions.find(
      option => option.value === pendingGrantPermission,
    );
    return match?.label || pendingGrantPermission;
  }, [pendingGrantPermission, permissionOptions]);

  const handleUpdatePermission = useCallback(
    (
      item: SharedPermission,
      nextPermission: SharedPermission['permission'],
    ) => {
      if (item.permission === nextPermission) {
        setPermissionEdits(prev => {
          if (!(item.user_id in prev)) {
            return prev;
          }
          const next = { ...prev };
          delete next[item.user_id];
          return next;
        });
        return;
      }
      setPermissionEdits(prev => ({
        ...prev,
        [item.user_id]: nextPermission,
      }));
    },
    [],
  );

  const handleSavePermissionChanges = useCallback(async () => {
    if (!currentShifu?.bid || !canManagePermissions) {
      return;
    }
    const removalIds = Array.from(permissionRemovals);
    const updates = Object.entries(permissionEdits).filter(
      ([userId]) => !permissionRemovals.has(userId),
    );
    if (removalIds.length === 0 && updates.length === 0) {
      toast({
        title: t('module.shifuSetting.permissionEditNoChanges'),
      });
      return;
    }
    setPermissionSaveLoading(true);
    try {
      type PermissionOperation = {
        type: 'remove' | 'grant';
        userId: string;
        permission?: SharedPermission['permission'];
        identifier?: string;
      };

      const removalOperations: PermissionOperation[] = removalIds.map(
        userId => ({
          type: 'remove' as const,
          userId,
        }),
      );
      const grantOperations: PermissionOperation[] = updates.map(
        ([userId, nextPermission]) => {
          const item = permissionList.find(entry => entry.user_id === userId);
          return {
            type: 'grant' as const,
            userId,
            permission: nextPermission,
            identifier: item?.identifier || '',
          };
        },
      );
      const operations = [...removalOperations, ...grantOperations];

      const missingIdentifiers = operations.filter(
        operation => operation.type === 'grant' && !operation.identifier,
      );
      if (missingIdentifiers.length > 0) {
        throw new Error(t('module.shifuSetting.permissionContactRequired'));
      }

      const removals = operations.filter(
        operation => operation.type === 'remove',
      );
      const grants = operations.filter(operation => operation.type === 'grant');

      const removalResults = await Promise.allSettled(
        removals.map(operation =>
          api.removeShifuPermission({
            shifu_bid: currentShifu.bid,
            user_id: operation.userId,
          }),
        ),
      );
      const grantResults = await Promise.allSettled(
        grants.map(operation =>
          api.grantShifuPermissions({
            shifu_bid: currentShifu.bid,
            contact_type: contactType,
            contacts: [operation.identifier || ''],
            permission: operation.permission || 'view',
          }),
        ),
      );
      const results = [...removalResults, ...grantResults];

      const failed = results
        .map((result, index) => ({
          result,
          operation: [...removals, ...grants][index],
        }))
        .filter(item => item.result.status === 'rejected')
        .map(item => item.operation.identifier || item.operation.userId);

      await refreshPermissionList();
      setPermissionConfirmOpen(false);

      if (failed.length > 0) {
        setPermissionEdits({});
        setPermissionRemovals(new Set());
        toast({
          title: t('common.core.unknownError'),
          description: failed.join(', '),
          variant: 'destructive',
        });
        return;
      }

      toast({ title: t('module.shifuSetting.permissionEditSuccess') });
      setPermissionEditMode(false);
      setPermissionEdits({});
      setPermissionRemovals(new Set());
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('common.core.unknownError');
      toast({ title: message, variant: 'destructive' });
    } finally {
      setPermissionSaveLoading(false);
    }
  }, [
    canManagePermissions,
    contactType,
    currentShifu?.bid,
    permissionEdits,
    permissionList,
    permissionRemovals,
    refreshPermissionList,
    t,
    toast,
  ]);

  const { requestExclusive, releaseExclusive } = useExclusiveAudio();
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
  } | null>(null);

  // Fetch TTS config from backend
  useEffect(() => {
    const fetchTtsConfig = async () => {
      try {
        const config = await api.ttsConfig({});
        const providers = Array.isArray(config?.providers)
          ? config.providers.map(provider => ({
              ...provider,
              name: (provider.name || '').toLowerCase(),
            }))
          : [];
        setTtsConfig({ providers });
      } catch (error) {
        console.error('Failed to fetch TTS config:', error);
      }
    };
    fetchTtsConfig();
  }, []);

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

    if (provider.voices?.length > 0) {
      const voiceValues = new Set(provider.voices.map(v => v.value));
      const fallbackVoice = provider.voices[0]?.value || '';
      if (ttsEnabled) {
        const nextVoice = voiceValues.has(ttsVoiceId)
          ? ttsVoiceId
          : fallbackVoice;
        if (nextVoice && nextVoice !== ttsVoiceId) {
          setTtsVoiceId(nextVoice);
        }
      } else if (ttsVoiceId && !voiceValues.has(ttsVoiceId)) {
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
  ]);
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
          resolvedProvider || ttsConfig?.providers?.[0]?.name || '';

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
      resolvedProvider,
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
        previewUrl: result.preview_url,
        url: result.url,
        temperature: result.temperature + '',
        systemPrompt: result.system_prompt || '',
      });
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
        provider: resolvedProvider,
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
    resolvedProvider,
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

  const permissionLabelMap = useMemo(() => {
    return permissionOptions.reduce<Record<string, string>>((map, option) => {
      map[option.value] = option.label;
      return map;
    }, {});
  }, [permissionOptions]);
  const permissionOriginalMap = useMemo(() => {
    const map = new Map<string, SharedPermission['permission']>();
    permissionList.forEach(item => {
      map.set(item.user_id, item.permission);
    });
    return map;
  }, [permissionList]);
  const sortedPermissionList = useMemo(() => {
    const orderMap: Record<SharedPermission['permission'], number> = {
      view: 0,
      edit: 1,
      publish: 2,
    };
    return [...permissionList].sort((a, b) => {
      const orderDiff = orderMap[a.permission] - orderMap[b.permission];
      if (orderDiff !== 0) {
        return orderDiff;
      }
      const aValue = (a.identifier || a.user_id || '').toLowerCase();
      const bValue = (b.identifier || b.user_id || '').toLowerCase();
      return aValue.localeCompare(bValue);
    });
  }, [permissionList]);
  const permissionChangeSummary = useMemo(() => {
    return Object.entries(permissionEdits)
      .filter(([userId]) => !permissionRemovals.has(userId))
      .map(([userId, nextPermission]) => {
        const originalPermission = permissionOriginalMap.get(userId) || 'view';
        const label = permissionLabelMap[nextPermission] || nextPermission;
        const originalLabel =
          permissionLabelMap[originalPermission] || originalPermission;
        const item = permissionList.find(entry => entry.user_id === userId);
        return {
          userId,
          identifier: item?.identifier || item?.user_id || userId,
          from: originalLabel,
          to: label,
        };
      });
  }, [
    permissionEdits,
    permissionLabelMap,
    permissionList,
    permissionOriginalMap,
    permissionRemovals,
  ]);
  const permissionRemovalSummary = useMemo(() => {
    return permissionList
      .filter(item => permissionRemovals.has(item.user_id))
      .map(item => ({
        userId: item.user_id,
        identifier: item.identifier || item.user_id,
      }));
  }, [permissionList, permissionRemovals]);

  return (
    <>
      <Dialog
        open={permissionDialogOpen}
        onOpenChange={nextOpen => {
          setPermissionDialogOpen(nextOpen);
          if (!nextOpen) {
            setPermissionError('');
            setPermissionInput('');
            setPermissionEditMode(false);
            setPermissionEdits({});
            setPermissionRemovals(new Set());
            setGrantConfirmOpen(false);
            setPermissionConfirmOpen(false);
            setPendingGrantContacts([]);
            setPendingGrantPermission('view');
            setPermissionLevel('view');
            setGrantLoading(false);
            setPermissionSaveLoading(false);
          }
        }}
      >
        <DialogContent className='pb-4'>
          <DialogHeader>
            <DialogTitle>
              <span>{t('module.shifuSetting.permissionDialogTitle')}</span>
            </DialogTitle>
          </DialogHeader>
          <Tabs
            defaultValue='grant'
            className='w-full'
          >
            <TabsList className='mb-1 w-full justify-start bg-transparent p-0'>
              <TabsTrigger
                value='grant'
                className='rounded-none border-b-2 border-transparent px-0 pb-2 pt-0 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none'
              >
                {t('module.shifuSetting.permissionTabGrant')}
              </TabsTrigger>
              <TabsTrigger
                value='list'
                className='ml-6 rounded-none border-b-2 border-transparent px-0 pb-2 pt-0 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none'
              >
                {t('module.shifuSetting.permissionTabList')}
              </TabsTrigger>
            </TabsList>
            <TabsContent
              value='grant'
              className='mt-1 min-h-[256px]'
            >
              <div className='space-y-6'>
                <div className='space-y-4'>
                  <Label className='text-sm font-medium text-foreground'>
                    {contactLabel}
                  </Label>
                  <Textarea
                    value={permissionInput}
                    onChange={event => {
                      setPermissionInput(event.target.value);
                      if (permissionError) {
                        setPermissionError('');
                      }
                    }}
                    placeholder={contactPlaceholder}
                    rows={3}
                  />
                  {permissionError ? (
                    <p className='text-xs text-destructive'>
                      {permissionError}
                    </p>
                  ) : null}
                </div>
                <div className='space-y-4'>
                  <Label className='text-sm font-medium text-foreground'>
                    {t('module.shifuSetting.permissionLabel')}
                  </Label>
                  <RadioGroup
                    value={permissionLevel}
                    onValueChange={value =>
                      setPermissionLevel(
                        value as SharedPermission['permission'],
                      )
                    }
                    className='flex flex-row flex-wrap gap-x-8 gap-y-2'
                  >
                    {permissionOptions.map(option => (
                      <div
                        key={option.value}
                        className='flex items-center'
                      >
                        <RadioGroupItem
                          value={option.value}
                          id={`permission-${option.value}`}
                        />
                        <Label
                          htmlFor={`permission-${option.value}`}
                          className='ml-2 text-sm font-medium text-foreground'
                        >
                          {option.value === 'publish' ? (
                            <>
                              {option.label}
                              <span className='text-xs text-muted-foreground'>
                                {t(
                                  'module.shifuSetting.permissionPublishHintWrapped',
                                  {
                                    hint: t(
                                      'module.shifuSetting.permissionPublishHint',
                                    ),
                                  },
                                )}
                              </span>
                            </>
                          ) : (
                            option.label
                          )}
                        </Label>
                      </div>
                    ))}
                  </RadioGroup>
                </div>
              </div>
              <DialogFooter className='mt-8 gap-2'>
                <Button
                  type='button'
                  variant='outline'
                  onClick={() => setPermissionDialogOpen(false)}
                  disabled={grantLoading}
                >
                  {t('common.core.cancel')}
                </Button>
                <Button
                  type='button'
                  onClick={handleGrantPermissions}
                  disabled={grantLoading}
                >
                  {grantLoading
                    ? t('common.core.submitting')
                    : t('module.shifuSetting.permissionGrant')}
                </Button>
              </DialogFooter>
            </TabsContent>
            <TabsContent
              value='list'
              className='mt-1 min-h-[256px]'
            >
              <ScrollArea
                type='always'
                className='mt-3 h-[180px] pr-2'
              >
                {permissionLoading ? (
                  <div className='text-xs text-muted-foreground'>
                    {t('module.shifuSetting.permissionLoading')}
                  </div>
                ) : permissionList.length === 0 ? (
                  <div className='text-xs text-muted-foreground'>
                    {t('module.shifuSetting.permissionEmpty')}
                  </div>
                ) : (
                  <div className='space-y-1'>
                    {sortedPermissionList.map(item => (
                      <div
                        key={item.user_id}
                        className='flex items-center gap-3 rounded-md px-2 py-1 hover:bg-muted/40'
                      >
                        <div className='min-w-0 flex-1'>
                          <div className='text-sm font-medium min-w-0'>
                            <span className='relative inline-block max-w-full pr-3'>
                              <span
                                className={cn(
                                  'block truncate',
                                  permissionRemovals.has(item.user_id) &&
                                    'line-through text-muted-foreground',
                                )}
                              >
                                {item.identifier || item.user_id}
                              </span>
                            </span>
                          </div>
                        </div>
                        {!permissionEditMode ? (
                          <div className='flex items-center gap-1 text-xs font-medium text-muted-foreground'>
                            <span>
                              {permissionLabelMap[item.permission] ||
                                item.permission}
                            </span>
                          </div>
                        ) : (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <button
                                type='button'
                                className='flex items-center gap-1 text-xs font-medium text-primary hover:text-primary'
                              >
                                {permissionRemovals.has(item.user_id)
                                  ? t('module.shifuSetting.permissionRemoved')
                                  : permissionLabelMap[
                                      permissionEdits[item.user_id] ||
                                        item.permission
                                    ] ||
                                    permissionEdits[item.user_id] ||
                                    item.permission}
                                <ChevronDown className='h-3.5 w-3.5' />
                              </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align='end'>
                              {permissionOptions.map(option => (
                                <DropdownMenuItem
                                  key={option.value}
                                  className='justify-between'
                                  onSelect={() => {
                                    if (permissionRemovals.has(item.user_id)) {
                                      setPermissionRemovals(prev => {
                                        const next = new Set(prev);
                                        next.delete(item.user_id);
                                        return next;
                                      });
                                    }
                                    handleUpdatePermission(
                                      item,
                                      option.value as SharedPermission['permission'],
                                    );
                                  }}
                                >
                                  <span>{option.label}</span>
                                  {(permissionEdits[item.user_id] ||
                                    item.permission) === option.value ? (
                                    <Check className='h-4 w-4 text-primary' />
                                  ) : (
                                    <span className='h-4 w-4' />
                                  )}
                                </DropdownMenuItem>
                              ))}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                className='text-destructive focus:text-destructive'
                                onSelect={() => {
                                  setPermissionRemovals(prev => {
                                    const next = new Set(prev);
                                    if (next.has(item.user_id)) {
                                      next.delete(item.user_id);
                                    } else {
                                      next.add(item.user_id);
                                    }
                                    return next;
                                  });
                                  setPermissionEdits(current => {
                                    if (!(item.user_id in current)) {
                                      return current;
                                    }
                                    const updated = { ...current };
                                    delete updated[item.user_id];
                                    return updated;
                                  });
                                }}
                              >
                                {permissionRemovals.has(item.user_id)
                                  ? t(
                                      'module.shifuSetting.permissionRemoveUndo',
                                    )
                                  : t('module.shifuSetting.permissionRemove')}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
              {permissionList.length > 0 ? (
                <div className='mt-4 text-xs text-muted-foreground'>
                  {t('module.shifuSetting.permissionCount', {
                    count: permissionList.length,
                    max: MAX_SHARED_PERMISSION_COUNT,
                  })}
                </div>
              ) : null}
              <DialogFooter className='mt-4 gap-2'>
                {permissionEditMode ? (
                  <Button
                    type='button'
                    onClick={() => {
                      const hasChanges =
                        permissionRemovals.size > 0 ||
                        Object.keys(permissionEdits).length > 0;
                      if (!hasChanges) {
                        setPermissionEditMode(false);
                        setPermissionEdits({});
                        setPermissionRemovals(new Set());
                        return;
                      }
                      setPermissionConfirmOpen(true);
                    }}
                  >
                    {t('common.core.confirm')}
                  </Button>
                ) : (
                  <>
                    <Button
                      type='button'
                      variant='outline'
                      onClick={() => setPermissionDialogOpen(false)}
                    >
                      {t('common.core.cancel')}
                    </Button>
                    <Button
                      type='button'
                      onClick={() => {
                        setPermissionEditMode(true);
                        setPermissionEdits({});
                        setPermissionRemovals(new Set());
                      }}
                    >
                      {t('module.shifuSetting.permissionEdit')}
                    </Button>
                  </>
                )}
              </DialogFooter>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={grantConfirmOpen}
        onOpenChange={openState => {
          setGrantConfirmOpen(openState);
          if (!openState) {
            setPendingGrantContacts([]);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('module.shifuSetting.permissionGrantConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className='space-y-2 text-sm text-muted-foreground'>
                <div>
                  <Trans
                    i18nKey='module.shifuSetting.permissionGrantConfirmDesc'
                    values={{
                      contactType: contactLabel,
                      permission: pendingGrantPermissionLabel,
                    }}
                    components={{
                      strong: <span className='font-medium text-foreground' />,
                    }}
                  />
                </div>
                <div className='space-y-1'>
                  {pendingGrantContacts.map(contact => (
                    <div key={contact}>{contact}</div>
                  ))}
                </div>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={grantLoading}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={grantLoading}
              onClick={event => {
                event.preventDefault();
                handleConfirmGrantPermissions();
              }}
            >
              {grantLoading
                ? t('common.core.submitting')
                : t('common.core.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={permissionConfirmOpen}
        onOpenChange={openState => {
          setPermissionConfirmOpen(openState);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('module.shifuSetting.permissionEditConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className='space-y-2 text-sm text-muted-foreground'>
                {permissionChangeSummary.length > 0 ? (
                  <div>
                    <div className='font-medium text-foreground'>
                      {t('module.shifuSetting.permissionEditChangeTitle')}
                    </div>
                    <div className='mt-1 space-y-1'>
                      {permissionChangeSummary.map(item => (
                        <div key={item.userId}>
                          {t('module.shifuSetting.permissionEditChangeItem', {
                            identifier: item.identifier,
                            from: item.from,
                            to: item.to,
                          })}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                {permissionRemovalSummary.length > 0 ? (
                  <div>
                    <div className='font-medium text-foreground'>
                      {t('module.shifuSetting.permissionEditRemoveTitle')}
                    </div>
                    <div className='mt-1 space-y-1'>
                      {permissionRemovalSummary.map(item => (
                        <div key={item.userId}>{item.identifier}</div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={permissionSaveLoading}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={permissionSaveLoading}
              onClick={event => {
                event.preventDefault();
                handleSavePermissionChanges();
              }}
            >
              {permissionSaveLoading
                ? t('common.core.submitting')
                : t('common.core.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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

                {canManagePermissions && (
                  <div className='mb-6'>
                    <div className='flex items-start justify-between gap-4'>
                      <div className='space-y-1'>
                        <FormLabel className='text-sm font-medium text-foreground'>
                          {t('module.shifuSetting.permissionSectionTitle')}
                        </FormLabel>
                        <p className='text-xs text-muted-foreground'>
                          {t('module.shifuSetting.permissionSectionDesc')}
                        </p>
                      </div>
                      <Button
                        type='button'
                        variant='outline'
                        size='sm'
                        onClick={() => setPermissionDialogOpen(true)}
                      >
                        {t('module.shifuSetting.permissionManage')}
                      </Button>
                    </div>
                  </div>
                )}

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
