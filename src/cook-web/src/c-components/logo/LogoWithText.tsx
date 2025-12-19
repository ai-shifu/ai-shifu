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
  const logoWideUrl = useEnvStore(state => state.logoWideUrl);
  const logoSquareUrl = useEnvStore(state => state.logoSquareUrl);
  const homeUrl = useEnvStore(state => state.homeUrl);
  const wideLogoSrc: string | StaticImageData = useMemo(() => {
    return logoWideUrl || logoHorizontal || imgLogoRow;
  }, [logoHorizontal, logoWideUrl]);

  const squareLogoSrc: string | StaticImageData = useMemo(() => {
    return logoSquareUrl || logoVertical || imgLogoColumn;
  }, [logoSquareUrl, logoVertical]);

  const wideWidth = useMemo(() => {
    if (
      typeof wideLogoSrc === 'object' &&
      'width' in wideLogoSrc &&
      wideLogoSrc.width &&
      wideLogoSrc.height
    ) {
      return Math.round((size * wideLogoSrc.width) / wideLogoSrc.height);
    }
    return Math.round(size * (imgLogoRow.width / imgLogoRow.height));
  }, [size, wideLogoSrc]);

  const containerWidth = isRow ? wideWidth : size;

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
        <div
          style={{
            // width: containerWidth,
            height: size,
            position: 'relative',
          }}
        >
          <Image
            src={wideLogoSrc}
            alt='logo'
            width={wideWidth}
            height={size}
            style={{
              width: 'auto',
              height: size,
              position: isRow ? 'relative' : 'absolute',
              top: 0,
              left: 0,
              opacity: isRow ? 1 : 0,
              transition: 'opacity 200ms ease',
            }}
            priority
          />
          <Image
            src={squareLogoSrc}
            alt='logo'
            width={size}
            height={size}
            style={{
              width: size,
              height: size,
              position: !isRow ? 'relative' : 'absolute',
              top: 0,
              left: 0,
              opacity: isRow ? 0 : 1,
              transition: 'opacity 200ms ease',
            }}
            priority
          />
        </div>
      </a>
    </div>
  );
};

export default memo(LogoWithText);
