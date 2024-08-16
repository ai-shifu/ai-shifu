import '@chatui/core/dist/index.css';
import Chat, { Bubble, useMessages } from '@chatui/core';
import { Button, Image } from 'antd';
import {
  useEffect,
  forwardRef,
  useImperativeHandle,
  useState,
  useContext,
} from 'react';
import { runScript, getLessonStudyRecord } from '@Api/study';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { CopyOutlined } from '@ant-design/icons';
import { genUuid } from '@Utils/common.js';
import ChatInteractionArea from './ChatInput/ChatInteractionArea.jsx';
import { AppContext } from 'Components/AppContext.js';
import styles from './ChatComponents.module.scss';
import { useCourseStore } from '@stores/useCourseStore.js';
import {
  LESSON_STATUS,
  INTERACTION_TYPE,
  INTERACTION_OUTPUT_TYPE,
  RESP_EVENT_TYPE,
  CHAT_MESSAGE_TYPE,
} from 'constants/courseConstants.js';
import classNames from 'classnames';
import { useUserStore } from '@stores/useUserStore.js';
import { fixMarkdown, fixMarkdownStream } from '@Utils/markdownUtils.js';
import { testPurchaseOrder } from '@Api/order.js';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { FRAME_LAYOUT_MOBILE } from 'constants/uiConstants.js';
import ChatMobileHeader from './ChatMobileHeader.jsx';

const USER_ROLE = {
  TEACHER: '老师',
  STUDENT: '学生',
};

const robotAvatar = require('@Assets/chat/sunner_icon.jpg');

