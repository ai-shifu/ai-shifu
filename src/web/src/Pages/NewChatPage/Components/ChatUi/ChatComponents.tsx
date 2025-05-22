import '@chatui/core/dist/index.css';
import Chat, { useMessages } from '@chatui/core';
import { LikeOutlined, DislikeOutlined, LikeFilled, DislikeFilled } from '@ant-design/icons';
import {
  useEffect,
  forwardRef,
  useImperativeHandle,
  useState,
  useContext,
  useRef,
} from 'react';
import { runScript, getLessonStudyRecord, scriptContentOperation } from 'Api/study';
import { genUuid } from 'Utils/common';
import ChatInteractionArea from './ChatInput/ChatInteractionArea';
import { AppContext } from 'Components/AppContext';
import styles from './ChatComponents.module.scss';
import { useCourseStore } from 'stores/useCourseStore';
import {
  LESSON_STATUS_VALUE,
  INTERACTION_TYPE,
  INTERACTION_OUTPUT_TYPE,
  RESP_EVENT_TYPE,
  CHAT_MESSAGE_TYPE,
} from 'constants/courseConstants';
import classNames from 'classnames';
import { useUserStore } from 'stores/useUserStore';
import { fixMarkdown, fixMarkdownStream } from 'Utils/markdownUtils';
import PayModal from '../Pay/PayModal';
import LoginModal from '../Login/LoginModal';
import { useDisclosture } from 'common/hooks/useDisclosture';
import { memo } from 'react';
import { useCallback } from 'react';
import { tokenTool } from 'Service/storeUtil';
import MarkdownBubble from './ChatMessage/MarkdownBubble';
import { useTracking, EVENT_NAMES } from 'common/hooks/useTracking';
import PayModalM from '../Pay/PayModalM';
import { useTranslation } from 'react-i18next';
import { useEnvStore } from 'stores/envStore';
import { shifu } from 'Service/Shifu';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
} from 'Pages/NewChatPage/events';
import ActiveMessageControl from './ChatMessage/ActiveMessageControl';
import { convertKeysToCamelCase } from 'Utils/objUtils';
import { useShallow } from 'zustand/react/shallow';
import { useChatComponentsScroll } from './ChatComponents/useChatComponentsScroll';
import logoColor120 from 'Assets/logos/logo-color-120.png';


const USER_ROLE = {
  TEACHER: '老师',
  STUDENT: '学生',
};

const createMessage = ({
  id = '',
  role,
  content,
  interaction_type,
  logid,
  type = CHAT_MESSAGE_TYPE.TEXT,
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

  let avatar = teach_avator || logoColor120;

  if (role === USER_ROLE.STUDENT) {
    avatar = null;
  }
  return {
    _id: mid,
    id: mid,
    role,
    content,
    interaction_type,
    isComplete: false,
    logid,
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
      interaction_type: serverMessage.interaction_type,
      logid: serverMessage.logid,
      type: serverMessage.script_type,
      userInfo,
      teach_avator,
      isComplete: true,
    });
  } else if (serverMessage.script_type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
    return createMessage({
      id: serverMessage.id,
      role: serverMessage.script_role,
      content: { lessonId: serverMessage.lesson_id },
      type: serverMessage.script_type,
      interaction_type: serverMessage.interaction_type,
      logid: serverMessage.logid,
      userInfo,
      teach_avator,
      isComplete: true,
    });
  }

  return {};
};

const convertEventInputModal = ({ type, content, script_id }) => {
  const scriptId = script_id;

  if (type === RESP_EVENT_TYPE.PHONE || type === RESP_EVENT_TYPE.CHECKCODE) {
    return {
      type,
      props: { content, scriptId },
    };
  } else if (type === RESP_EVENT_TYPE.INPUT) {
    return {
      type,
      props: { content, scriptId },
    };
  } else if (
    type === RESP_EVENT_TYPE.BUTTONS ||
    type === RESP_EVENT_TYPE.ORDER ||
    type === RESP_EVENT_TYPE.NONBLOCK_ORDER ||
    type === RESP_EVENT_TYPE.REQUIRE_LOGIN
  ) {
    const getBtnType = (type) => {
      if (type === INTERACTION_TYPE.ORDER) {
        return INTERACTION_TYPE.ORDER;
      }
      if (type === INTERACTION_TYPE.NONBLOCK_ORDER) {
        return INTERACTION_TYPE.NONBLOCK_ORDER;
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
          scriptId,
        },
      };
    } else {
      return {
        type,
        props: { ...content, scriptId },
      };
    }
  }
};

