import './ForkChatUI/styles/index.scss';
import 'markdown-flow-ui/dist/markdown-flow-ui.css';
import styles from './ChatComponents.module.scss';
import {
  useEffect,
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
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import useAutoScroll from './useAutoScroll';
import { useUserStore } from '@/store';
import { fixMarkdownStream } from '@/c-utils/markdownUtils';
import PayModal from '../Pay/PayModal';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import PayModalM from '../Pay/PayModalM';
import { useTranslation } from 'react-i18next';
import { toast } from '@/hooks/useToast';
import { useEnvStore } from '@/c-store/envStore';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
} from '@/app/c/[[...id]]/events';
import { useShallow } from 'zustand/react/shallow';
import {
  StudyRecordItem,
  LikeStatus,
  getRunMessage,
  SSE_INPUT_TYPE,
  getLessonStudyRecord,
  PREVIEW_MODE,
  SSE_OUTPUT_TYPE,
  SYS_INTERACTION_TYPE,
  LIKE_STATUS,
} from '@/c-api/studyV2';
import { ContentRender, OnSendContentParams } from 'markdown-flow-ui';
import InteractionBlock from './InteractionBlock';
import { LoadingBar } from './LoadingBar';
interface ContentItem {
  content: string;
  customRenderBar?: (() => JSX.Element | null) | React.ComponentType<any>;
  defaultButtonText: string;
  defaultInputText: string;
  readonly: boolean;
  isHistory?: boolean;
  generated_block_bid: string;
  like_status?: LikeStatus; // business logic, not from api
}
interface SSEParams {
  input: string | Record<string, any>;
  input_type: SSE_INPUT_TYPE;
  reload_generated_block_bid?: string;
}