const MarkdownBubble = (props) => {
  const { mobileStyle } = props;
  const onCopy = (content) => {
    navigator.clipboard.writeText(content);
  };

  return (
    <Bubble>
      <ReactMarkdown
        children={props.content}
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            return !inline && match ? (
              <div
                className="markdown-code_block"
                style={{
                  position: 'relative',
                }}
              >
                <Button
                  className="copy_btn"
                  type="dashed"
                  ghost
                  size="small"
                  icon={<CopyOutlined></CopyOutlined>}
                  onClick={() => onCopy(children)}
                ></Button>
                <SyntaxHighlighter
                  {...props}
                  children={String(children).replace(/\n$/, '')}
                  style={vscDarkPlus}
                  language={match[1]}
                  showLineNumbers={!mobileStyle}
                  wrapLines={false}
                  onCopy={() => {
                    onCopy(children);
                  }}
                ></SyntaxHighlighter>
              </div>
            ) : (
              <code
                {...props}
                className={classNames(className, styles.inlineCode)}
              >
                {children}
              </code>
            );
          },
          img(imgProps) {
            return (
              <Image
                {...imgProps}
                width={mobileStyle ? '100%' : '70%'}
                preview={!props.isStreaming}
              ></Image>
            );
          },
        }}
      />
    </Bubble>
  );
};

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
  if (type === RESP_EVENT_TYPE.INPUT) {
    return {
      type,
      props: { content },
    };
  } else if (
    type === RESP_EVENT_TYPE.BUTTONS ||
    type === RESP_EVENT_TYPE.ORDER
  ) {
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
    const [chatId, setChatId] = useState('');
    const [lessonId, setLessonId] = useState(null);
    const [inputDisabled, setInputDisabled] = useState(false);
    const [inputModal, setInputModal] = useState(null);
    const [_, setLessonEnd] = useState(false);
    // 是否是再聊天框内进行登录
    const [loginInChat, setLoginInChat] = useState(false);
    const [loaded, setLoaded] = useState(false);
    const [lastSendMsg, setLastSendMsg] = useState(null);
    const [loadedData, setLoadedData] = useState(false);
    // 是否在流式输出内容
    const [isStreaming, setIsStreaming] = useState(false);

    const { userInfo, frameLayout } = useContext(AppContext);
    const { lessonId: currLessonId, changeCurrLesson } = useCourseStore(
      (state) => state
    );

    const { messages, appendMsg, setTyping, updateMsg, resetList } =
      useMessages([]);

    const { hasLogin, checkLogin, updateUserInfo } = useUserStore(
      (state) => state
    );

    const mobileStyle = frameLayout === FRAME_LAYOUT_MOBILE;
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
      }

      return () => {
        delete window.ztDebug.resend;
      };
    }, []);

    useEffect(() => {
      if (!lessonId) {
        setLessonId(currLessonId);
      }
    }, [currLessonId]);

    const fixRecordData = (records) => {
      let lessonId = '';

      return records;
    };

    const resetAndLoadData = async () => {
      if (!chapterId) {
        return;
      }

      setIsStreaming(false);
      setTyping(false);
      setInputDisabled(true);
      setLessonEnd(false);
      resetList();

      const resp = await getLessonStudyRecord(chapterId);
      const records = resp.data.records;
      const ui = resp.data.ui;

      if (!records || records.length === 0) {
        nextStep({
          chatId,
          lessonId: currLessonId,
          type: INTERACTION_OUTPUT_TYPE.START,
          val: '',
        });
        return;
      }

      let lesson_id = 0;
      records.forEach((v, i) => {
        if (v.script_type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
          const newMessage = convertMessage({
            script_role: '',
          });
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

      if (ui) {
        const nextInputModal = convertEventInputModal(ui);
        setInputDisabled(false);
        setInputModal(nextInputModal);
      }

      setLoadedData(true);
    };

    useEffect(() => {
      if (!loadedData) {
        return;
      }
      const inner = document.querySelector(
        `.${styles.chatComponents} .PullToRefresh-inner`
      );
      document
        .querySelector(`.${styles.chatComponents} .PullToRefresh`)
        .scrollTo(0, inner.clientHeight);
      setLoadedData(false);
    }, [loadedData]);

    useEffect(() => {
      if (!loaded) {
        return;
      }
      (async () => {
        await resetAndLoadData();
      })();
    }, [chapterId]);

    useEffect(() => {
      // 在聊天内登录，不重新加载数据
      if ((hasLogin && loginInChat) || !loaded) {
        return;
      }

      (async () => {
        await resetAndLoadData();
      })();
    }, [hasLogin]);

    useEffect(() => {
      if (loaded) {
        return;
      }
      (async () => {
        await resetAndLoadData();
        setLoaded(true);
      })();
    }, [loaded]);

    const lessonUpdateResp = (response, isEnd) => {
      const content = response.content;
      lessonUpdate?.({
        id: content.lesson_id,
        name: content.lesson_name,
        status: content.status,
      });

      if (content.status === LESSON_STATUS.PREPARE_LEARNING && !isEnd) {
        nextStep({
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
    };

    const nextStep = ({ chatId, lessonId, val, type, scriptId }) => {
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
          } else if (response.type === RESP_EVENT_TYPE.BUTTONS) {
            if (isEnd) {
              return;
            }
            const model = convertEventInputModal(response);
            setInputModal(model);
            setInputDisabled(false);
          } else if (response.type === RESP_EVENT_TYPE.LESSON_UPDATE) {
            lessonUpdateResp(response, isEnd);
          } else if (response.type === RESP_EVENT_TYPE.ORDER) {
            setInputModal(convertEventInputModal(response));
            setInputDisabled(false);
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
            checkLogin();
          } else if (response.type === RESP_EVENT_TYPE.PROFILE_UPDATE) {
            const content = response.content;
            updateUserInfo({ [content.key]: content.value });
          }
        } catch (e) {}
      });
    };

    const handleSend = async (type, val, scriptId) => {
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

        if (type === INTERACTION_OUTPUT_TYPE.CHECKCODE) {
          setLoginInChat(true);
        }
      }

      setTyping(true);
      setInputDisabled(true);
      nextStep({ chatId, lessonId, type, val, scriptId });
    };

    const renderMessageContent = (msg) => {
      const { content, type } = msg;
      if (type === CHAT_MESSAGE_TYPE.LESSON_SEPARATOR) {
        return <div>less</div>;
      }
      if (content === undefined) {
        return <></>;
      }
      if (type === CHAT_MESSAGE_TYPE.TEXT) {
        return <MarkdownBubble content={content} isStreaming={isStreaming} mobileStyle={mobileStyle} />;
      }
      return <></>;
    };

    useImperativeHandle(ref, () => ({}));

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
        await testPurchaseOrder({ orderId: val.orderId });
        setInputDisabled(true);
        onPurchased?.();
        return;
      }

      handleSend(type, val, scriptId);
    };

    return (
      <div
        className={classNames(
          styles.chatComponents,
          className,
          mobileStyle ? styles.mobile : ''
        )}
      >
        <ChatMobileHeader className={styles.ChatMobileHeader} />
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
      </div>
    );
  }
);

export default ChatComponents;
