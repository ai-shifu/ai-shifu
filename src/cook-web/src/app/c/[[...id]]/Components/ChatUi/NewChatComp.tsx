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
import dynamic from 'next/dynamic';

import useMessages from './ForkChatUI/hooks/useMessages';
import { Chat } from './ForkChatUI/components/Chat';
import { useChatComponentsScroll } from './ChatComponents/useChatComponentsScroll';

// i18n

import {
  runScript,
  getLessonStudyRecord,
  scriptContentOperation,
} from '@/c-api/studyV2';
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
import { STUDY_PREVIEW_MODE } from '@/c-constants/study';
import { StudyRecordItem, LikeStatus } from '@/c-api/studyV2';
import { ContentRender } from 'markdown-flow-ui';
import InteractionBlock from './InteractionBlock';

interface ContentItem {
  content: string;
  customRenderBar: () => null;
  defaultButtonText: string;
  defaultInputText: string;
  readonly: boolean;
  generated_block_bid: string;
  like_status?: LikeStatus; // bussiness logic, not from api
}

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
    const { courseId: shifu_bid } = useEnvStore.getState()

    const [inputModal, setInputModal] = useState(null);
    const [loadedChapterId, setLoadedChapterId] = useState('');
    const [loadedData, setLoadedData] = useState(false);
    const [contentList, setContentList] = useState<ContentItem[]>([]);
    const { mobileStyle } = useContext(AppContext);

    const reduceRecordsToContent = (records: StudyRecordItem[]) => {
       const result: ContentItem[]= [];
       records.forEach((item: StudyRecordItem) => {
        result.push({
          generated_block_bid: item.generated_block_bid,
          content: item.content,
          customRenderBar: () => null,
          defaultButtonText: '',
          defaultInputText: '',
          readonly: false
        } as ContentItem);

        // if like_status is exist, add interaction block
        if(item.like_status){
         result.push({
            generated_block_bid: item.generated_block_bid,
            content: '',
            like_status: item.like_status,
            customRenderBar: () => null,
            defaultButtonText: '',
            defaultInputText: '',
            readonly: false
          })
        };
      });
      return result;
    };

    const refreshData = async () => {
      const recordResp = await getLessonStudyRecord({ 
        shifu_bid,
        outline_bid: chapterId,
      });
      if(recordResp?.records?.length > 0) {
        console.log('获取学习记录', recordResp);
        setLoadedData(true);
        setLoadedChapterId(chapterId);
        const contentRecords: ContentItem[] = reduceRecordsToContent(recordResp.records);
        setContentList(contentRecords);
        console.log('contentList', contentRecords);
      }else{
        console.log('获取学习记录为空，开始run');
      }
    };

    useEffect(() => {
      refreshData();
    }, [chapterId]);

    return (
      <div
        className={cn(
          styles.chatComponents,
          className,
          mobileStyle ? styles.mobile : '',
        )}
      >
        {contentList.map((item, idx) => (item.like_status ? 
            <InteractionBlock
              key={`${item.generated_block_bid}-interaction`}
              shifu_bid={shifu_bid}
              generated_block_bid={item.generated_block_bid}
              like_status={item.like_status}
              readonly={item.readonly}
            />
            :
            <ContentRender
              key={item.generated_block_bid}
              content={item.content}
              customRenderBar={item.customRenderBar}
              defaultButtonText={item.defaultButtonText}
              defaultInputText={item.defaultInputText}
              readonly={item.readonly}
            />
        ))}
        
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
