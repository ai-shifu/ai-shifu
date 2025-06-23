import { memo } from 'react';

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
  const logoHorizontal = useEnvStore((state) => state.logoHorizontal);
  const logoVertical = useEnvStore((state) => state.logoVertical);
  const siteUrl = useEnvStore((state) => state.siteUrl);
  const commonStyles = {
    width: isRow ? 'auto' : size + 'px',
    height: isRow ? size + 'px' : 'auto',
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
          <img src={ logoHorizontal || imgLogoRow.src} alt="logo" style={{ ...commonStyles }} />
        ) : (
          <img src={logoVertical || imgLogoColumn.src} alt="logo" style={{ ...commonStyles }} />
        )}
      </a>
    </div>
  );
};

export default memo(LogoWithText);
