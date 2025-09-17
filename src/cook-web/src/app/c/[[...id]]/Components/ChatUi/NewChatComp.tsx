import './ForkChatUI/styles/index.scss';
import styles from './ChatComponents.module.scss';
import {
  useEffect,
  forwardRef,
  useState,
  useContext,
  useRef,
  memo,
  useCallback,
} from 'react';
import { cn } from '@/lib/utils';
import { useChatComponentsScroll } from './ChatComponents/useChatComponentsScroll';

import { genUuid } from '@/c-utils/common';
import { AppContext } from '@/c-components/AppContext';

import { useCourseStore } from '@/c-store/useCourseStore';
import {
  LESSON_STATUS_VALUE,
} from '@/c-constants/courseConstants';

import { useUserStore } from '@/store';
import { fixMarkdownStream } from '@/c-utils/markdownUtils';
import PayModal from '../Pay/PayModal';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import PayModalM from '../Pay/PayModalM';
// import { useTranslation } from 'react-i18next';
import { useEnvStore } from '@/c-store/envStore';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
} from '@/app/c/[[...id]]/events';
import { useShallow } from 'zustand/react/shallow';
import { StudyRecordItem, LikeStatus ,getRunMessage, SSE_INPUT_TYPE, getLessonStudyRecord, PREVIEW_MODE, SSE_OUTPUT_TYPE, SYS_INTERACTION_TYPE} from '@/c-api/studyV2';
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

