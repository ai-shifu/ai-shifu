import '@chatui/core/dist/index.css';
import Chat, { useMessages } from '@chatui/core';
import {
  useEffect,
  forwardRef,
  useImperativeHandle,
  useState,
  useContext,
} from 'react';
import { runScript, getLessonStudyRecord } from 'Api/study';
import { genUuid } from 'Utils/common.js';
import ChatInteractionArea from './ChatInput/ChatInteractionArea.jsx';
import { AppContext } from 'Components/AppContext.js';
import styles from './ChatComponents.module.scss';
import { useCourseStore } from 'stores/useCourseStore.js';
import {
  LESSON_STATUS,
  INTERACTION_TYPE,
  INTERACTION_OUTPUT_TYPE,
  RESP_EVENT_TYPE,
  CHAT_MESSAGE_TYPE,
} from 'constants/courseConstants.js';
import classNames from 'classnames';
import { useUserStore } from 'stores/useUserStore.js';
import { fixMarkdown, fixMarkdownStream } from 'Utils/markdownUtils.js';
import { FRAME_LAYOUT_MOBILE } from 'constants/uiConstants.js';
import ChatMobileHeader from './ChatMobileHeader.jsx';
import PayModal from '../Pay/PayModal.jsx';
import { useDisclosture } from 'common/hooks/useDisclosture.js';
import { memo } from 'react';
import { useCallback } from 'react';
import { tokenTool } from '@Service/storeUtil.js';
import MarkdownBubble from './ChatMessage/MarkdownBubble.jsx';
import { useTracking, EVENT_NAMES } from 'common/hooks/useTracking.js';


const USER_ROLE = {
  TEACHER: '老师',
  STUDENT: '学生',
};

const robotAvatar = require('@Assets/chat/sunner_icon.jpg');

const createMessage = ({
  id = 0,
  role,
  content,
  type = CHAT_MESSAGE_TYPE.TEXT,
  userInfo,
}) => {
  const mid = id || genUuid();
  if (type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
    return {
      _id: mid,
      id: mid,
      type: CHAT_MESSAGE_TYPE.LESSON_SEPARATOR,
      content: content,
    };
  }
  const position = role === USER_ROLE.STUDENT ? 'right' : 'left';

  let avatar = robotAvatar;

  if (role === USER_ROLE.STUDENT) {
    avatar = null;
  }
  return {
    _id: mid,
    id: mid,
    role,
    content,
    type,
    position,
    user: { avatar },
  };
};

const convertMessage = (serverMessage, userInfo) => {
  if (serverMessage.script_type === CHAT_MESSAGE_TYPE.TEXT) {
    return createMessage({
      id: serverMessage.id,
      role: serverMessage.script_role,
      content: fixMarkdown(serverMessage.script_content),
      type: serverMessage.script_type,
      userInfo,
    });
  } else if (serverMessage.script_type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
    return createMessage({
      id: serverMessage.id,
      role: serverMessage.script_role,
      content: { lessonId: serverMessage.lesson_id },
      type: serverMessage.script_type,
      userInfo,
    });
  }

  return {};
};

const convertEventInputModal = ({ type, content }) => {
  if (type === RESP_EVENT_TYPE.PHONE || type === RESP_EVENT_TYPE.CHECKCODE) {
    return {
      type,
      props: { content },
    };
  } else if (type === RESP_EVENT_TYPE.INPUT) {
    return {
      type,
      props: { content },
    };
  } else if (type === RESP_EVENT_TYPE.BUTTONS || type === RESP_EVENT_TYPE.ORDER) {
    const getBtnType = (type) => {
      if (type === INTERACTION_TYPE.ORDER) {
        return INTERACTION_TYPE.ORDER;
      }

      return INTERACTION_TYPE.CONTINUE;
    };
    const btnType = getBtnType(type);

    const buttons = content.buttons;
    if (buttons.length === 1) {
      return {
        type: btnType,
        props: {
          ...buttons[0],
          script_id: content.script_id,
        },
      };
    } else {
      return {
        type,
        props: content,
      };
    }
  }
};

