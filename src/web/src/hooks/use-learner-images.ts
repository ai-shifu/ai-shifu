import type { ImageInputOptions } from 'markdown-flow-ui/renderer';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  LEARNER_IMAGE_TYPES,
  MAX_LEARNER_IMAGE_BYTES,
  MAX_LEARNER_IMAGES,
  resolveLearnerImageUrl,
} from '@/lib/learner-images';
import { toast } from './use-toast';
import { useTracking } from './use-tracking';

export const useLearnerImages = (
  scope: string,
  surface: 'answer' | 'follow_up',
  previewMode = false,
  initialImages: string[] = [],
) => {
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const initialKey = initialImages.join('\n');
  const [images, setImages] = useState<string[]>(initialImages);
  const [uploading, setUploading] = useState(false);
  const busy = useRef(false);
  const generation = useRef(0);
  useEffect(() => {
    generation.current += 1;
    busy.current = false;
    setImages(initialKey ? initialKey.split('\n') : []);
    setUploading(false);
    return () => {
      generation.current += 1;
    };
  }, [scope, initialKey]);

  const track = (name: string, outcome?: 'success' | 'failed') => {
    if (previewMode) return;
    try {
      void trackEvent(name, {
        surface,
        ...(outcome ? { outcome } : {}),
      })?.catch(() => {});
    } catch {}
  };

  const addFiles = async (files: File[]) => {
    if (busy.current || !files.length) return;
    if (
      images.length + files.length > MAX_LEARNER_IMAGES ||
      files.some(
        file =>
          !LEARNER_IMAGE_TYPES.includes(file.type) ||
          file.size === 0 ||
          file.size > MAX_LEARNER_IMAGE_BYTES,
      )
    ) {
      toast({ title: t('module.chat.imageInputInvalid') });
      return;
    }
    busy.current = true;
    setUploading(true);
    const currentGeneration = generation.current;
    try {
      for (const file of files) {
        if (generation.current !== currentGeneration) break;
        track('learner_image_upload_started');
        try {
          const { uploadLearnerImage } = await import('@/api/learning');
          const url = await uploadLearnerImage(file);
          track('learner_image_upload_finished', 'success');
          if (generation.current === currentGeneration)
            setImages(current => [...current, url]);
        } catch {
          track('learner_image_upload_finished', 'failed');
          if (generation.current === currentGeneration)
            toast({ title: t('module.chat.imageUploadFailed') });
          break;
        }
      }
    } finally {
      if (generation.current === currentGeneration) {
        busy.current = false;
        setUploading(false);
      }
    }
  };

  const imageInput: ImageInputOptions = {
    images,
    uploading,
    onSelect: addFiles,
    onRemove: index =>
      setImages(current => current.filter((_, i) => i !== index)),
    maxImages: MAX_LEARNER_IMAGES,
    accept: LEARNER_IMAGE_TYPES.join(','),
    resolvePreviewUrl: resolveLearnerImageUrl,
  };
  return { images, setImages, uploading, addFiles, imageInput };
};
