import { memo } from 'react';
import logoBlue from 'Assets/logos/logo-blue-120.png';
import logoColor from 'Assets/logos/logo-color-120.png';
import logoWhite from 'Assets/logos/logo-white-120.png';
import logoTextRow from 'Assets/logos/logo-text-horiz-160.png';
import logoTextColumn from 'Assets/logos/logo-text-verti-160.png';
import logoTextRowWhite from 'Assets/logos/logo-text-horiz-white-160.png';
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

  const commonStyles = {
    width: isRow ? 'auto' : size + 'px',
    height: isRow ? size + 'px' : 'auto',
  };

  const textStyles = {
    width: isRow ? 'auto' : size * 0.8 + 'px',
    height: isRow ? size * 0.8 + 'px' : 'auto',
    marginLeft: isRow ? size * 0.3 + 'px' : '0',
    marginTop: isRow ? '0' : size * 0.3 + 'px',
  };

  const getLogoByColor = (color) => {
    switch (color) {
      case 'color':
        return logoColor;
      case 'white':
        return logoWhite;
      default:
        return logoBlue;
    }
  };

  const getTextRowByColor = (color) => {
    switch (color) {
      case 'white':
        return logoTextRowWhite;
      default:
        return logoTextRow;
    }
  }

  // const { bannerUrl, bannerCollapseUrl } = useSystemStore.getState();
  const { bannerUrl } = useSystemStore(state => state);
  const { bannerCollapseUrl } = useSystemStore(state => state);

  let customBannerUrl = false
  if (bannerCollapseUrl && bannerCollapseUrl!= null && bannerCollapseUrl!== ''
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
      {customBannerUrl && isRow && (
        <img src={bannerUrl} alt="banner" style={{ ...commonStyles }} />
      )}
      {customBannerUrl && !isRow && (
        <img src={bannerCollapseUrl} alt="banner" style={{ ...commonStyles }} />
      )}
      {!customBannerUrl && (
        <>
          <img src={getLogoByColor(color)} alt="logo" style={{ ...commonStyles }} />
          {isRow ? (
            <img src={getTextRowByColor(color)} alt="logotext" style={{ ...textStyles }} />
          ) : (
            <img src={logoTextColumn} alt="logotext" style={{ ...textStyles }} />
          )}
        </>
      )}
    </div>
  );
};

export default memo(LogoWithText);