export const ChatComponents = forwardRef(
  (
    {
      className,
      lessonUpdate,
      onGoChapter = (id) => {},
      chapterId,
      onPurchased,
    },
    ref
  ) => {
    const { trackEvent } = useTracking();
    const [chatId, setChatId] = useState('');
    const [lessonId, setLessonId] = useState(null);
    const [inputDisabled, setInputDisabled] = useState(false);
    const [inputModal, setInputModal] = useState(null);
    const [_, setLessonEnd] = useState(false);
    // 是否是再聊天框内进行登录
    const [_lastSendMsg, setLastSendMsg] = useState(null);
    const [loadedChapterId, setLoadedChapterId] = useState('');
    const [loadedData, setLoadedData] = useState(false);
    // 是否在流式输出内容
    const [isStreaming, setIsStreaming] = useState(false);
    const [initRecords, setInitRecords] = useState([]);

    const { userInfo, frameLayout } = useContext(AppContext);
    const { lessonId: currLessonId, changeCurrLesson } = useCourseStore(
      (state) => state
    );

    const { messages, appendMsg, setTyping, updateMsg, resetList } =
      useMessages([]);

    const { checkLogin, updateUserInfo } = useUserStore((state) => state);

    const mobileStyle = frameLayout === FRAME_LAYOUT_MOBILE;
    const {
      open: payModalOpen,
      onOpen: onPayModalOpen,
      onClose: onPayModalClose,
    } = useDisclosture();

    const _onPayModalClose = useCallback(() => {
      onPayModalClose();
      setInputDisabled(false);
    }, [onPayModalClose])

    useEffect(() => {
      setLessonId(currLessonId);
    }, [currLessonId, lessonId]);

    const initLoadedInteraction = useCallback(
      (ui) => {
        const nextInputModal = convertEventInputModal(ui);
        setInputDisabled(false);
        setInputModal(nextInputModal);
      },
      []
    );

    const lessonUpdateResp = useCallback(
      (response, isEnd, nextStepFunc) => {
        const content = response.content;
        lessonUpdate?.({
          id: content.lesson_id,
          name: content.lesson_name,
          status: content.status,
        });

        if (content.status === LESSON_STATUS.PREPARE_LEARNING && !isEnd) {
          nextStepFunc({
            chatId,
            lessonId: content.lesson_id,
            type: INTERACTION_OUTPUT_TYPE.START,
            val: '',
          });
        }

        if (content.status === LESSON_STATUS.LEARNING && !isEnd) {
          setLessonId(content.lesson_id);
          changeCurrLesson(content.lesson_id);
        }
      },
      [changeCurrLesson, chatId, lessonUpdate]
    );

    const nextStep = useCallback(
      ({ chatId, lessonId, val, type, scriptId }) => {
        setLastSendMsg({ chatId, lessonId, val, type, scriptId });
        let lastMsg = null;
        let isEnd = false;

        runScript(chatId, lessonId, val, type, scriptId, (response) => {
          setLessonEnd((v) => {
            isEnd = v;
            return v;
          });

          try {
            if (response.type === RESP_EVENT_TYPE.TEXT) {
              if (isEnd) {
                return;
              }
              setIsStreaming(true);
              if (lastMsg !== null && lastMsg.type === 'text') {
                const currText = fixMarkdownStream(
                  lastMsg.content,
                  response.content
                );
                lastMsg.content = lastMsg.content + currText;
                updateMsg(lastMsg.id, lastMsg);
              } else {
                const id = genUuid();
                lastMsg = createMessage({
                  id: id,
                  type: response.type,
                  role: USER_ROLE.TEACHER,
                  content: response.content,
                  userInfo,
                });
                appendMsg(lastMsg);
              }
            } else if (response.type === RESP_EVENT_TYPE.TEXT_END) {
              setIsStreaming(false);
              setTyping(false);
              if (isEnd) {
                return;
              }
              lastMsg = null;
            } else if (
              response.type === RESP_EVENT_TYPE.INPUT ||
              response.type === RESP_EVENT_TYPE.PHONE ||
              response.type === RESP_EVENT_TYPE.CHECKCODE
            ) {
              if (isEnd) {
                return;
              }
              setInputModal({ type: response.type, props: response });
              setInputDisabled(false);
            } else if (
              response.type === RESP_EVENT_TYPE.BUTTONS ||
              response.type === RESP_EVENT_TYPE.ORDER
            ) {
              if (isEnd) {
                return;
              }
              const model = convertEventInputModal(response);
              setInputModal(model);
              setInputDisabled(false);
            } else if (response.type === RESP_EVENT_TYPE.LESSON_UPDATE) {
              lessonUpdateResp(response, isEnd, nextStep);
            } else if (response.type === RESP_EVENT_TYPE.CHAPTER_UPDATE) {
              const { status, lesson_id: lessonId } = response.content;
              if (status === LESSON_STATUS.COMPLETED) {
                isEnd = true;
                setLessonEnd(true);
                setTyping(false);
              }
              if (status === LESSON_STATUS.PREPARE_LEARNING) {
                setInputModal({
                  type: INTERACTION_TYPE.NEXT_CHAPTER,
                  props: {
                    label: '下一章',
                    lessonId,
                  },
                });
                setInputDisabled(false);
              }
            } else if (response.type === RESP_EVENT_TYPE.USER_LOGIN) {
              tokenTool.set({ token: response.content.token, faked: true });
              checkLogin();
            } else if (response.type === RESP_EVENT_TYPE.PROFILE_UPDATE) {
              const content = response.content;
              updateUserInfo({ [content.key]: content.value });
            }
          } catch (e) {}
        });
      },
      [appendMsg, checkLogin, lessonUpdateResp, setTyping, updateMsg, updateUserInfo, userInfo]
    );

    const scrollToBottom = useCallback(() => {
      const inner = document.querySelector(
        `.${styles.chatComponents} .PullToRefresh-inner`
      );
      document
        .querySelector(`.${styles.chatComponents} .PullToRefresh`)
        .scrollTo(0, inner.clientHeight);
    }, []);

    const onImageLoaded = useCallback(() => {
      scrollToBottom();
    }, [scrollToBottom]);

    useEffect(() => {
      if (!loadedData) {
        return;
      }

      scrollToBottom();

      if (!initRecords || initRecords.length === 0) {
        nextStep({
          chatId,
          lessonId: lessonId,
          type: INTERACTION_OUTPUT_TYPE.START,
          val: '',
        });
      }
      setLoadedData(false);
    }, [chatId, initRecords, lessonId, loadedData, nextStep, scrollToBottom]);

    useEffect(() => {
      async function resetAndLoadData() {
        // 只有课程切换时才重置数据
        if (!chapterId || loadedChapterId === chapterId) {
          return;
        }
        setIsStreaming(false);
        setTyping(false);
        setInputDisabled(true);
        setLessonEnd(false);
        resetList();
        setInitRecords(null);

        const resp = await getLessonStudyRecord(chapterId);
        const records = resp.data.records;
        setInitRecords(records);
        const ui = resp.data.ui;

        if (records) {
          records.forEach((v, i) => {
            if (v.script_type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
            } else {
              const newMessage = convertMessage(
                {
                  ...v,
                  id: i,
                  script_type: CHAT_MESSAGE_TYPE.TEXT,
                },
                userInfo
              );
              appendMsg(newMessage);
            }
          });

          setLessonId(records[records.length - 1].lesson_id);
        }

        if (ui) {
          initLoadedInteraction(ui);
        }

        setLoadedData(true);
        setLoadedChapterId(chapterId);
      }

      resetAndLoadData();
    }, [
      appendMsg,
      chapterId,
      initLoadedInteraction,
      loadedChapterId,
      resetList,
      setTyping,
      userInfo,
    ]);

    // debugger
    useEffect(() => {
      if (window.ztDebug) {
        window.ztDebug.resend = () => {
          setLastSendMsg((lastSendMsg) => {
            if (lastSendMsg) {
              nextStep({ ...lastSendMsg });
            }

            return lastSendMsg;
          });
        };

        window.ztDebug.resendX = (
          chatId,
          lessonId,
          val,
          type,
          scriptId = null
        ) => {
          nextStep({
            chatId,
            lessonId,
            val,
            type,
            scriptId,
          });
        };

        window.ztDebug.openPayModal = () => {
          onPayModalOpen();
        };
      }

      return () => {
        delete window.ztDebug.resend;
      };
    }, [nextStep, onPayModalOpen]);

    const handleSend = useCallback(
      async (type, val, scriptId) => {
        if (
          (type === INTERACTION_OUTPUT_TYPE.TEXT ||
            type === INTERACTION_OUTPUT_TYPE.SELECT ||
            type === INTERACTION_OUTPUT_TYPE.CONTINUE ||
            type === INTERACTION_OUTPUT_TYPE.PHONE ||
            type === INTERACTION_OUTPUT_TYPE.CHECKCODE) &&
          val.trim()
        ) {
          const message = createMessage({
            role: USER_ROLE.STUDENT,
            content: val,
            type: CHAT_MESSAGE_TYPE.TEXT,
            userInfo,
          });
          appendMsg(message);
        }

        setTyping(true);
        setInputDisabled(true);
        nextStep({ chatId, lessonId, type, val, scriptId });
      },
      [appendMsg, chatId, lessonId, nextStep, setTyping, userInfo]
    );

    const onPayModalOk = useCallback(() => {
      handleSend(INTERACTION_OUTPUT_TYPE.ORDER);
      onPurchased?.();
      onPayModalClose();
    }, [handleSend, onPayModalClose, onPurchased]);

    const renderMessageContent = useCallback(
      (msg) => {
        const { content, type } = msg;
        if (type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
          return <></>;
        }

        if (content === undefined) {
          return <></>;
        }

        if (type === CHAT_MESSAGE_TYPE.TEXT) {
          return (
            <MarkdownBubble
              content={content}
              isStreaming={isStreaming}
              mobileStyle={mobileStyle}
              onImageLoaded={onImageLoaded}
            />
          );
        }
        return <></>;
      },
      [isStreaming, mobileStyle, onImageLoaded]
    );


    const renderBeforeMessageList = () => {
      if (messages.length === 0) {
        return (
          <div
            className="full-height chat-ui_container"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          ></div>
        );
      }
    };

    const onChatInputSend = async (type, val, scriptId) => {
      if (type === INTERACTION_OUTPUT_TYPE.NEXT_CHAPTER) {
        onGoChapter?.(val.lessonId);
        return;
      }

      if (type === INTERACTION_OUTPUT_TYPE.ORDER) {
        setInputDisabled(true);
        trackEvent(EVENT_NAMES.POP_PAY, { from: 'script', way: 'manual' });
        onPayModalOpen();
        return;
      }

      handleSend(type, val, scriptId);
    };

    useImperativeHandle(ref, () => ({}));
    return (
      <div
        className={classNames(
          styles.chatComponents,
          className,
          mobileStyle ? styles.mobile : ''
        )}
      >
        <Chat
          navbar={null}
          messages={messages}
          renderMessageContent={renderMessageContent}
          renderBeforeMessageList={renderBeforeMessageList}
          recorder={{ canRecord: true }}
          inputOptions={{ disabled: inputDisabled }}
          Composer={() => {
            return <></>;
          }}
        />

        {inputModal && (
          <ChatInteractionArea
            type={inputModal.type}
            props={inputModal.props}
            disabled={inputDisabled}
            onSend={(type, val) => {
              onChatInputSend(type, val);
            }}
          />
        )}
        {mobileStyle && (
          <ChatMobileHeader className={styles.ChatMobileHeader} />
        )}
        <PayModal
          open={payModalOpen}
          onCancel={_onPayModalClose}
          onOk={onPayModalOk}
        />
      </div>
    );
  }
);

export default memo(ChatComponents);
