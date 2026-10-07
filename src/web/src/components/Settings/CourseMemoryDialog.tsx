import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
import { useTracking } from '@/hooks/useTracking';
import { getTrackingIdentityGeneration } from '@/lib/tracking';
import {
  deleteCourseMemory,
  listCourseMemory,
  type CourseMemoryEntry,
} from '@/api/courseMemory';

type Props = { courseId: string; onClose: () => void };

/** Mounted only for an eligible learner open; unmounting invalidates pending results. */
export default function CourseMemoryDialog({ courseId, onClose }: Props) {
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const [items, setItems] = useState<CourseMemoryEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<CourseMemoryEntry | null>(null);
  const [deleting, setDeleting] = useState(false);
  const pending = useRef(false);
  const loadingRef = useRef(false);
  const alive = useRef(false);
  const identity = useRef(getTrackingIdentityGeneration());
  const opened = useRef(false);
  const current = () =>
    alive.current && identity.current === getTrackingIdentityGeneration();
  const track = (name: string, outcome?: 'success' | 'failed') => {
    try {
      void Promise.resolve(
        trackEvent(name, {
          course_id: courseId,
          ...(outcome ? { outcome } : {}),
        }),
      ).catch(() => {});
    } catch {}
  };

  const load = async (before?: string) => {
    if (loadingRef.current || !current()) return;
    loadingRef.current = true;
    setLoading(true);
    setError('');
    try {
      const page = await listCourseMemory(courseId, before);
      if (!current()) return;
      setItems(previous =>
        before ? [...previous, ...page.items] : page.items,
      );
      setCursor(page.next_before);
    } catch {
      if (current()) setError('memoryLoadFailed');
    } finally {
      loadingRef.current = false;
      if (current()) setLoading(false);
    }
  };

  useEffect(() => {
    alive.current = true;
    if (!opened.current) {
      opened.current = true;
      track('learner_course_memory_opened');
    }
    void load();
    return () => {
      alive.current = false;
    };
    // The parent keys this mounted dialog by course and learner identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const remove = async () => {
    if (pending.current || !selected || !current()) return;
    pending.current = true;
    setDeleting(true);
    setError('');
    track('learner_course_memory_delete_attempt');
    try {
      const result = await deleteCourseMemory(courseId, selected.value_id);
      if (!current()) return;
      if (result.conflict) {
        track('learner_course_memory_delete_result', 'failed');
        setSelected(null);
        await load();
        if (current()) setError('memoryChanged');
      } else {
        setItems(previous =>
          previous.filter(item => item.value_id !== selected.value_id),
        );
        setSelected(null);
        track('learner_course_memory_delete_result', 'success');
      }
    } catch {
      if (current()) {
        setError('memoryDeleteFailed');
        track('learner_course_memory_delete_result', 'failed');
      }
    } finally {
      pending.current = false;
      if (current()) setDeleting(false);
    }
  };

  return (
    <Dialog
      open
      onOpenChange={open => {
        if (!open && !pending.current) onClose();
      }}
    >
      <DialogContent
        className='max-w-xl'
        showClose={!deleting}
        onEscapeKeyDown={event => {
          if (pending.current) event.preventDefault();
        }}
      >
        <DialogHeader>
          <DialogTitle>{t('module.settings.memoryTitle')}</DialogTitle>
          <DialogDescription>
            {t('module.settings.memoryDescription')}
          </DialogDescription>
        </DialogHeader>
        {error ? <p role='alert'>{t(`module.settings.${error}`)}</p> : null}
        <div
          className='max-h-[55vh] overflow-y-auto space-y-3'
          aria-busy={loading}
        >
          {!loading && !items.length && !error ? (
            <p>{t('module.settings.memoryEmpty')}</p>
          ) : null}
          {items.map(item => (
            <div
              key={item.value_id}
              className='border rounded p-3 space-y-2'
            >
              <p className='font-medium break-all'>{item.key}</p>
              <p className='whitespace-pre-wrap break-words'>{item.value}</p>
              <Button
                variant='outline'
                disabled={deleting || !!selected}
                onClick={() => {
                  if (!selected) {
                    setError('');
                    setSelected(item);
                  }
                }}
              >
                {t('module.settings.memoryDelete')}
              </Button>
            </div>
          ))}
        </div>
        {loading ? (
          <Loader2
            role='status'
            aria-label={t('module.settings.memoryLoading')}
            className='animate-spin'
          />
        ) : null}
        {!loading && error === 'memoryLoadFailed' ? (
          <Button onClick={() => void load(cursor ?? undefined)}>
            {t('module.settings.memoryRetry')}
          </Button>
        ) : null}
        {!loading && cursor !== null ? (
          <Button
            disabled={deleting}
            onClick={() => void load(cursor)}
          >
            {t('module.settings.memoryMore')}
          </Button>
        ) : null}
        <AlertDialog
          open={!!selected}
          onOpenChange={open => {
            if (!open && !pending.current) setSelected(null);
          }}
        >
          <AlertDialogContent
            onEscapeKeyDown={event => {
              if (pending.current) event.preventDefault();
            }}
          >
            <AlertDialogHeader>
              <AlertDialogTitle>
                {t('module.settings.memoryConfirmTitle')}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {t('module.settings.memoryConfirmDescription')}
              </AlertDialogDescription>
            </AlertDialogHeader>
            {error === 'memoryDeleteFailed' ? (
              <p role='alert'>{t('module.settings.memoryDeleteFailed')}</p>
            ) : null}
            <AlertDialogFooter>
              <Button
                variant='outline'
                disabled={deleting}
                onClick={() => setSelected(null)}
              >
                {t('common.core.cancel')}
              </Button>
              <Button
                disabled={deleting}
                onClick={() => void remove()}
              >
                {deleting ? (
                  <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                ) : null}
                {t('module.settings.memoryConfirm')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  );
}
