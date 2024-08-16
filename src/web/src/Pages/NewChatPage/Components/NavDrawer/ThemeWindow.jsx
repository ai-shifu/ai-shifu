import PopupModal from 'Components/PopupModal';
import { memo } from 'react';

export const ThemeWindow = ({ open, onClose, style, className }) => {
  return (
    <PopupModal
      open={open}
      onClose={onClose}
      wrapStyle={{ ...style }}
      className={className}
    >
      <div
        style={{
          display: 'flex',
          height: '100px',
          verticalAlign: 'middle',
          justifyContent: 'center',
          alignItems: 'center',
        }}
      >
        敬请期待
      </div>
    </PopupModal>
  );
};

export default memo(ThemeWindow);
