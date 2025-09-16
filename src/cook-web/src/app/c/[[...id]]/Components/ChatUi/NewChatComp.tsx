import './ForkChatUI/styles/index.scss';
import styles from './ChatComponents.module.scss';

import {
  useEffect,
  forwardRef,
  useImperativeHandle,
  useState,
  useContext,
  useRef,
  memo,
  useCallback,
} from 'react';
import { cn } from '@/lib/utils';

import useMessages from './ForkChatUI/hooks/useMessages';
import { Chat } from './ForkChatUI/components/Chat';
import { useChatComponentsScroll } from './ChatComponents/useChatComponentsScroll';

import { ThumbsUp, ThumbsDown } from 'lucide-react';
// i18n

import {
  runScript,
  getLessonStudyRecord,
  scriptContentOperation,
} from '@/c-api/study';
import { genUuid } from '@/c-utils/common';
import ChatInteractionArea from './ChatInput/ChatInteractionArea';
import { AppContext } from '@/c-components/AppContext';

import { useCourseStore } from '@/c-store/useCourseStore';
import {
  LESSON_STATUS_VALUE,
  INTERACTION_TYPE,
  INTERACTION_OUTPUT_TYPE,
  RESP_EVENT_TYPE,
  CHAT_MESSAGE_TYPE,
} from '@/c-constants/courseConstants';

import { useUserStore } from '@/store';
import { fixMarkdown, fixMarkdownStream } from '@/c-utils/markdownUtils';
import PayModal from '../Pay/PayModal';
// TODO: FIXME
// import LoginModal from '../Login/LoginModal';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';

import { tokenTool } from '@/c-service/storeUtil';
import MarkdownBubble from './ChatMessage/MarkdownBubble';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import PayModalM from '../Pay/PayModalM';
// import { useTranslation } from 'react-i18next';
import { useEnvStore } from '@/c-store/envStore';
import { shifu } from '@/c-service/Shifu';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
} from '@/app/c/[[...id]]/events';
import ActiveMessageControl from './ChatMessage/ActiveMessageControl';
import { convertKeysToCamelCase } from '@/c-utils/objUtils';
import { useShallow } from 'zustand/react/shallow';

import logoColor120 from '@/c-assets/logos/logo-color-120.png';

// TODO: FIXME
export const NewChatComponents = forwardRef<any, any>(
  (
    {
      className,
      lessonUpdate,
      onGoChapter = () => {},
      chapterId,
      lessonId,
      onPurchased,
      chapterUpdate,
      updateSelectedLesson,
    },
    ref,
  ) => {
    // const { t } = useTranslation();
    const { trackEvent, trackTrailProgress } = useTracking();
    const { courseId } = useEnvStore.getState();

    const [inputModal, setInputModal] = useState(null);
    const [loadedChapterId, setLoadedChapterId] = useState('');
    const [loadedData, setLoadedData] = useState(false);
    const { mobileStyle } = useContext(AppContext);

    

    return (
      <div
        className={cn(
          styles.chatComponents,
          className,
          mobileStyle ? styles.mobile : '',
        )}
      >
        chat块
        {inputModal && (
         '互动块'
        )}
        {/* {payModalOpen &&
          (mobileStyle ? (
            <PayModalM
              open={payModalOpen}
              onCancel={_onPayModalClose}
              onOk={onPayModalOk}
              type={''}
              payload={{}}
            />
          ) : (
            <PayModal
              open={payModalOpen}
              onCancel={_onPayModalClose}
              onOk={onPayModalOk}
              type={''}
              payload={{}}
            />
          ))} */}
      </div>
    );
  },
);

NewChatComponents.displayName = 'NewChatComponents';

export default memo(NewChatComponents);
