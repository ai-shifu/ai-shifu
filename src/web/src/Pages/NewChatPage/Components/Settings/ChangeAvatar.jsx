import { useState, useRef } from 'react';
import classNames from 'classnames';
import styles from './ChangeAvatar.module.scss';
import { Avatar } from 'antd';
import AvatarSettingModal from './AvatarSettingModal.jsx';
import { convertFileToDataUrl } from '@Utils/imgUtils';
import { useEffect } from 'react';

export const ChangeAvatar = ({
  className,
  image,
  onChange = ({dataUrl}) => {},
}) => {
  const [modalOpen, setModalOpen] = useState(false);
  const uploadRef = useRef(null);
  const [img, setImg] = useState(image);
  const [uploadImage, setUploadedImage] = useState(null);

  const onAvatarClick = () => {
    uploadRef.current.click();

  }; 

  const onAvatarSettingModalOk = async ({ img }) => {
    onChange?.({ dataUrl: img });
    setImg(img);
    setModalOpen(false);
  };

  const onAvatarUploadChange = async (e) => {
    if (e.target.files.length === 0) {
      return;
    }

    const file = e.target.files[0];
    setUploadedImage(await convertFileToDataUrl(file))
    setModalOpen(true);
  };
  return (
    <>
      {(uploadImage && modalOpen) && (
        <AvatarSettingModal
          image={uploadImage}
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          onOk={onAvatarSettingModalOk}
        />
      )}
      <div className={classNames(styles.ChangeAvatar, className)}>
        <div className={styles.avatarContainer} onClick={onAvatarClick}>
          <Avatar size={100} src={img} />
          <input
            type="file"
            className={styles.avatarUpload}
            ref={uploadRef}
            onChange={onAvatarUploadChange}
          />
          <img
            className={styles.editIcon}
            src={require('@Assets/newchat/light/icon-edit-avatar-Normal@2x.png')}
            alt=""
          />
        </div>
      </div>
    </>
  );
};

export default ChangeAvatar;
