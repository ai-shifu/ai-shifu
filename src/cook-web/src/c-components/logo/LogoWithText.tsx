import { memo } from 'react';

import { useEnvStore } from '@/c-store/envStore';

import Image from 'next/image';
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
  const width = isRow ? size * 3.8125 : size;
  const height = isRow ? size : size * 2.5;
  const logoSrc = isRow
    ? logoUrl || logoHorizontal || imgLogoRow.src
    : logoVertical || imgLogoColumn.src;

  return (
    <div
      style={{
        display: 'flex',
        flexFlow: flexFlow,
        alignItems: 'center',
        // ...commonStyles,
      }}
    >
      <a href={homeUrl || 'https://ai-shifu.cn/'}>
        <Image
          src={logoSrc}
          alt='logo'
          width={Math.round(width)}
          height={Math.round(height)}
          style={{
            width,
            height: isRow ? height : 34,
            objectFit: 'contain',
          }}
        />
      </a>
    </div>
  );
};

export default memo(LogoWithText);
