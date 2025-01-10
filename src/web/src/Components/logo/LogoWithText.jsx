import { memo } from 'react';
import logoRow from 'Assets/logos/ai-shifu-logo-horizontal.png';
import logoColumn from 'Assets/logos/ai-shifu-logo-vertical.png';
import { useEnvStore } from 'stores/envStore.js';
// import squareLogo from 'Assets/logos/ai-shifu-logo-square.png';

/**
 *
 * @param {direction} 'row' | 'col'
 * @param {size} number
 * @param { color } 'blue' | 'color' | 'white'
 * @returns
 */
export const LogoWithText = ({ direction, size = 64, color = 'blue' }) => {
  const isRow = direction === 'row';
  const flexFlow = isRow ? 'row nowrap' : 'column nowrap';
  const logoHorizontal = useEnvStore((state) => state.logoHorizontal);
  const logoVertical = useEnvStore((state) => state.logoVertical);
  console.log(logoHorizontal, logoVertical);
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
      <a href="https://ai-shifu.com">
        {isRow ? (
          <img src={ logoHorizontal || logoRow} alt="logo" style={{ ...commonStyles }} />
        ) : (
          <img src={logoVertical || logoColumn} alt="logo" style={{ ...commonStyles }} />
        )}
      </a>
    </div>
  );
};

export default memo(LogoWithText);