export const NewChatComponents = (
    {
      className,
      lessonUpdate,
      onGoChapter,
      chapterId,
      lessonId,
      onPurchased,
      chapterUpdate,
      updateSelectedLesson,
      preview_mode = PREVIEW_MODE.NORMAL,
    },
  ) => {
    // const { t } = useTranslation();
    const { trackEvent, trackTrailProgress } = useTracking();
    const { courseId: shifu_bid } = useEnvStore.getState()
    const { updateUserInfo, refreshUserInfo } = useUserStore(
      useShallow(state => ({
        updateUserInfo: state.updateUserInfo,
        refreshUserInfo: state.refreshUserInfo,
      })),
    );
    const { updateResetedChapterId } = useCourseStore(
      useShallow(state => ({
        updateResetedChapterId: state.updateResetedChapterId,
      })),
    );

    const outline_bid = lessonId || chapterId;
 
    const [loadedChapterId, setLoadedChapterId] = useState('');
    const [loadedData, setLoadedData] = useState(false);
    const [contentList, setContentList] = useState<ContentItem[]>([]);
    const { mobileStyle } = useContext(AppContext);
    const [isLoading, setIsLoading] = useState(false);
    const currentContentRef = useRef<string>('');
    const currentBlockIdRef = useRef<string | null>(null);
    const runRef = useRef<((params: SSEParams) => void) | null>(null);
    const chatRef = useRef(null);
    const {
      scrollToLesson,
      scrollToBottom,
    } = useChatComponentsScroll({
      chatRef,
      containerStyle: styles.chatComponents,
      // HACK: messages is not used in NewChatComp
      messages : [],
      appendMsg: () => {}, 
      deleteMsg: () => {},
    });


    const {
      open: payModalOpen,
      onOpen: onPayModalOpen,
      onClose: onPayModalClose,
    } = useDisclosure();


    const onPayModalOk = () => {
      onPurchased?.();
      refreshUserInfo();
    }

  
    // when get type: LESSON_UPDATE, update lesson info
    const lessonUpdateResp = useCallback(
      (response, isEnd) => {
        const {outline_bid: currentOutlineBid, status,title} = response.content;
        lessonUpdate?.({
          id: currentOutlineBid,
          name: title,
          status: status,
          status_value: status,
        });
        if (
          status === LESSON_STATUS_VALUE.PREPARE_LEARNING &&
          !isEnd
        ) {
          runRef.current?.({
            input: '',
            input_type: SSE_INPUT_TYPE.NORMAL,
          });
        }

        if (status === LESSON_STATUS_VALUE.LEARNING && !isEnd) {
          updateSelectedLesson(currentOutlineBid);
        }
      },
      [lessonUpdate, updateSelectedLesson],
    );

    // get sse message
    const run = useCallback((sseParams: SSEParams) => {
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

      let isEnd = false;
      getRunMessage(
        shifu_bid,
        outline_bid,
        preview_mode,
        sseParams,
        async response => {
          try {
            // TODO: MOCK 
            const nid = response.script_id || response.generated_block_bid;
            // Stream typing effect
            if (
              [
                SSE_OUTPUT_TYPE.CONTENT,
                SSE_OUTPUT_TYPE.BREAK,
                SSE_OUTPUT_TYPE.INTERACTION
              ].includes(response.type)
            ) {
              trackTrailProgress(nid);
            }
            if (response.type === SSE_OUTPUT_TYPE.CONTENT) {
              if (isEnd) {
                return;
              }
              // Ensure we have a current block id (create if absent)
              if (!currentBlockIdRef.current) {
           
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
            }
            else if (response.type === SSE_OUTPUT_TYPE.OUTLINE_ITEM_UPDATE) {
              if(response.content.have_children) {
                // is chapter
                const {
                  status,
                  outline_bid: chapterId,
                } = response.content;
                // HACK: chapterUpdate NEED status_value!
                chapterUpdate?.({ id: chapterId, status, status_value: status });
                if (status === LESSON_STATUS_VALUE.COMPLETED) {
                  isEnd = true;
                }
              }else{
                // is lesson
                lessonUpdateResp(response, isEnd);
              }
            }else if (response.type === SSE_OUTPUT_TYPE.BREAK) {
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
            }else if (response.type === SSE_OUTPUT_TYPE.PROFILE_UPDATE) {
              updateUserInfo({ [response.content.key]: response.content.value });
            }
          } catch (e) {
            // eslint-disable-next-line no-console
            console.warn('SSE handling error:', e);
          }
        },
      );
    }, [
      chapterUpdate,
      lessonUpdateResp,
      outline_bid,
      preview_mode,
      shifu_bid,
      trackTrailProgress,
    ]);

    useEffect(() => {
      runRef.current = run;
    }, [run]);


    //  map mdf learn records to content & separate interaction block (like_status is exist)
    const reduceRecordsToContent = useCallback((records: StudyRecordItem[]) => {
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
    }, []);

    // page init or chapter/lesson change 
    const refreshData = useCallback(async () => {
      setContentList([]);
      console.log('refreshData=====', outline_bid);
      const recordResp = await getLessonStudyRecord({ 
        shifu_bid,
        outline_bid,
      });
      if(recordResp?.records?.length > 0) {
        setLoadedData(true);
        setLoadedChapterId(chapterId);
        const contentRecords: ContentItem[] = reduceRecordsToContent(recordResp.records);
        setContentList(contentRecords);
      }else{
        runRef.current?.({
          input: '',
          input_type: 'normal',
        });
      }
    }, [chapterId, outline_bid, reduceRecordsToContent, shifu_bid]);

    // user choose chapter should refresh data
    useEffect(() => {
      if (!chapterId) {
        return;
      }
      if (loadedChapterId === chapterId) {
        return;
      }

      setLoadedChapterId(chapterId);
      refreshData();
    }, [chapterId, loadedChapterId, refreshData]);

    // user reset chapter
    useEffect(() => {
      const unsubscribe = useCourseStore.subscribe(
        state => state.resetedChapterId,
        curr => {
          if (!curr) {
            return;
          }

          if (curr === loadedChapterId) {
            refreshData();
            // @ts-expect-error EXPECT
            updateResetedChapterId(null);
          }
        },
      );

      return () => {
        unsubscribe();
      };
    }, [loadedChapterId, refreshData, updateResetedChapterId]);

    // user login success
    useEffect(() => {
      const unsubscribe = useUserStore.subscribe(
        state => state.isLoggedIn,
        () => {
          if (!chapterId) {
            return;
          }

          setLoadedChapterId(chapterId);
          refreshData();
        },
      );

      return () => {
        unsubscribe();
      };
    }, [chapterId, refreshData]);


    // user choose interaction in chat
    const onSend = (content: OnSendContentParams) => {
      console.log('onSend', content);
      const { variableName, buttonText, inputText } = content;
      if(buttonText === SYS_INTERACTION_TYPE.PAY){
        trackEvent(EVENT_NAMES.POP_PAY, { from: 'show-btn' });
        onPayModalOpen();
        return;
      }
      if(buttonText === SYS_INTERACTION_TYPE.LOGIN){
        // redirect to login page
        window.location.href = `/login?redirect=${encodeURIComponent(location.pathname)}`;
        return;
      }
      if(buttonText === SYS_INTERACTION_TYPE.NEXT_CHAPTER){
        const nextOutlineBid = (variableName || inputText || '').trim();
        if(nextOutlineBid && nextOutlineBid !== outline_bid){
          onGoChapter?.(nextOutlineBid);
        }
        return;
      }
      scrollToBottom();
      run({
        input: {
          [variableName as string]: buttonText || inputText
        },
        input_type: SSE_INPUT_TYPE.NORMAL,
      })
    };

    // event listener: select lesson in course catalog
    useEffect(() => {
      const onGoToNavigationNode = e => {
        const { chapterId, lessonId } = e.detail;
        if (chapterId !== loadedChapterId) {
          return;
        }
        scrollToLesson(lessonId);
        updateSelectedLesson(lessonId);
        refreshData()
      };

      events.addEventListener(
        BZ_EVENT_NAMES.GO_TO_NAVIGATION_NODE,
        onGoToNavigationNode,
      );

      return () => {
        events.removeEventListener(
          BZ_EVENT_NAMES.GO_TO_NAVIGATION_NODE,
          onGoToNavigationNode,
        );
      };
    }, [loadedChapterId, scrollToLesson, updateSelectedLesson, refreshData]);


    return (
      <div
        className={cn(
          styles.chatComponents,
          className,
          mobileStyle ? styles.mobile : '',
        )}
        ref={chatRef}
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
        
        {payModalOpen &&
          (mobileStyle ? (
            <PayModalM
              open={payModalOpen}
              onCancel={onPayModalClose}
              onOk={onPayModalOk}
              type={''}
              payload={{}}
            />
          ) : (
            <PayModal
              open={payModalOpen}
              onCancel={onPayModalClose}
              onOk={onPayModalOk}
              type={''}
              payload={{}}
            />
          ))}
      </div>
    );
}


NewChatComponents.displayName = 'NewChatComponents';

export default memo(NewChatComponents);
