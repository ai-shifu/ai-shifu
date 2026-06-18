import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Loader2, Mic, Square, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import api from '@/api';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';

import {
  MINIMAX_PROMPT_MAX_SECONDS,
  MINIMAX_SOURCE_MAX_SECONDS,
  MINIMAX_SOURCE_MIN_SECONDS,
  MINIMAX_SUPPORTED_UPLOAD_TYPES,
  getMiniMaxCloneSubmitBlockReason,
  type MiniMaxCloneSubmitBlockReason,
  type MiniMaxClonedVoice,
} from './minimax-voice-clone';

interface MiniMaxCloneCost {
  estimated_credits?: string;
  available_credits?: string;
  can_submit?: boolean;
  billing_enabled?: boolean;
}

interface MiniMaxVoiceCloneDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shifuId: string;
  cloneCost: MiniMaxCloneCost | null;
  onRefreshCost: () => Promise<void>;
  onVoiceChange: (voice: MiniMaxClonedVoice) => void;
  onVoiceReady: (voice: MiniMaxClonedVoice) => void;
}

export default function MiniMaxVoiceCloneDialog({
  open,
  onOpenChange,
  shifuId,
  cloneCost,
  onRefreshCost,
  onVoiceChange,
  onVoiceReady,
}: MiniMaxVoiceCloneDialogProps) {
  const { t } = useTranslation();
  const [displayName, setDisplayName] = useState('');
  const [voiceId, setVoiceId] = useState('');
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceCaptureMethod, setSourceCaptureMethod] = useState<
    'recording' | 'upload'
  >('recording');
  const [promptFile, setPromptFile] = useState<File | null>(null);
  const [recordingKind, setRecordingKind] = useState<
    'source' | 'prompt' | null
  >(null);
  const [sourceElapsed, setSourceElapsed] = useState(0);
  const [promptElapsed, setPromptElapsed] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [pollingVoice, setPollingVoice] = useState<MiniMaxClonedVoice | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = useState('');
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const recordingStartedAtRef = useRef<number>(0);
  const recordingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const submitBlockReason = useMemo(
    () =>
      getMiniMaxCloneSubmitBlockReason({
        sourceFileSelected: Boolean(sourceFile),
        sourceCaptureMethod,
        sourceElapsed,
        recordingKind,
        submitting,
        cloneInProgress: Boolean(pollingVoice),
        canSubmitByCredits: cloneCost?.can_submit !== false,
      }),
    [
      cloneCost?.can_submit,
      pollingVoice,
      recordingKind,
      sourceCaptureMethod,
      sourceElapsed,
      sourceFile,
      submitting,
    ],
  );

  const canSubmit = submitBlockReason === null;
  const sourceMaxMinutes = Math.floor(MINIMAX_SOURCE_MAX_SECONDS / 60);

  const sourceStatusText =
    sourceCaptureMethod === 'upload' && sourceFile
      ? t('module.shifuSetting.minimaxCloneUploadReady')
      : t('module.shifuSetting.minimaxCloneSeconds', {
          seconds: sourceElapsed,
        });
  const promptStatusText =
    promptFile && promptElapsed === 0
      ? t('module.shifuSetting.minimaxCloneUploadReady')
      : t('module.shifuSetting.minimaxCloneSeconds', {
          seconds: promptElapsed,
        });
  const submitBlockText = getSubmitBlockText({
    reason: submitBlockReason,
    currentSeconds: sourceElapsed,
    minSeconds: MINIMAX_SOURCE_MIN_SECONDS,
    t,
  });

  const costText =
    cloneCost?.estimated_credits && cloneCost.estimated_credits !== '0'
      ? t('module.shifuSetting.minimaxCloneCostCredits', {
          credits: cloneCost.estimated_credits,
        })
      : t('module.shifuSetting.minimaxCloneCostFree');

  const reset = useCallback(() => {
    setDisplayName('');
    setVoiceId('');
    setSourceFile(null);
    setSourceCaptureMethod('recording');
    setPromptFile(null);
    setSourceElapsed(0);
    setPromptElapsed(0);
    setSubmitting(false);
    setPollingVoice(null);
    setErrorMessage('');
  }, []);

  const stopRecording = useCallback(() => {
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    mediaRecorderRef.current = null;
    mediaStreamRef.current?.getTracks().forEach(track => track.stop());
    mediaStreamRef.current = null;
    setRecordingKind(null);
  }, []);

  const startRecording = useCallback(
    async (kind: 'source' | 'prompt') => {
      if (
        !navigator.mediaDevices?.getUserMedia ||
        typeof MediaRecorder === 'undefined'
      ) {
        setErrorMessage(
          t('module.shifuSetting.minimaxCloneRecordingUnsupported'),
        );
        return;
      }
      stopRecording();
      setErrorMessage('');
      chunksRef.current = [];
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const mimeType = pickRecordingMimeType();
      const recorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType } : undefined,
      );
      mediaRecorderRef.current = recorder;
      recordingStartedAtRef.current = Date.now();
      setRecordingKind(kind);
      if (kind === 'source') {
        setSourceElapsed(0);
        setSourceFile(null);
      } else {
        setPromptElapsed(0);
        setPromptFile(null);
      }
      recorder.ondataavailable = event => {
        if (event.data?.size) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const elapsed = Math.max(
          0,
          Math.round((Date.now() - recordingStartedAtRef.current) / 1000),
        );
        const type = mimeType || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type });
        const file = new File(
          [blob],
          kind === 'source' ? 'recording.webm' : 'prompt.webm',
          { type },
        );
        if (kind === 'source') {
          setSourceFile(file);
          setSourceCaptureMethod('recording');
          setSourceElapsed(elapsed);
        } else {
          setPromptFile(file);
          setPromptElapsed(Math.min(elapsed, MINIMAX_PROMPT_MAX_SECONDS));
        }
      };
      recorder.start();
      recordingTimerRef.current = setInterval(() => {
        const elapsed = Math.max(
          0,
          Math.round((Date.now() - recordingStartedAtRef.current) / 1000),
        );
        if (kind === 'source') {
          setSourceElapsed(elapsed);
          if (elapsed >= MINIMAX_SOURCE_MAX_SECONDS) {
            stopRecording();
          }
        } else {
          setPromptElapsed(Math.min(elapsed, MINIMAX_PROMPT_MAX_SECONDS));
          if (elapsed >= MINIMAX_PROMPT_MAX_SECONDS) {
            stopRecording();
          }
        }
      }, 500);
    },
    [stopRecording, t],
  );

  const pollVoice = useCallback(
    (voice: MiniMaxClonedVoice) => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
      setPollingVoice(voice);
      pollTimerRef.current = setInterval(async () => {
        try {
          const detail = (await api.getMinimaxTtsVoice({
            voice_bid: voice.voice_bid,
          })) as MiniMaxClonedVoice;
          setPollingVoice(detail);
          onVoiceChange(detail);
          if (detail.status === 'ready' || detail.status === 'failed') {
            if (pollTimerRef.current) {
              clearInterval(pollTimerRef.current);
              pollTimerRef.current = null;
            }
            if (detail.status === 'ready') {
              onVoiceReady(detail);
              onOpenChange(false);
              reset();
            }
          }
        } catch {
          // Keep polling; transient route failures are expected while workers run.
        }
      }, 3000);
    },
    [onOpenChange, onVoiceChange, onVoiceReady, reset],
  );

  const submitClone = useCallback(async () => {
    if (!sourceFile || !canSubmit) return;
    setSubmitting(true);
    setErrorMessage('');
    try {
      const formData = new FormData();
      const normalizedDisplayName =
        displayName.trim() ||
        buildDefaultCloneDisplayName(
          t('module.shifuSetting.minimaxCloneDefaultDisplayName'),
        );
      formData.append('shifu_bid', shifuId);
      formData.append('display_name', normalizedDisplayName);
      if (!displayName.trim()) {
        setDisplayName(normalizedDisplayName);
      }
      if (voiceId.trim()) {
        formData.append('voice_id', voiceId.trim());
      }
      formData.append('source_capture_method', sourceCaptureMethod);
      formData.append('source_audio', sourceFile);
      if (promptFile) {
        formData.append('prompt_audio', promptFile);
      }
      const created = (await api.submitMinimaxTtsVoiceClone(formData, {
        skipErrorToast: true,
      })) as MiniMaxClonedVoice;
      onVoiceChange(created);
      pollVoice(created);
      await onRefreshCost();
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('module.shifuSetting.minimaxCloneSubmitFailed'),
      );
    } finally {
      setSubmitting(false);
    }
  }, [
    canSubmit,
    displayName,
    onRefreshCost,
    onVoiceChange,
    pollVoice,
    promptFile,
    shifuId,
    sourceCaptureMethod,
    sourceFile,
    t,
    voiceId,
  ]);

  useEffect(() => {
    if (!open) {
      stopRecording();
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    } else {
      onRefreshCost();
    }
  }, [onRefreshCost, open, stopRecording]);

  useEffect(() => {
    return () => {
      stopRecording();
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, [stopRecording]);

  return (
    <Dialog
      open={open}
      onOpenChange={nextOpen => {
        onOpenChange(nextOpen);
        if (!nextOpen) reset();
      }}
    >
      <DialogContent className='max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {t('module.shifuSetting.minimaxCloneDialogTitle')}
          </DialogTitle>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='space-y-2'>
            <label className='text-sm font-medium'>
              {t('module.shifuSetting.minimaxCloneDisplayName')}
            </label>
            <Input
              value={displayName}
              maxLength={64}
              onChange={event => setDisplayName(event.target.value)}
              placeholder={t(
                'module.shifuSetting.minimaxCloneDisplayNamePlaceholder',
              )}
            />
            <p className='text-xs leading-5 text-muted-foreground'>
              {t('module.shifuSetting.minimaxCloneDisplayNameHint')}
            </p>
          </div>

          <div className='space-y-2'>
            <label className='text-sm font-medium'>
              {t('module.shifuSetting.minimaxCloneVoiceId')}
            </label>
            <Input
              value={voiceId}
              maxLength={64}
              onChange={event => setVoiceId(event.target.value)}
              placeholder={t(
                'module.shifuSetting.minimaxCloneVoiceIdPlaceholder',
              )}
            />
          </div>

          <div className='space-y-2'>
            <div className='flex items-center justify-between'>
              <label className='text-sm font-medium'>
                {t('module.shifuSetting.minimaxCloneSourceAudio')}
              </label>
              <div className='flex items-center gap-2'>
                <Badge variant='secondary'>
                  {t('module.shifuSetting.minimaxCloneRequired')}
                </Badge>
                <Badge variant='secondary'>{sourceStatusText}</Badge>
              </div>
            </div>
            <p className='text-xs leading-5 text-muted-foreground'>
              {t('module.shifuSetting.minimaxCloneSourceAudioDescription', {
                maxMinutes: sourceMaxMinutes,
                minSeconds: MINIMAX_SOURCE_MIN_SECONDS,
              })}
            </p>
            <div className='grid grid-cols-2 gap-2'>
              <Button
                type='button'
                variant='outline'
                onClick={() =>
                  recordingKind === 'source'
                    ? stopRecording()
                    : startRecording('source')
                }
              >
                {recordingKind === 'source' ? (
                  <Square className='mr-2 h-4 w-4' />
                ) : (
                  <Mic className='mr-2 h-4 w-4' />
                )}
                {recordingKind === 'source'
                  ? t('module.shifuSetting.minimaxCloneStopRecording')
                  : t('module.shifuSetting.minimaxCloneRecord')}
              </Button>
              <Button
                type='button'
                variant='outline'
                onClick={() =>
                  document.getElementById('minimax-source-upload')?.click()
                }
              >
                <Upload className='mr-2 h-4 w-4' />
                {t('module.shifuSetting.minimaxCloneUpload')}
              </Button>
            </div>
            <input
              id='minimax-source-upload'
              type='file'
              accept={MINIMAX_SUPPORTED_UPLOAD_TYPES}
              className='hidden'
              onChange={event => {
                const file = event.target.files?.[0] || null;
                if (file) {
                  setSourceFile(file);
                  setSourceCaptureMethod('upload');
                  setSourceElapsed(0);
                }
              }}
            />
            {sourceFile ? (
              <p className='truncate text-xs text-muted-foreground'>
                {t('module.shifuSetting.minimaxCloneAudioSelected', {
                  name: sourceFile.name,
                })}
              </p>
            ) : null}
          </div>

          <div className='space-y-2'>
            <div className='flex items-center justify-between'>
              <label className='text-sm font-medium'>
                {t('module.shifuSetting.minimaxClonePromptAudio')}
              </label>
              <div className='flex items-center gap-2'>
                <Badge variant='outline'>
                  {t('module.shifuSetting.minimaxCloneOptional')}
                </Badge>
                <Badge variant='secondary'>{promptStatusText}</Badge>
              </div>
            </div>
            <p className='text-xs leading-5 text-muted-foreground'>
              {t('module.shifuSetting.minimaxClonePromptAudioDescription', {
                seconds: MINIMAX_PROMPT_MAX_SECONDS,
              })}
            </p>
            <div className='grid grid-cols-2 gap-2'>
              <Button
                type='button'
                variant='outline'
                onClick={() =>
                  recordingKind === 'prompt'
                    ? stopRecording()
                    : startRecording('prompt')
                }
              >
                {recordingKind === 'prompt' ? (
                  <Square className='mr-2 h-4 w-4' />
                ) : (
                  <Mic className='mr-2 h-4 w-4' />
                )}
                {recordingKind === 'prompt'
                  ? t('module.shifuSetting.minimaxCloneStopRecording')
                  : t('module.shifuSetting.minimaxCloneRecord')}
              </Button>
              <Button
                type='button'
                variant='outline'
                onClick={() =>
                  document.getElementById('minimax-prompt-upload')?.click()
                }
              >
                <Upload className='mr-2 h-4 w-4' />
                {t('module.shifuSetting.minimaxCloneUpload')}
              </Button>
            </div>
            <input
              id='minimax-prompt-upload'
              type='file'
              accept={MINIMAX_SUPPORTED_UPLOAD_TYPES}
              className='hidden'
              onChange={event => {
                const file = event.target.files?.[0] || null;
                if (file) {
                  setPromptFile(file);
                  setPromptElapsed(0);
                }
              }}
            />
            {promptFile ? (
              <p className='truncate text-xs text-muted-foreground'>
                {t('module.shifuSetting.minimaxCloneAudioSelected', {
                  name: promptFile.name,
                })}
              </p>
            ) : null}
          </div>

          <div className='flex items-center justify-between text-sm'>
            <span className='text-muted-foreground'>{costText}</span>
            {cloneCost?.can_submit === false ? (
              <span className='text-destructive'>
                {t('module.shifuSetting.minimaxCloneInsufficientCredits')}
              </span>
            ) : null}
          </div>

          {pollingVoice ? (
            <div className='flex items-center justify-between rounded-md border px-3 py-2 text-sm'>
              <span className='truncate'>{pollingVoice.display_name}</span>
              <Badge variant='secondary'>
                {t(
                  `module.shifuSetting.minimaxCloneStatus.${pollingVoice.status}`,
                )}
              </Badge>
            </div>
          ) : null}

          {errorMessage ? (
            <p className='text-sm text-destructive'>{errorMessage}</p>
          ) : null}

          {submitBlockText ? (
            <p className='text-xs leading-5 text-muted-foreground'>
              {submitBlockText}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
          >
            {t('common.core.cancel')}
          </Button>
          <Button
            type='button'
            disabled={!canSubmit}
            onClick={submitClone}
            title={submitBlockText || undefined}
          >
            {submitting ? (
              <Loader2 className='mr-2 h-4 w-4 animate-spin' />
            ) : null}
            {t('module.shifuSetting.minimaxCloneSubmit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function pickRecordingMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/wav',
  ];
  return candidates.find(type => MediaRecorder.isTypeSupported(type)) || '';
}

function buildDefaultCloneDisplayName(prefix: string): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, '0');
  const stamp = `${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(
    now.getHours(),
  )}:${pad(now.getMinutes())}`;
  return `${prefix} ${stamp}`.trim();
}

function getSubmitBlockText({
  reason,
  currentSeconds,
  minSeconds,
  t,
}: {
  reason: MiniMaxCloneSubmitBlockReason;
  currentSeconds: number;
  minSeconds: number;
  t: ReturnType<typeof useTranslation>['t'];
}): string {
  switch (reason) {
    case 'clone_in_progress':
      return t('module.shifuSetting.minimaxCloneSubmitReasonCloneInProgress');
    case 'insufficient_credits':
      return t(
        'module.shifuSetting.minimaxCloneSubmitReasonInsufficientCredits',
      );
    case 'missing_source_audio':
      return t('module.shifuSetting.minimaxCloneSubmitReasonMissingSource', {
        seconds: minSeconds,
      });
    case 'recording_in_progress':
      return t('module.shifuSetting.minimaxCloneSubmitReasonRecording');
    case 'source_recording_too_short':
      return t('module.shifuSetting.minimaxCloneSubmitReasonSourceTooShort', {
        currentSeconds,
        minSeconds,
      });
    case 'submitting':
      return t('module.shifuSetting.minimaxCloneSubmitReasonSubmitting');
    default:
      return '';
  }
}
