import { useState, memo } from 'react';
import styles from './AvatarSettingModal.module.scss';
import SettingBaseModal from './SettingBaseModal';
import Cropper from 'react-easy-crop';
import { genCroppedImg } from '@/c-utils/imgUtils';

export const AvatarSettingModal = ({
  open,
  onClose,
  image,
  onOk = ({ img }) => {},
  initialValues = {},
}) => {
  const [srcImg] = useState(image);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState(null);

  const onOkClick = async () => {
    if (!croppedAreaPixels) {
      onOk?.({ img: srcImg });
    }

    const img = await genCroppedImg(srcImg, croppedAreaPixels);
    onOk?.({ img });
  };

  const onCropComplete = (_croppedArea, croppedAreaPixels) => {
    setCroppedAreaPixels(croppedAreaPixels);
  };

  return (
    <SettingBaseModal open={open} onClose={onClose} onOk={onOkClick}>
      <div className={styles.avatarSettingModalWrapper}>
        <div className={styles.avatarSettingModal}>
          <Cropper
            image={image}
            crop={crop}
            zoom={zoom}
            aspect={1}
            onCropChange={setCrop}
            onCropComplete={onCropComplete}
            onZoomChange={setZoom}
            style={{ height: '200px', width: '200px;' }}
          />
        </div>
      </div>
    </SettingBaseModal>
  );
};

export default memo(AvatarSettingModal);
