import styles from './ChangeAvatar.module.scss';

import { useState, useRef, memo, useCallback, useEffect } from 'react';
import clsx from 'clsx';

import { Avatar, AvatarImage } from '@/components/ui/avatar';
import AvatarSettingModal from './AvatarSettingModal';
import { convertFileToDataUrl } from '@/c-utils/imgUtils';

import { uploadAvatar } from '@/c-api/user';

import iconEditAvatar2x from '@/c-assets/newchat/light/icon-edit-avatar-Normal@2x.png'

export const ChangeAvatar = ({
  className,
  image,
  onChange = ({ dataUrl }) => {},
}) => {
  const [modalOpen, setModalOpen] = useState(false);
  const uploadRef = useRef(null);
  const [img, setImg] = useState(image);
  const [uploadImage, setUploadedImage] = useState(null);

  useEffect(() => {
    setImg(image);
  }, [image])
  const onAvatarClick = () => {
    uploadRef.current.click();
  };

  const onAvatarSettingModalOk = useCallback(
    async ({ img }) => {
      const { data: imgUrl } = await uploadAvatar({ avatar: img });
      onChange?.({ dataUrl: imgUrl });
      setImg(imgUrl);
      setModalOpen(false);
    },
    [onChange]
  );

  const onAvatarUploadChange = useCallback(async (e) => {
    if (e.target.files.length === 0) {
      return;
    }

    const file = e.target.files[0];
    setUploadedImage(await convertFileToDataUrl(file));
    setModalOpen(true);
  }, []);

  const onAvatarSettingModalClose = useCallback(() => {
    setModalOpen(false);
  }, []);

  return (
    <>
      {uploadImage && modalOpen && (
        <AvatarSettingModal
          image={uploadImage}
          open={modalOpen}
          onClose={onAvatarSettingModalClose}
          onOk={onAvatarSettingModalOk}
        />
      )}
      <div className={clsx(styles.ChangeAvatar, className)}>
        <div className={styles.avatarContainer} onClick={onAvatarClick}>
          <Avatar>
            <AvatarImage src={img} />
          </Avatar>
          <input
            type="file"
            className={styles.avatarUpload}
            ref={uploadRef}
            onChange={onAvatarUploadChange}
            accept='.png,.jpg,.jpeg,.bmp,.webp'
          />
          <img
            className={styles.editIcon}
            src={iconEditAvatar2x.src}
            alt=""
          />
        </div>
      </div>
    </>
  );
};

export default memo(ChangeAvatar);
