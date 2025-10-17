import React from 'react';
import clsx from 'clsx';
import { SystemMessage } from './SystemMessage';
import { IMessageStatus } from '../MessageStatus';
import { Avatar } from '../Avatar';
import { Time } from '../Time';
import { Typing } from '../Typing';

export interface User {
  avatar?: string;
  name?: string;
  url?: string;
  [k: string]: any;
}

export type MessageId = string | number;

export interface MessageProps {
  /**
   * Unique ID
   */
  _id: MessageId;
  /**
   * Message type
   */
  type: string;
  /**
   * Message content
   */
  content?: any;
  /**
   * Message creation time
   */
  createdAt?: number;
  /**
   * Message sender info
   */
  user?: User;
  /**
   * Message position
   */
  position?: 'left' | 'right' | 'center' | 'pop';
  /**
   * Whether to show the timestamp
   */
  hasTime?: boolean;
  /**
   * Status
   */
  status?: IMessageStatus;
  /**
   * Renderer for message content
   */
  renderMessageContent?: (message: MessageProps) => React.ReactNode;
}

const Message = (props: MessageProps) => {
  const { renderMessageContent = () => null, ...msg } = props;
  const {
    type,
    content,
    user = {},
    _id: id,
    position = 'left',
    hasTime = true,
    createdAt,
  } = msg;
  const { name, avatar } = user;

  if (type === 'system') {
    return (
      <SystemMessage
        content={content.text}
        action={content.action}
      />
    );
  }

  const isRL = position === 'right' || position === 'left';

  return (
    <div
      className={clsx('Message', position)}
      data-id={id}
      data-type={type}
    >
      {hasTime && createdAt && (
        <div className='Message-meta'>
          <Time date={createdAt} />
        </div>
      )}
      <div className='Message-main'>
        {isRL && avatar && (
          <Avatar
            src={avatar}
            alt={name}
            url={user.url}
          />
        )}
        <div className='Message-inner'>
          {isRL && name && <div className='Message-author'>{name}</div>}
          <div
            className='Message-content'
            role='alert'
            aria-live='assertive'
            aria-atomic='false'
          >
            {type === 'typing' ? <Typing /> : renderMessageContent(msg)}
          </div>
        </div>
      </div>
    </div>
  );
};

export default React.memo(Message);
