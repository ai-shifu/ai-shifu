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
  const logoHorizontal = useEnvStore((state) => state.logoHorizontal);
  const logoVertical = useEnvStore((state) => state.logoVertical);
  const siteUrl = useEnvStore((state) => state.siteUrl);
  const width = isRow ? size * 3.8125 : size;
  const height = isRow ? size : size * 2.5;
  const commonStyles = {
    width: width + 'px',
    height: height + 'px',
  };

  return (
    <div
      style={{
        display: 'flex',
        flexFlow: flexFlow,
        alignItems: 'center',
        ...commonStyles,
      }}
    >
      <a href={siteUrl}>
        {isRow ? (
          <Image src={ logoHorizontal || imgLogoRow.src} alt="logo" width={width} height={height} style={{ ...commonStyles }} />
        ) : (
          <Image src={logoVertical || imgLogoColumn.src} alt="logo" width={width} height={height} style={{ ...commonStyles }} />
        )}
      </a>
    </div>
  );
};

export default memo(LogoWithText);
