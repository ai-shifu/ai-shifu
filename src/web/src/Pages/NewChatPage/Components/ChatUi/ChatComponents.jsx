import '@chatui/core/dist/index.css';
import Chat, { useMessages } from '@chatui/core';
import {
  useEffect,
  forwardRef,
  useImperativeHandle,
  useState,
  useContext,
  useRef,
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
import PayModal from '../Pay/PayModal.jsx';
import LoginModal from '../Login/LoginModal.jsx';
import { useDisclosture } from 'common/hooks/useDisclosture.js';
import { memo } from 'react';
import { useCallback } from 'react';
import { tokenTool } from '@Service/storeUtil.js';
import MarkdownBubble from './ChatMessage/MarkdownBubble.jsx';
import { useTracking, EVENT_NAMES } from 'common/hooks/useTracking.js';
import PayModalM from '../Pay/PayModalM.jsx';
import { smoothScroll } from 'Utils/smoothScroll.js';
import { useSystemStore } from 'stores/useSystemStore.js';

const USER_ROLE = {
  TEACHER: '老师',
  STUDENT: '学生',
};

const robotAvatar = 'https://avtar.agiclass.cn/sunner.jpg';

const createMessage = ({
  id = 0,
  role,
  content,
  type = CHAT_MESSAGE_TYPE.TEXT,
  userInfo,
  teach_avator,
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

  let avatar = teach_avator ||  robotAvatar;

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

const convertMessage = (serverMessage, userInfo, teach_avator) => {
  if (serverMessage.script_type === CHAT_MESSAGE_TYPE.TEXT) {
    return createMessage({
      id: serverMessage.id,
      role: serverMessage.script_role,
      content: fixMarkdown(serverMessage.script_content),
      type: serverMessage.script_type,
      userInfo,
      teach_avator,
    });
  } else if (serverMessage.script_type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
    return createMessage({
      id: serverMessage.id,
      role: serverMessage.script_role,
      content: { lessonId: serverMessage.lesson_id },
      type: serverMessage.script_type,
      userInfo,
      teach_avator,
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
  } else if (
    type === RESP_EVENT_TYPE.BUTTONS ||
    type === RESP_EVENT_TYPE.ORDER ||
    type === RESP_EVENT_TYPE.REQUIRE_LOGIN
  ) {

    const getBtnType = (type) => {
      if (type === INTERACTION_TYPE.ORDER) {
        return INTERACTION_TYPE.ORDER;
      }
      if (type === RESP_EVENT_TYPE.REQUIRE_LOGIN) {
        return INTERACTION_TYPE.REQUIRE_LOGIN;
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

const SCROLL_BOTTOM_THROTTLE = 50;
export const ChatComponents = forwardRef(
  (
    {
      className,
      lessonUpdate,
      onGoChapter = (id) => {},
      chapterId,
      onPurchased,
      chapterUpdate,
    },
    ref
  ) => {
    const { trackEvent, trackTrailProgress } = useTracking();
    const chatId = useSystemStore().courseId;
    const [lessonId, setLessonId] = useState(null);
    const [inputDisabled, setInputDisabled] = useState(false);
    const [inputModal, setInputModal] = useState(null);
    const [_, setLessonEnd] = useState(false);
    const [_lastSendMsg, setLastSendMsg] = useState(null);
    const [loadedChapterId, setLoadedChapterId] = useState('');
    const [loadedData, setLoadedData] = useState(false);
    const [isStreaming, setIsStreaming] = useState(false);
    const [initRecords, setInitRecords] = useState([]);

    const [autoScroll, setAutoScroll] = useState(true);
    const [askMode, setAskMode] = useState(false);

    const { userInfo, mobileStyle } = useContext(AppContext);
    const chatRef = useRef();
    const {
      lessonId: currLessonId,
      changeCurrLesson,
      updateResetedChapterId,
    } = useCourseStore((state) => ({
      lessonId: state.lessonId,
      changeCurrLesson: state.changeCurrLesson,
      updateResetedChapterId: state.updateResetedChapterId,
    }));

    const { messages, appendMsg, setTyping, updateMsg, resetList, deleteMsg } =
      useMessages([]);

    const { checkLogin, updateUserInfo, refreshUserInfo } = useUserStore(
      (state) => ({
        checkLogin: state.checkLogin,
        updateUserInfo: state.updateUserInfo,
        refreshUserInfo: state.refreshUserInfo,
      })
    );

    const {
      open: payModalOpen,
      onOpen: onPayModalOpen,
      onClose: onPayModalClose,
    } = useDisclosture();

    const {
      open: loginModalOpen,
      onOpen: onLoginModalOpen,
      onClose: onLoginModalClose,
    } = useDisclosture();

    const _onPayModalClose = useCallback(() => {
      onPayModalClose();
      setInputDisabled(false);
    }, [onPayModalClose]);

    const _onLoginModalClose = useCallback(() => {
      onLoginModalClose();
      setInputDisabled(false);
    }, [onLoginModalClose]);

    useEffect(() => {
      setLessonId(currLessonId);
    }, [currLessonId, lessonId]);

    const initLoadedInteraction = useCallback((ui) => {
      const nextInputModal = convertEventInputModal(ui);
      setInputDisabled(false);
      setInputModal(nextInputModal);
    }, []);

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
        setAskMode(false);
        setLastSendMsg({ chatId, lessonId, val, type, scriptId });
        let lastMsg = null;
        let isEnd = false;
        let teach_avator = null;
        runScript(chatId, lessonId, val, type, scriptId, (response) => {
          setLessonEnd((v) => {
            isEnd = v;
            return v;
          });


          if (response.type === RESP_EVENT_TYPE.TEACHER_AVATOR) {
            teach_avator = response.content;
          }

          const scriptId = response.script_id;
          if (
            [
              RESP_EVENT_TYPE.TEXT_END,
              RESP_EVENT_TYPE.PHONE,
              RESP_EVENT_TYPE.CHECKCODE,
              RESP_EVENT_TYPE.ORDER,
              RESP_EVENT_TYPE.USER_LOGIN,
              RESP_EVENT_TYPE.REQUIRE_LOGIN,
            ].includes(response.type)
          ) {
            trackTrailProgress(scriptId);
          }

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
                  teach_avator: teach_avator,
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
              response.type === RESP_EVENT_TYPE.ORDER ||
              response.type === RESP_EVENT_TYPE.REQUIRE_LOGIN
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
              const { status, lesson_id: chapterId } = response.content;
              chapterUpdate?.({ id: chapterId, status });
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
                    lessonId: chapterId,
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
            } else if (response.type === RESP_EVENT_TYPE.ASK_MODE) {
              const content = response.content;
              setAskMode(content.ask_mode);
            }
          } catch (e) {}
        });
      },
      [
        appendMsg,
        chapterUpdate,
        checkLogin,
        lessonUpdateResp,
        setTyping,
        trackTrailProgress,
        updateMsg,
        updateUserInfo,
        userInfo,
      ]
    );

    const onMessageListScroll = useCallback(
      (e) => {
        const scrollWrapper = e.target;
        const inner = scrollWrapper.children[0];

        if (!scrollWrapper || !inner) {
          return;
        }

        if (
          scrollWrapper.scrollTop >= 0 &&
          scrollWrapper.scrollTop + scrollWrapper.clientHeight <
            inner.clientHeight - SCROLL_BOTTOM_THROTTLE
        ) {
          if (
            messages.length &&
            messages[messages.length - 1].position === 'pop'
          ) {
            return;
          }
          setAutoScroll(false);
          appendMsg({ type: 'loading', position: 'pop' });
        } else {
          if (
            messages.length &&
            messages[messages.length - 1].position === 'pop'
          ) {
            setAutoScroll(true);
            deleteMsg(messages[messages.length - 1]._id);
          }
        }
      },
      [appendMsg, messages, deleteMsg]
    );

    const scrollToBottom = useCallback(() => {
      const inner = document.querySelector(
        `.${styles.chatComponents} .PullToRefresh-inner`
      );
      const wrapper = document.querySelector(
        `.${styles.chatComponents} .PullToRefresh`
      );
      smoothScroll({ el: wrapper, to: inner.clientHeight });
    }, []);

    const onImageLoaded = useCallback(() => {
      if (!autoScroll) {
        return;
      }
      scrollToBottom();
    }, [autoScroll, scrollToBottom]);

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

    const resetAndLoadData = useCallback(async () => {
      if (!chapterId) {
        return;
      }
      setIsStreaming(false);
      setTyping(false);
      setInputDisabled(true);
      setLessonEnd(false);
      resetList();
      setInitRecords(null);

      const resp = await getLessonStudyRecord(chapterId);
      const records = resp.data?.records || [];
      const teach_avator = resp.data?.teach_avator || null;
      setInitRecords(records);
      const ui = resp.data?.ui || null;

      if (records && records.length > 0) {
        records.forEach((v, i) => {
          if (v.script_type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
          } else {
            const newMessage = convertMessage(
              {
                ...v,
                id: i,
                script_type: CHAT_MESSAGE_TYPE.TEXT,
              },
              userInfo,
              teach_avator
            );
            appendMsg(newMessage);
          }
        });

        setLessonId(records[records.length - 1].lesson_id);
      }

      if (ui) {
        initLoadedInteraction(ui);
      }
      setAskMode(resp.data?.ask_mode)
      setLoadedData(true);
      setLoadedChapterId(chapterId);
    }, [
      appendMsg,
      chapterId,
      initLoadedInteraction,
      resetList,
      setTyping,
      userInfo,
    ]);

    useEffect(() => {
      if (loadedChapterId !== chapterId) {
        setLoadedChapterId(chapterId);
        resetAndLoadData();
      }
    }, [chapterId, loadedChapterId, resetAndLoadData]);

    useEffect(() => {
      return useCourseStore.subscribe(
        (state) => state.resetedChapterId,
        (curr) => {
          if (!curr) {
            return;
          }

          if (curr === loadedChapterId) {
            resetAndLoadData();
            // 恢复到 null
            updateResetedChapterId(null);
          } else {
            return;
          }
        }
      );
    });

    useEffect(() => {
      return useUserStore.subscribe(
        (state) => state.hasLogin,
        () => {
          setLoadedChapterId(chapterId);
          resetAndLoadData();
        }
      );
    }, [chapterId, resetAndLoadData]);

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
        if (window.ztDebug) {
          delete window.ztDebug.resend;
        }
      };
    }, [nextStep, onPayModalOpen]);

    const handleSend = useCallback(
      async (type, val, scriptId) => {
        if (
          (type === INTERACTION_OUTPUT_TYPE.TEXT ||
            type === INTERACTION_OUTPUT_TYPE.SELECT ||
            type === INTERACTION_OUTPUT_TYPE.CONTINUE ||
            type === INTERACTION_OUTPUT_TYPE.PHONE ||
            type === INTERACTION_OUTPUT_TYPE.CHECKCODE ||
            type === INTERACTION_OUTPUT_TYPE.LOGIN ||
            type === INTERACTION_OUTPUT_TYPE.ASK) &&
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
        scrollToBottom();
        nextStep({ chatId, lessonId, type, val, scriptId });
      },
      [
        appendMsg,
        chatId,
        lessonId,
        nextStep,
        scrollToBottom,
        setTyping,
        userInfo,
      ]
    );

    const onPayModalOk = useCallback(() => {
      handleSend(INTERACTION_OUTPUT_TYPE.ORDER);
      onPurchased?.();
      refreshUserInfo();
    }, [handleSend, onPurchased, refreshUserInfo]);

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

    const onChatInputSend = useCallback(
      async (type, val, scriptId) => {
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
        if (type === INTERACTION_OUTPUT_TYPE.REQUIRE_LOGIN) {
          setInputDisabled(true);
          trackEvent(EVENT_NAMES.POP_LOGIN, { from: 'script', way: 'manual' });
          onLoginModalOpen();
          return;
        }

        handleSend(type, val, scriptId);
      },
      [handleSend, onGoChapter, onLoginModalOpen, onPayModalOpen, trackEvent]
    );

    useImperativeHandle(ref, () => ({}));

    const onChatInteractionAreaSizeChange = useCallback(({ height }) => {
      if (!chatRef || !chatRef.current) {
        return;
      }

      const messageListElem = chatRef.current.querySelector('.MessageList');
      if (!messageListElem) {
        return;
      }

      messageListElem.style.paddingBottom = `${height}px`;
    }, []);

    const onLogin = useCallback(async () => {

      console.log('onLogin');
      await refreshUserInfo();
      handleSend(INTERACTION_OUTPUT_TYPE.LOGIN, '已经登录成功登录了');

    }, [handleSend, refreshUserInfo]);

    return (
      <div
        className={classNames(
          styles.chatComponents,
          className,
          mobileStyle ? styles.mobile : ''
        )}
        ref={chatRef}
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
          onScroll={onMessageListScroll}
        />

        {inputModal && (
          <ChatInteractionArea
            askMode={askMode}
            type={inputModal.type}
            props={inputModal.props}
            disabled={inputDisabled}
            onSend={onChatInputSend}
            onSizeChange={onChatInteractionAreaSizeChange}
          />
        )}
        {payModalOpen &&
          (mobileStyle ? (
            <PayModalM
              open={payModalOpen}
              onCancel={_onPayModalClose}
              onOk={onPayModalOk}
            />
          ) : (
            <PayModal
              open={payModalOpen}
              onCancel={_onPayModalClose}
              onOk={onPayModalOk}
            />
          ))}
        {loginModalOpen && (
          <LoginModal open={loginModalOpen} onClose={_onLoginModalClose} onLogin={onLogin} />
        )}
      </div>
    );
  }
);

export default memo(ChatComponents);
