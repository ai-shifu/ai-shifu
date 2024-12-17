import { memo } from 'react';
import logoTextRow from 'Assets/logos/ai-shifu-logo-horizontal.png';
import logoTextColumn from 'Assets/logos/ai-shifu-logo-vertical.png';

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

  const commonStyles = { width: isRow ? 'auto' : size + 'px',
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
              <img src={logoTextRow} alt="logotext" style={{ ...commonStyles }} />
            ) : (
          <img src={logoTextColumn} alt="logotext" style={{ ...commonStyles }} />
        )}
    </div>
  );
};

export default memo(LogoWithText);
