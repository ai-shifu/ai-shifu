import styles from './ChatMobileHeader.module.scss';
import IconButton from 'Components/IconButton.jsx';
import MoeIcon from '@Assets/newchat/light/icon16-more2x.png';
import classNames from 'classnames';

export const ChatMobileHeader = (props) => {
  return <div className={classNames(styles.ChatMobileHeader, props.className)}>
    <img alt="" className={styles.logo} src={require('@Assets/logos/logo-hori-84.png')} />
    <IconButton icon={MoeIcon} />
  </div>
}

export default ChatMobileHeader;
