import { memo } from 'react';
import logoTextRow from 'Assets/logos/ai-shifu-logo-horizontal.png';
import logoTextColumn from 'Assets/logos/ai-shifu-logo-vertical.png';
import { useSystemStore } from 'stores/useSystemStore';

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

  const { bannerUrl } = useSystemStore(state => state);
  const { collapsedBannerUrl } = useSystemStore(state => state);
  let customBannerUrl = false

  if (collapsedBannerUrl && collapsedBannerUrl!= null && collapsedBannerUrl!== ''
    && bannerUrl && bannerUrl!= null && bannerUrl!== '') {
    customBannerUrl = true;
  }
  return (
    <div
      style={{
        display: 'flex',
        flexFlow: flexFlow,
        alignItems: 'center',
        ...commonStyles,
      }}
    >
      <a href="https://www.ai-shifu.com">
        {customBannerUrl && isRow && (
          <img src={bannerUrl} alt="logotext" style={{ ...commonStyles }} />
        )}
        {customBannerUrl && !isRow && (
          <img src={collapsedBannerUrl} alt="logotext" style={{ ...commonStyles }} />
        )}
        {!customBannerUrl && (
          <>
            {isRow ? (
              <img src={logoTextRow} alt="logotext" style={{ ...commonStyles }} />
            ) : (
              <img src={logoTextColumn} alt="logotext" style={{ ...commonStyles }} />
            )}
          </>
        )}
      </a>
    </div>
  );
};

export default memo(LogoWithText);