export const ChatComponents = forwardRef(
  (
    {
      className,
      lessonUpdate,
      onGoChapter = () => { },
      chapterId,
      lessonId,
      onPurchased,
      chapterUpdate,
      updateSelectedLesson,
    },
    ref
  ) => {
    const { t } = useTranslation();
    const { trackEvent, trackTrailProgress } = useTracking();
    const { courseId } = useEnvStore.getState();
    const chatId = courseId;

    const [inputDisabled, setInputDisabled] = useState(false);
    const [inputModal, setInputModal] = useState(null);
    const [loadedChapterId, setLoadedChapterId] = useState('');
    const [loadedData, setLoadedData] = useState(false);
    const [isStreaming, setIsStreaming] = useState(false);
    const [initRecords, setInitRecords] = useState([]);
    // lesson id the current message is belong to
    const [messageLessonId, setMessageLessonId] = useState('');

    // action control is register in plugin
    const [showActionControl, setShowActionControl] = useState(false);
    const [actionControlType, setActionControlType] = useState('');
    const [actionControlPayload, setActionControlPayload] = useState({
      type: '',
      val: '',
      scriptId: '',
    });
    const [askButtonState, setAskButtonState] = useState({
      total: 1,
      used: 1,
      askMode: false,
      visible: false,
    });

    const { userInfo, mobileStyle } = useContext(AppContext);
    const chatRef = useRef();

    const { updateResetedChapterId } = useCourseStore(
      useShallow((state) => ({
        updateResetedChapterId: state.updateResetedChapterId,
      }))
    );

    const { messages, appendMsg, setTyping, updateMsg, resetList, deleteMsg } =
      useMessages([]);

    const { autoScroll, onMessageListScroll, scrollToLesson, scrollToBottom } =
      useChatComponentsScroll({
        chatRef,
        containerStyle: styles.chatComponents,
        messages,
        appendMsg,
        deleteMsg,
      });
    const lastMsgRef = useRef(null);
    const { checkLogin, updateUserInfo, refreshUserInfo } = useUserStore(
      useShallow((state) => ({
        checkLogin: state.checkLogin,
        updateUserInfo: state.updateUserInfo,
        refreshUserInfo: state.refreshUserInfo,
      }))
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

    const closeActionControl = useCallback(() => {
      setShowActionControl(false);
    }, []);

    const onActionControlComplete = (type, display, val, scriptId) => {
      closeActionControl();
      handleSend(type, display, val, scriptId);
    };

    const getActionControl = () => {
      const Control = shifu.getChatInputActionControls(actionControlType);
      return (
        <Control
          onClose={closeActionControl}
          payload={actionControlPayload}
          onComplete={onActionControlComplete}
        ></Control>
      );
    };

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
          status_value: content.status_value,
        });

        if (
          content.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING &&
          !isEnd
        ) {
          nextStepFunc({
            chatId,
            lessonId: content.lesson_id,
            type: INTERACTION_OUTPUT_TYPE.START,
            val: '',
          });
        }

        if (content.status_value === LESSON_STATUS_VALUE.LEARNING && !isEnd) {
          updateSelectedLesson(content.lesson_id);
        }
      },
      [chatId, lessonUpdate, updateSelectedLesson]
    );

    const nextStep = useCallback(
      ({ chatId, lessonId, val, type, scriptId }) => {
        setAskButtonState((v) => ({
          ...v,
          askMode: false,
        }));
        let lastMsg = null;
        let isEnd = false;
        let teach_avator = null;
        let lastLessonId = messageLessonId;
        let lastActiveMsg = null;

        runScript(chatId, lessonId, val, type, scriptId, async (response) => {

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
              RESP_EVENT_TYPE.NONBLOCK_ORDER,
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
                console.log('lastMsg', lastMsg.content);
                lastMsgRef.current = lastMsg;
              } else {
                console.log('appendMsg', response.content);
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
                lastMsgRef.current = lastMsg;
              }
            } else if (response.type === RESP_EVENT_TYPE.TEXT_END) {
              setIsStreaming(false);
              setTyping(false);
              if (lastMsg) {
                lastMsg.isComplete = true;
                if (response.log_id) {
                  lastMsg.logid = response.log_id;
                }
                updateMsg(lastMsg.id, lastMsg);
                // lastMsg = null;
                lastActiveMsg = lastMsg;
                lastMsg = null;
                lastMsgRef.current = null;
              }
              lastMsgRef.current = null;
              if (isEnd) {
                lastMsg = null;
                return;
              }
            } else if (response.type === RESP_EVENT_TYPE.ACTIVE) {
              if (lastActiveMsg) {
                lastActiveMsg.ext = {
                  ...lastActiveMsg.ext,
                  active: convertKeysToCamelCase(response.content),
                };
                updateMsg(lastActiveMsg.id, lastActiveMsg);
                lastActiveMsg = null;
              }
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
              response.type === RESP_EVENT_TYPE.NONBLOCK_ORDER ||
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

              const content = response.content;

              if (
                content.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING
              ) {
                const newLessonId = content.lesson_id;
                if (!newLessonId) {
                  return;
                }
                if (newLessonId !== lastLessonId) {
                  const msg = createMessage({
                    id: `lesson-${newLessonId}`,
                    type: CHAT_MESSAGE_TYPE.LESSON_SEPARATOR,
                    content: { lessonId: newLessonId },
                  });
                  appendMsg(msg);
                  lastLessonId = newLessonId;
                  setMessageLessonId(newLessonId);
                }
              }
            } else if (response.type === RESP_EVENT_TYPE.CHAPTER_UPDATE) {
              const {
                status,
                status_value,
                lesson_id: chapterId,
              } = response.content;
              chapterUpdate?.({ id: chapterId, status, status_value });
              if (status_value === LESSON_STATUS_VALUE.COMPLETED) {
                isEnd = true;
                setTyping(false);
              }
              if (status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING) {
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
              await tokenTool.set({
                token: response.content.token,
                faked: true,
              });
              checkLogin();
            } else if (response.type === RESP_EVENT_TYPE.PROFILE_UPDATE) {
              const content = response.content;
              updateUserInfo({ [content.key]: content.value });
            } else if (response.type === RESP_EVENT_TYPE.ASK_MODE) {
              const content = response.content;
              setAskButtonState({
                used: content.ask_count,
                total: content.ask_limit_count,
                askMode: content.ask_mode,
                visible: content.visible,
              });
            }
          } catch (e) { }
        });
      },
      [
        appendMsg,
        chapterUpdate,
        checkLogin,
        lessonUpdateResp,
        messageLessonId,
        setTyping,
        trackTrailProgress,
        updateMsg,
        updateUserInfo,
        userInfo,
      ]
    );

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
      resetList();
      setInitRecords(null);

      const resp = await getLessonStudyRecord(chapterId);
      const records = resp.data?.records || [];
      const teach_avator = resp.data?.teach_avator || null;
      setInitRecords(records);
      const ui = resp.data?.ui || null;

      if (records && records.length > 0) {
        let lessonId = '';
        let lastMsg = null;

        records.forEach((v, i) => {
          const newLessonId = v.lesson_id;
          if (newLessonId !== lessonId && !!newLessonId) {
            lessonId = newLessonId;
            appendMsg(
              convertMessage({
                ...v,
                id: `lesson-${newLessonId}`,
                script_type: CHAT_MESSAGE_TYPE.LESSON_SEPARATOR,
                logid: v.id,
              })
            );
          }

          if (v.script_type === CHAT_MESSAGE_TYPE.ACTIVE) {
            if (!lastMsg) {
              return;
            }

            lastMsg.ext = {
              ...lastMsg.ext,
              active: convertKeysToCamelCase({
                msg: v.script_content,
                ...v.data,
              }),
            };
            updateMsg(lastMsg.id, lastMsg);
            lastMsg = null;
            return;
          }

          const newMessage = convertMessage(
            {
              ...v,
              id: i,
              script_type: CHAT_MESSAGE_TYPE.TEXT,
              logid: v.id,
            },
            userInfo,
            teach_avator
          );
          appendMsg(newMessage);
          lastMsg = newMessage;
        });

        setMessageLessonId(lessonId);
      }

      if (ui) {
        initLoadedInteraction(ui);
      }
      const askUiContent = resp.data?.ask_ui?.content;

      if (askUiContent) {
        setAskButtonState({
          used: askUiContent.ask_count,
          total: askUiContent.ask_limit_count,
          askMode: askUiContent.ask_mode,
          visible: askUiContent.visible,
        });
      }

      setLoadedData(true);
      setLoadedChapterId(chapterId);
    }, [
      appendMsg,
      chapterId,
      initLoadedInteraction,
      resetList,
      setTyping,
      updateMsg,
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
            // reset to null
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
      async (type, display, val, scriptId) => {
        if (
          type === INTERACTION_OUTPUT_TYPE.TEXT ||
          type === INTERACTION_OUTPUT_TYPE.SELECT ||
          type === INTERACTION_OUTPUT_TYPE.CONTINUE ||
          type === INTERACTION_OUTPUT_TYPE.PHONE ||
          type === INTERACTION_OUTPUT_TYPE.CHECKCODE ||
          type === INTERACTION_OUTPUT_TYPE.LOGIN ||
          type === INTERACTION_OUTPUT_TYPE.ASK
        ) {
          if (val && typeof val === 'string' && val.trim() && display) {
            const message = createMessage({
              role: USER_ROLE.STUDENT,
              content: val,
              type: CHAT_MESSAGE_TYPE.TEXT,
              userInfo,
            });
            await appendMsg(message);
          }
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

    const [interactionTypes, setInteractionTypes] = useState({});


    const renderMessageContentOperation = useCallback(
      (msg) => {
        const likeClick = async () => {
          setInteractionTypes((prevTypes) => {
            const currentType = prevTypes[msg.id] ?? msg.interaction_type;
            const updatedTypes = {
              ...prevTypes,
              [msg.id]: currentType === 1 ? 0 : 1,
            };

            scriptContentOperation(msg.logid, updatedTypes[msg.id]).then(() => { });
            return updatedTypes;
          });
        };

        const disClick = async () => {
          setInteractionTypes((prevTypes) => {
            const currentType = prevTypes[msg.id] ?? msg.interaction_type;
            const updatedTypes = {
              ...prevTypes,
              [msg.id]: currentType === 2 ? 0 : 2,
            };

            scriptContentOperation(msg.logid, updatedTypes[msg.id]).then(() => { });
            return updatedTypes;
          });
        };

        const currentInteractionType =
          interactionTypes[msg.id] ?? msg.interaction_type;

        return (
          <div className={styles.messageContentOperation}>
            {currentInteractionType === 1 ? (
              <LikeFilled className={styles.brandcolor} onClick={likeClick} />
            ) : (
              <LikeOutlined className={styles.brandcolor} onClick={likeClick} />
            )}
            {currentInteractionType === 2 ? (
              <DislikeFilled className={styles.brandcolor} onClick={disClick} />
            ) : (
              <DislikeOutlined className={styles.brandcolor} onClick={disClick} />
            )}
          </div>
        );
      },
      [interactionTypes, setInteractionTypes]
    );


    const renderMessageContent = useCallback(
      (msg) => {
        const { content, type, ext } = msg;
        if (type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
          return <></>;
        }

        if (content === undefined) {
          return <></>;
        }
        if (type === CHAT_MESSAGE_TYPE.TEXT) {
          return (
            <div>
              <MarkdownBubble
                content={content}
                isStreaming={isStreaming}
                mobileStyle={mobileStyle}
                onImageLoaded={onImageLoaded}
              />
              {ext?.active && <ActiveMessageControl {...ext.active} />}
              {((msg.isComplete || msg.logid) && msg.position == 'left') && renderMessageContentOperation(msg)}
            </div>
          );
        }
        return <></>;
      },
      [isStreaming, mobileStyle, onImageLoaded, renderMessageContentOperation]
    );

    const onChatInputSend = useCallback(
      async (type, display, val, scriptId) => {
        if (type === INTERACTION_OUTPUT_TYPE.NEXT_CHAPTER) {
          onGoChapter?.(val.lessonId);
          return;
        }

        if (type === INTERACTION_OUTPUT_TYPE.ORDER) {
          setInputDisabled(true);
          trackEvent(EVENT_NAMES.POP_PAY, { from: 'show-btn' });
          onPayModalOpen();
          return;
        }

        if (type === INTERACTION_OUTPUT_TYPE.REQUIRE_LOGIN) {
          setInputDisabled(true);
          trackEvent(EVENT_NAMES.POP_LOGIN, { from: 'script' });
          onLoginModalOpen();
          return;
        }

        if (
          !(
            type === INTERACTION_OUTPUT_TYPE.TEXT ||
            type === INTERACTION_OUTPUT_TYPE.SELECT ||
            type === INTERACTION_OUTPUT_TYPE.CONTINUE ||
            type === INTERACTION_OUTPUT_TYPE.PHONE ||
            type === INTERACTION_OUTPUT_TYPE.CHECKCODE ||
            type === INTERACTION_OUTPUT_TYPE.LOGIN ||
            type === INTERACTION_OUTPUT_TYPE.ASK
          )
        ) {
          setShowActionControl(true);
          setActionControlType(type);
          setActionControlPayload({
            type,
            val,
            scriptId,
          });

          if (type === INTERACTION_OUTPUT_TYPE.NONBLOCK_ORDER) {
            trackEvent(EVENT_NAMES.POP_PAY, { from: 'show-nb-btn' });
          }
          return;
        }

        handleSend(type, display, val, scriptId);
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
      await refreshUserInfo();
      handleSend(INTERACTION_OUTPUT_TYPE.LOGIN, false, t('chat.loginSuccess'));
    }, [handleSend, refreshUserInfo, t]);

    useEffect(() => {
      const onGoToNavigationNode = (e) => {
        const { chapterId, lessonId } = e.detail;

        if (chapterId !== loadedChapterId) {
          return;
        }

        scrollToLesson(lessonId);
        updateSelectedLesson(lessonId);
      };

      events.addEventListener(
        BZ_EVENT_NAMES.GO_TO_NAVIGATION_NODE,
        onGoToNavigationNode
      );

      return () => {
        events.removeEventListener(
          BZ_EVENT_NAMES.GO_TO_NAVIGATION_NODE,
          onGoToNavigationNode
        );
      };
    }, [loadedChapterId, scrollToLesson, updateSelectedLesson]);
    useEffect(() => {
      if (lastMsgRef.current) {
        const messageIndex = messages.findIndex(msg => msg.id === lastMsgRef.current.id);
        if (messageIndex === -1) {
          appendMsg(lastMsgRef.current);
        } else if (messageIndex !== messages.length - 1) {
          deleteMsg(lastMsgRef.current.id);
          appendMsg(lastMsgRef.current);
        }
      }
    }, [messages, appendMsg, deleteMsg]);

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
          recorder={{ canRecord: true }}
          inputOptions={{ disabled: inputDisabled }}
          Composer={() => {
            return <></>;
          }}
          onScroll={onMessageListScroll}
        />

        {inputModal && (
          <ChatInteractionArea
            askButtonState={askButtonState}
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
          ))}
        {loginModalOpen && (
          <LoginModal
            open={loginModalOpen}
            onClose={_onLoginModalClose}
            onLogin={onLogin}
          />
        )}
        {showActionControl && getActionControl()}
      </div>
    );
  }
);

export default memo(ChatComponents);
