import { memo } from 'react';
import logoRow from 'Assets/logos/ai-shifu-logo-horizontal.png';
import logoColumn from 'Assets/logos/ai-shifu-logo-vertical.png';

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
      {isRow ? (
        <img src={logoRow} alt="logo" style={{ ...commonStyles }} />
      ) : (
        <img src={logoColumn} alt="logo" style={{ ...commonStyles }} />
      )}
    </div>
  );
};

export default memo(LogoWithText);