export const NewChatComponents = ({
  className,
  lessonUpdate,
  onGoChapter,
  chapterId,
  lessonId,
  onPurchased,
  chapterUpdate,
  updateSelectedLesson,
  preview_mode = PREVIEW_MODE.NORMAL,
}) => {
  const { trackEvent, trackTrailProgress } = useTracking();
  const { t } = useTranslation();
  const showOutputInProgressToast = useCallback(() => {
    toast({
      title: t('chat.outputInProgress'),
    });
  }, [t]);
  const { courseId: shifu_bid } = useEnvStore.getState();
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

  const outline_bid = lessonId;
  const [isTypeFinished, setIsTypeFinished] = useState(false);

  const [loadedChapterId, setLoadedChapterId] = useState('');
  const [loadedData, setLoadedData] = useState(false);
  const [contentList, setContentList] = useState<ContentItem[]>([]);
  const contentListRef = useRef<ContentItem[]>([]);
  const { mobileStyle } = useContext(AppContext);
  const [isLoading, setIsLoading] = useState(true);
  const currentContentRef = useRef<string>('');
  const currentBlockIdRef = useRef<string | null>(null);
  const runRef = useRef<((params: SSEParams) => void) | null>(null);
  const chatRef = useRef(null);
  const { scrollToLesson } = useChatComponentsScroll({
    chatRef,
    containerStyle: styles.chatComponents,
    // HACK: messages is not used in NewChatComp
    messages: [],
    appendMsg: () => {},
    deleteMsg: () => {},
  });

  const [lastInteractionBlock, setLastInteractionBlock] =
    useState<ContentItem | null>(null);
  const {
    open: payModalOpen,
    onOpen: onPayModalOpen,
    onClose: onPayModalClose,
  } = useDisclosure();

  const onPayModalOk = () => {
    onPurchased?.();
    refreshUserInfo();
  };

  const { scrollToBottom } = useAutoScroll(chatRef as any, {
    bottomSelector: '#chat-box-bottom',
    threshold: 120,
  });

  // when get type: LESSON_UPDATE, update lesson info
  const lessonUpdateResp = useCallback(
    (response, isEnd) => {
      const {
        outline_bid: currentOutlineBid,
        status,
        title,
      } = response.content;
      lessonUpdate?.({
        id: currentOutlineBid,
        name: title,
        status: status,
        status_value: status,
      });
      if (status === LESSON_STATUS_VALUE.PREPARE_LEARNING && !isEnd) {
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
  const run = useCallback(
    (sseParams: SSEParams) => {
      setIsTypeFinished(false);
      // Create a placeholder block immediately with a loading bar
      const id = genUuid();
      currentBlockIdRef.current = id;
      currentContentRef.current = '';
      setLastInteractionBlock(null);
      setContentList(prev => {
        const newList = [
          ...prev,
          {
            generated_block_bid: id,
            content: '',
            customRenderBar: () => <LoadingBar />,
            defaultButtonText: '',
            defaultInputText: '',
            readonly: false,
          } as ContentItem,
        ];
        contentListRef.current = newList;
        return newList;
      });

      let isEnd = false;
      getRunMessage(
        shifu_bid,
        outline_bid,
        preview_mode,
        sseParams,
        async response => {
          try {
            const nid = response.generated_block_bid;
            // Stream typing effect
            if ([SSE_OUTPUT_TYPE.BREAK].includes(response.type)) {
              trackTrailProgress(nid);
            }

            if (response.type === SSE_OUTPUT_TYPE.INTERACTION) {
              // let interaction block show after typewriter end
              setLastInteractionBlock({
                generated_block_bid: currentBlockIdRef.current || '',
                content: response.content,
                customRenderBar: () => null,
                defaultButtonText: '',
                defaultInputText: '',
                readonly: false,
              });
            } else if (response.type === SSE_OUTPUT_TYPE.CONTENT) {
              if (isEnd) {
                return;
              }

              // Update streaming text incrementally
              const prevText = currentContentRef.current || '';
              const delta = fixMarkdownStream(prevText, response.content || '');
              const nextText = prevText + delta;
              currentContentRef.current = nextText;

              const blockId = currentBlockIdRef.current;
              if (blockId) {
                setContentList(prev => {
                  const updatedList = prev.map(item =>
                    item.generated_block_bid === blockId
                      ? {
                          ...item,
                          content: nextText,
                          customRenderBar: () => null,
                        }
                      : item,
                  );
                  contentListRef.current = updatedList;
                  return updatedList;
                });
              }
            } else if (response.type === SSE_OUTPUT_TYPE.OUTLINE_ITEM_UPDATE) {
              if (response.content.have_children) {
                // is chapter
                const { status, outline_bid: chapterId } = response.content;
                // HACK: chapterUpdate NEED status_value!
                chapterUpdate?.({
                  id: chapterId,
                  status,
                  status_value: status,
                });
                if (status === LESSON_STATUS_VALUE.COMPLETED) {
                  isEnd = true;
                }
              } else {
                // is lesson
                lessonUpdateResp(response, isEnd);
              }
            } else if (response.type === SSE_OUTPUT_TYPE.BREAK) {
              const blockId = currentBlockIdRef.current;
              if (blockId) {
                setContentList(prev => {
                  const updatedList = prev.map(item =>
                    item.generated_block_bid === blockId
                      ? { ...item, readonly: true, customRenderBar: () => null }
                      : item,
                  );
                  contentListRef.current = updatedList;
                  return updatedList;
                });
              }
              // Prepare for possible next segment in the same stream
              currentBlockIdRef.current = null;
              currentContentRef.current = '';
            } else if (response.type === SSE_OUTPUT_TYPE.PROFILE_UPDATE) {
              updateUserInfo({
                [response.content.key]: response.content.value,
              });
            }
          } catch (e) {
            // eslint-disable-next-line no-console
            console.warn('SSE handling error:', e);
          }
        },
      );
    },
    [
      chapterUpdate,
      lessonUpdateResp,
      outline_bid,
      preview_mode,
      shifu_bid,
      trackTrailProgress,
      updateUserInfo,
    ],
  );

  useEffect(() => {
    runRef.current = run;
  }, [run]);

  //  map mdf learn records to content & separate interaction block (like_status is exist)
  const reduceRecordsToContent = useCallback((records: StudyRecordItem[]) => {
    const result: ContentItem[] = [];
    records.forEach((item: StudyRecordItem) => {
      result.push({
        generated_block_bid: item.generated_block_bid,
        content: item.content,
        customRenderBar: () => null,
        defaultButtonText: item.user_input || '',
        defaultInputText: item.user_input || '',
        readonly: false,
        isHistory: true,
      } as ContentItem);
      // if like_status is exist, add interaction block
      if (item.like_status) {
        result.push({
          generated_block_bid: item.generated_block_bid,
          content: '',
          like_status: item.like_status,
          customRenderBar: () => null,
          defaultButtonText: '',
          defaultInputText: '',
          readonly: false,
        });
      }
    });
    return result;
  }, []);

  // page init or chapter/lesson change
  const refreshData = useCallback(async () => {
    setContentList(() => {
      contentListRef.current = [];
      return [];
    });
    setIsLoading(true);
    const recordResp = await getLessonStudyRecord({
      shifu_bid,
      outline_bid,
    });
    if (recordResp?.records?.length > 0) {
      setLoadedData(true);
      setLoadedChapterId(chapterId);
      const contentRecords: ContentItem[] = reduceRecordsToContent(
        recordResp.records,
      );
      setContentList(() => {
        contentListRef.current = contentRecords;
        return contentRecords;
      });
      setIsTypeFinished(true);
      scrollToBottom('smooth');
    } else {
      runRef.current?.({
        input: '',
        input_type: 'normal',
      });
    }
    setIsLoading(false);
  }, [
    chapterId,
    outline_bid,
    reduceRecordsToContent,
    lessonId,
    shifu_bid,
    scrollToBottom,
  ]);

  // user choose chapter should refresh data
  useEffect(() => {
    if (!chapterId) {
      return;
    }
    if (loadedChapterId === chapterId) {
      return;
    }

    setLoadedChapterId(chapterId);
    // refreshData();
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

  const updateContentListWithUserOperate = useCallback(
    (
      params: OnSendContentParams,
    ): { newList: ContentItem[]; needChangeItemIndex: number } => {
      const newList = [...contentList];
      const needChangeItemIndex = newList.findIndex(item =>
        item.content.includes(params.variableName || ''),
      );
      if (needChangeItemIndex !== -1) {
        newList[needChangeItemIndex] = {
          ...newList[needChangeItemIndex],
          readonly: false, // anytime can click or input
          defaultButtonText: params.buttonText || '',
          defaultInputText: params.inputText || '',
        };
      }
      // remove the item after the needChangeItemIndex
      newList.length = needChangeItemIndex + 1;

      setContentList(() => {
        contentListRef.current = newList;
        return newList;
      });

      return { newList, needChangeItemIndex };
    },
    [contentList],
  );

  const onRefresh = useCallback(
    (generated_block_bid: string) => {
      if (!isTypeFinished) {
        showOutputInProgressToast();
        return;
      }

      const currentList = contentListRef.current;
      const newList = [...currentList];
      const needChangeItemIndex = newList.findIndex(
        item => item.generated_block_bid === generated_block_bid,
      );
      // delete the item after the needChangeItemIndex, include the needChangeItemIndex
      newList.length = needChangeItemIndex;

      setContentList(() => {
        contentListRef.current = newList;
        return newList;
      });

      setIsTypeFinished(false);
      // refresh the item
      run({
        input: '',
        input_type: SSE_INPUT_TYPE.NORMAL,
        reload_generated_block_bid: generated_block_bid,
      });
    },
    [isTypeFinished, run, showOutputInProgressToast],
  );

  // user choose interaction in chat
  const onSend = useCallback(
    (content: OnSendContentParams) => {
      if (!isTypeFinished) {
        showOutputInProgressToast();
        return;
      }
      // console.log('onSend', content);
      const { variableName, buttonText, inputText } = content;
      if (buttonText === SYS_INTERACTION_TYPE.PAY) {
        trackEvent(EVENT_NAMES.POP_PAY, { from: 'show-btn' });
        onPayModalOpen();
        return;
      }
      if (buttonText === SYS_INTERACTION_TYPE.LOGIN) {
        // redirect to login page
        window.location.href = `/login?redirect=${encodeURIComponent(location.pathname)}`;
        return;
      }

      const { newList, needChangeItemIndex } =
        updateContentListWithUserOperate(content);

      // if(buttonText === SYS_INTERACTION_TYPE.NEXT_CHAPTER){
      //   const nextOutlineBid = (variableName || inputText || '').trim();
      //   if(nextOutlineBid && nextOutlineBid !== outline_bid){
      //     onGoChapter?.(nextOutlineBid);
      //   }
      //   return;
      // }

      setIsTypeFinished(false);
      scrollToBottom();
      run({
        input: {
          [variableName as string]: buttonText || inputText,
        },
        input_type: SSE_INPUT_TYPE.NORMAL,
        reload_generated_block_bid:
          needChangeItemIndex !== -1
            ? newList[needChangeItemIndex].generated_block_bid
            : undefined, // for reload
      });
    },
    [
      updateContentListWithUserOperate,
      trackEvent,
      onPayModalOpen,
      scrollToBottom,
      run,
      isTypeFinished,
      showOutputInProgressToast,
    ],
  );

  // lessonId 在上层有两种，分别用到useCourseStore和useLessonTree...在点击侧边栏时，会有问题，临时FIX
  useEffect(() => {
    if (!lessonId) {
      return;
    }
    refreshData();
  }, [lessonId]);

  // event listener: select lesson in course catalog
  useEffect(() => {
    const onGoToNavigationNode = e => {
      const { chapterId, lessonId: newLessonId } = e.detail;
      if (chapterId !== loadedChapterId) {
        return;
      }
      // FIX: when go to navigation node, set isTypeFinished to true to avoid repeated generation of interaction block
      setIsTypeFinished(true);
      setLastInteractionBlock(null);
      scrollToLesson(newLessonId);
      updateSelectedLesson(newLessonId);
      // refreshData()
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

  const getAdaptedContentList = () => {
    return contentList.map(item => ({
      ...item,
      content: item.content,
      customRenderBar: item.customRenderBar || (() => null),
      defaultButtonText: item.defaultButtonText,
      defaultInputText: item.defaultInputText,
      readonly: item.readonly,
    }));
  };

  // when typewriter finished, add interaction block
  const onTypeFinished = () => {
    if (lastInteractionBlock) {
      const gid = contentList[contentList.length - 1].generated_block_bid;
      const newInteractionBlock = [
        {
          generated_block_bid: gid,
          content: '',
          like_status: LIKE_STATUS.NONE,
          customRenderBar: () => null,
          defaultButtonText: '',
          defaultInputText: '',
          readonly: false,
        },
        lastInteractionBlock,
      ];
      setContentList(p => [...p, ...newInteractionBlock] as ContentItem[]);
      setLastInteractionBlock(null);
    }
    setIsTypeFinished(true);
  };

  return (
    <div
      className={cn(
        styles.chatComponents,
        className,
        mobileStyle ? styles.mobile : '',
      )}
      ref={chatRef}
    >
      {isLoading ? (
        <></>
      ) : (
        getAdaptedContentList().map((item, idx) =>
          item.like_status ? (
            <InteractionBlock
              key={`${item.generated_block_bid}-interaction`}
              shifu_bid={shifu_bid}
              generated_block_bid={item.generated_block_bid}
              like_status={item.like_status}
              readonly={item.readonly}
              onRefresh={onRefresh}
            />
          ) : (
            <ContentRender
              key={idx}
              typingSpeed={60}
              enableTypewriter={!item.isHistory}
              content={item.content}
              customRenderBar={item.customRenderBar}
              defaultButtonText={item.defaultButtonText}
              defaultInputText={item.defaultInputText}
              readonly={item.readonly}
              onSend={onSend}
              onTypeFinished={onTypeFinished}
            />
          ),
        )
      )}
      <div id='chat-box-bottom'></div>
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
};

NewChatComponents.displayName = 'NewChatComponents';

export default memo(NewChatComponents);
