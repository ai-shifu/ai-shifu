import styles from './ChatMobileHeader.module.scss';
import IconButton from 'Components/IconButton.jsx';
import MoeIcon from 'Assets/newchat/light/icon16-more2x.png';
import classNames from 'classnames';
import { memo } from 'react';
import LogoWithText from 'Components/logo/LogoWithText.jsx';

export const ChatMobileHeader = (props) => {
  return <div className={classNames(styles.ChatMobileHeader, props.className)}>
    <LogoWithText direction="row" size={30} />
    <IconButton icon={MoeIcon} />
  </div>
}

export default memo(ChatMobileHeader);
