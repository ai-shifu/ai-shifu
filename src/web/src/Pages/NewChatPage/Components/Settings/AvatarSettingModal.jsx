import { useRef, useState } from 'react';
import styles from './AvatarSettingModal.module.scss';
import SettingBaseModal from './SettingBaseModal.jsx';
import Cropper from 'react-easy-crop';
import { genCroppedImg } from '@Utils/imgUtils';

export const AvatarSettingModal = ({
  open,
  onClose,
  image,
  onOk = ({ img }) => {},
  initialValues = {},
}) => {
  const [srcImg, setSrcImg] = useState(image);
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

  const onCropComplete = (croppedArea, croppedAreaPixels) => {
    setCroppedAreaPixels(croppedAreaPixels);
  };

  return (
    <SettingBaseModal
      className={styles.AvatarSettingModal}
      open={open}
      onClose={onClose}
      onOk={onOkClick}
    >
      <div className={styles.AvatarSettingModal} >
        <Cropper
          image={image}
          crop={crop}
          zoom={zoom}
          onCropChange={setCrop}
          onCropComplete={onCropComplete}
          onZoomChange={setZoom}
          style={{ height: '200px', width: '200px;' }}
        />
      </div>
    </SettingBaseModal>
  );
};

export default AvatarSettingModal;
