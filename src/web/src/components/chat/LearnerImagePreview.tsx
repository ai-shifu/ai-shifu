import { useTranslation } from 'react-i18next';
import Image from 'next/image';
import { resolveLearnerImageUrl } from '@/lib/learner-images';

export function LearnerImagePreview({ images }: { images: string[] }) {
  const { t } = useTranslation();
  return (
    <div className='flex flex-wrap gap-2'>
      {images.map((url, index) => {
        const source = resolveLearnerImageUrl(url);
        return (
          <a
            key={`${url}-${index}`}
            href={source}
            target='_blank'
            rel='noreferrer'
          >
            <Image
              src={source}
              alt={t('module.chat.attachedImage')}
              width={72}
              height={72}
              unoptimized
              className='h-[72px] w-[72px] rounded-md border object-contain'
            />
          </a>
        );
      })}
    </div>
  );
}
