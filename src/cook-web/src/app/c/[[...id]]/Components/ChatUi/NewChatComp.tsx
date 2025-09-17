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
  useMemo,
} from 'react';
import { cn } from '@/lib/utils';
import dynamic from 'next/dynamic';
import { useTranslation } from 'react-i18next';

import useMessages from './ForkChatUI/hooks/useMessages';
import { Chat } from './ForkChatUI/components/Chat';
import { useChatComponentsScroll } from './ChatComponents/useChatComponentsScroll';

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
import { fixMarkdownStream } from '@/c-utils/markdownUtils';
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
import { StudyRecordItem, LikeStatus ,getRunMessage, SSE_INPUT_TYPE, getLessonStudyRecord} from '@/c-api/studyV2';
import { ContentRender, OnSendContentParams } from 'markdown-flow-ui';
import InteractionBlock from './InteractionBlock';
import { LoadingBar } from './LoadingBar';
interface ContentItem {
  content: string;
  customRenderBar?: (() => JSX.Element | null) | React.ComponentType<any>;
  defaultButtonText: string;
  defaultInputText: string;
  readonly: boolean;
  generated_block_bid: string;
  like_status?: LikeStatus; // business logic, not from api
}
interface SSEParams {
  input: string | Record<string, any>;
  input_type: SSE_INPUT_TYPE;
  reload_generated_block_bid?: string;
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
      preview_mode = 'normal',
    },
    ref,
  ) => {
    // const { t } = useTranslation();
    const { trackEvent, trackTrailProgress } = useTracking();
    const { courseId: shifu_bid } = useEnvStore.getState()
    const outline_bid = lessonId || chapterId;

   
 
    const [inputModal, setInputModal] = useState(null);
    const [loadedChapterId, setLoadedChapterId] = useState('');
    const [loadedData, setLoadedData] = useState(false);
    const [contentList, setContentList] = useState<ContentItem[]>([]);
    const { mobileStyle } = useContext(AppContext);
    const [isLoading, setIsLoading] = useState(false);
    const currentContentRef = useRef<string>('');
    const currentBlockIdRef = useRef<string | null>(null);


    useEffect(() => {
      if(!outline_bid){
        return
      }
      refreshData();
    }, [outline_bid]);


    const run = (sseParams: SSEParams) => {
      // Create a placeholder block immediately with a loading bar
      const id = genUuid();
      currentBlockIdRef.current = id;
      currentContentRef.current = '';
      setContentList(prev => [
        ...prev,
        {
          generated_block_bid: id,
          content: '',
          customRenderBar: () => <LoadingBar />,
          defaultButtonText: '',
          defaultInputText: '',
          readonly: false,
        } as ContentItem,
      ]);

      getRunMessage(
        shifu_bid,
        outline_bid,
        preview_mode,
        sseParams,
        async response => {
          try {
            // Stream typing effect
            if (response.type === RESP_EVENT_TYPE.TEXT) {
              // Ensure we have a current block id (create if absent)
              if (!currentBlockIdRef.current) {
                const nid = genUuid();
                currentBlockIdRef.current = nid;
                currentContentRef.current = '';
                setContentList(prev => [
                  ...prev,
                  {
                    generated_block_bid: nid,
                    content: '',
                    customRenderBar: () => <LoadingBar />,
                    defaultButtonText: '',
                    defaultInputText: '',
                    readonly: false,
                  } as ContentItem,
                ]);
              }

              // Update streaming text incrementally
              const prevText = currentContentRef.current || '';
              const delta = fixMarkdownStream(prevText, response.content || '');
              const nextText = prevText + delta;
              currentContentRef.current = nextText;

              const blockId = currentBlockIdRef.current;
              if (blockId) {
                setContentList(prev =>
                  prev.map(item =>
                    item.generated_block_bid === blockId
                      ? { ...item, content: nextText, customRenderBar: () => null }
                      : item,
                  ),
                );
              }
              return;
            }

            if (response.type === RESP_EVENT_TYPE.TEXT_END) {
              const blockId = currentBlockIdRef.current;
              if (blockId) {
                setContentList(prev =>
                  prev.map(item =>
                    item.generated_block_bid === blockId
                      ? { ...item, readonly: true, customRenderBar: () => null }
                      : item,
                  ),
                );
              }
              // Prepare for possible next segment in the same stream
              currentBlockIdRef.current = null;
              currentContentRef.current = '';
              return;
            }
          } catch (e) {
            // eslint-disable-next-line no-console
            console.warn('SSE handling error:', e);
          }
        },
      );
    };

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
        outline_bid,
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
        run({
          input: '',
          input_type: 'normal',
        })
      }
    };


    const onSend = (content: OnSendContentParams) => {
      console.log('onSend', content);
      const { variableName, buttonText, inputText } = content;
      run({
        input: {
          [variableName as string]: buttonText || inputText
        },
        input_type: 'normal',
      })
    };


    return (
      <div
        className={cn(
          styles.chatComponents,
          className,
          mobileStyle ? styles.mobile : '',
        )}
      >
        {contentList.map((item) => (item.like_status ? 
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
              onSend={onSend}
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
