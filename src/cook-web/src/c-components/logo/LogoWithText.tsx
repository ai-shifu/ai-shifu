import { memo, useMemo } from 'react';
import Image, { type StaticImageData } from 'next/image';

import { useEnvStore } from '@/c-store/envStore';

import imgLogoRow from '@/c-assets/logos/ai-shifu-logo-horizontal.png';
import imgLogoColumn from '@/c-assets/logos/ai-shifu-logo-vertical.png';

/**
 *
 * @param {direction} 'row' | 'col'
 * @param {size} number
 * @returns
 */
export const LogoWithText = ({ direction, size = 64 }) => {
  const isRow = direction === 'row';
  const flexFlow = isRow ? 'row nowrap' : 'column nowrap';
  const logoHorizontal = useEnvStore(state => state.logoHorizontal);
  const logoVertical = useEnvStore(state => state.logoVertical);
  const logoUrl = useEnvStore(state => state.logoUrl);
  const homeUrl = useEnvStore(state => state.homeUrl);
  const logoSrc: string | StaticImageData = useMemo(() => {
    if (isRow) {
      return logoUrl || logoHorizontal || imgLogoRow;
    }
    return logoVertical || imgLogoColumn;
  }, [isRow, logoHorizontal, logoVertical, logoUrl]);

  return (
    <div
      style={{
        display: 'flex',
        flexFlow: flexFlow,
        alignItems: 'center',
        // ...commonStyles,
      }}
    >
      <a
        href={homeUrl || 'https://ai-shifu.cn/'}
        target='_blank'
      >
        {isRow ? <Image
          src={logoSrc}
          alt='logo'
          height={size}
          priority
        /> : <Image
          src={logoSrc}
          alt='logo'
          style={{
            width: 'size',
            height: size,
            objectFit: 'contain',
          }}
          width={size}
          height={size}
          priority
        />}
      </a>
    </div>
  );
};

export default memo(LogoWithText);
