import Chat, {
  Bubble,
  useMessages,
  Empty,
  Card,
  CardTitle,
  CardActions,
} from '@chatui/core';
import { Button } from 'antd';
import { Image } from 'antd';

import '@chatui/core/dist/index.css';
import './chatui-theme.css';
import '../../App.css';
import React, { forwardRef, useImperativeHandle } from 'react';
import { runScript } from '../../Api/study';
import { UploadEvent } from '../../Api/UploadEvent';
import ReactMarkdown from 'react-markdown';

import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { CopyOutlined } from '@ant-design/icons';
import { getLessonStudyRecord } from '../../Api/study';

const generateUUID = () => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    var r = (Math.random() * 16) | 0,
      v = c == 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};
const quickOperstionList = [];


const MarkdownBubble = (props) => {
  const onCopy = (content) => {
    console.log(content);
    navigator.clipboard.writeText(content).then((res) => {});
  };
  return (
    <Bubble>
      <ReactMarkdown
        children={props.content}
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
                  showLineNumbers={true}
                  wrapLines={false}
                  onCopy={() => {
                    onCopy(children);
                  }}
                  renderInline={true}
                ></SyntaxHighlighter>
              </div>
            ) : (
              <code {...props} className={className}>
                {children}
              </code>
            );
          },
          img(props) {
            return <Image {...props} width={400} style="width:100%" preview={false}></Image>;
          },
        }}
      ></ReactMarkdown>
    </Bubble>
  );
};

const ChatComponents = forwardRef(
  ({ onTitleUpdate, className, lessonStatusUpdate }, ref) => {
    const { messages, appendMsg, setTyping, updateMsg, resetList } =
      useMessages([]);
    const [chatId, setChatId] = React.useState('');
    const [scriptId, setScriptId] = React.useState('');
    const [inputPlaceholder, setInputPlaceholder] = React.useState('请输入');
    const [inputDisabled, setInputDisabled] = React.useState(true);
    const [lessonId, setLessonId] = React.useState('');

    function handleSend(type, val) {
      console.log('handle send', type, val);
      let sendScriptId = scriptId;
      if (type === 'text' && val.trim()) {
        appendMsg({
          _id: generateUUID(),
          type: 'text',
          content: { type: 'text', text: val },
          position: 'right',
        });
        UploadEvent('ChatInput', {
          text_length: val.length,
          page: 'chat',
        });
      } else if (type === 'button') {
        sendScriptId = undefined;
      }
      setTyping(true);
      let lastMsg = null;
      runScript(chatId, lessonId, val, type, (response) => {
        try {
          setChatId(response.chat_id);
          let id = generateUUID();
          if (lastMsg !== null && lastMsg.content.type === 'calling') {
            lastMsg.content.isProcessed = true;
            updateMsg(lastMsg._id, lastMsg);
          }
          if (response.type === 'calling') {
            lastMsg = {
              content: {
                function_name: response.function_name,
                type: response.type,
                isProcessed: false,
              },
              _id: id,
            };
            appendMsg(lastMsg);
            UploadEvent('CallingRunning', {
              page: 'chat',
              function_name: response.function_name,
            });
          } else if (response.type === 'text') {
            console.log('lastmsg', lastMsg);
            if (lastMsg !== null && lastMsg.content.type === 'text') {
              lastMsg.content.text = lastMsg.content.text + response.content;
              updateMsg(lastMsg._id, lastMsg);
            } else {
              lastMsg = {
                _id: id,
                type: response.type,
                content: {
                  type: response.type,
                  text: response.content,
                },
                position: 'left',
                user: { avatar: require('../../Assets/chat/sunner_icon.jpg') },
              };
              appendMsg(lastMsg);
            }
          } else if (response.type === 'text_end') {
            lastMsg = null;
          } else if (response.type === 'input') {
            setInputPlaceholder(response.content);
            setScriptId(response.id);
            setInputDisabled(false);
          } else if (response.type === 'button') {
            lastMsg = {
              _id: id,
              type: 'card',
              content: response.content,
              position: 'right',
            };
            appendMsg(lastMsg);
            setInputDisabled(true);
          } else if (response.type === 'buttons') {
            console.log(response);
            lastMsg = {
              _id: id,
              type: 'card',
              content: response.content,
              position: 'right',
            };
            appendMsg(lastMsg);
            setInputDisabled(true);
          } else if (response.type === 'study_complete') {
            // setLessonId(response.lesson_id);
          } else if (response.type === 'lesson_update') {
            if (lessonStatusUpdate) {
              lessonStatusUpdate(response.content);
            }
          }
        } catch (e) {
          // console.log("error", e);
        }
      });
    }

    function onButtonClick(type, content) {
      handleSend(type, content);
    }
    function renderMessageContent(msg) {
      const { content } = msg;
      if (content === undefined) {
        return null;
      }
      if (content.type === 'calling') {
        return (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '10px',
              borderRadius: '5px',
              fontWeight: 'bold',
              minWidth: '25%',
              backgroundColor: '#f7f8fa',
            }}
          >
            <div>
              <div
                style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
              >
                <img
                  style={{ display: content.isProcessed ? 'block' : 'none' }}
                  src={require('../../Assets/success_chat.png')}
                  alt=""
                />
                <img
                  className="chat_loading"
                  style={{ display: content.isProcessed ? 'none' : 'block' }}
                  src={require('../../Assets/loading_chat.png')}
                  alt=""
                />
                {content.isProcessed
                  ? '操作执行完成'
                  : `正在执行操作:“${content.function_name}”`}
              </div>
            </div>
          </div>
        );
      } else if (content.type === 'text') {
        return <MarkdownBubble content={content.text} />;
      } else if (content.type === 'init') {
      } else if (msg.type === 'card') {
        const type = content.buttons.length > 1 ? 'select' : 'continue';
        return (
          <Bubble>
            <Card size="xl">
              <CardTitle>{content.title}</CardTitle>
              <CardActions>
                {content.buttons.map((btn) => {
                  return (
                    <Button onClick={() => onButtonClick(type, btn.value)}>
                      {btn.label}
                    </Button>
                  );
                })}
              </CardActions>
            </Card>
          </Bubble>
        );
      }
      return null;
    }

    function loadMsg(chatId, newMessages) {
      resetList();
      if (newMessages === undefined || newMessages === null) {
        return;
      }

      newMessages.forEach((item) => {
        if (item.script_role === '学生') {
          appendMsg({
            _id: generateUUID(),
            type: 'text',
            content: { type: 'text', text: item.script_content },
            position: 'right',
          });
        } else {
          if (item.function_call) {
            appendMsg({
              content: {
                function_name: item.function_call,
                type: 'calling',
                isProcessed: true,
              },
              _id: generateUUID(),
            });
          } else {
            appendMsg({
              _id: generateUUID(),
              type: 'text',
              content: { type: 'text', text: item.script_content },
              position: 'left',
              user: { avatar: require('../../Assets/chat/sunner_icon.jpg') },
            });
          }
        }
      });
    }
    function checkResetListComplete() {
      return new Promise((resolve) => {
        const intervalId = setInterval(() => {
          if (
            messages !== undefined &&
            messages !== null &&
            messages.length === 0
          ) {
            clearInterval(intervalId);
            resolve();
          }
        }, 100);
      });
    }
    const switchLesson = (lessonInfo) => {
      console.log('switch Lesson', lessonInfo);
      setLessonId(lessonInfo.lesson_id);
      setChatId(lessonInfo.course_id);
      if (lessonInfo.status === '未开始') {
        // loadMsg(lessonInfo.lesson_id, [])

        // checkResetListComplete().then(()=>{
        handleSend('start', '');
        // })
      } else {
        getLessonStudyRecord(lessonInfo.lesson_id).then((res) => {
          // console.log("getLessonStudyRecord", res);
          loadMsg(lessonInfo.lesson_id, res.data);
        });
      }
    };
    useImperativeHandle(ref, () => ({
      loadMsg,
      switchLesson,
    }));

    function renderBeforeMessageList() {
      // message 的长度等于 0 的时候 返回 Empty 组件
      if (messages.length === 0) {
        return (
          <div
            className="full-height chat-ui_container"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Empty
              className="chatui_empty"
              children={
                <div className="empty_header">
                  <div className="title">
                    <img
                      className="logo"
                      src={require('../../Assets/chat/img8.png')}
                      alt=""
                    />
                    <div className="system-name"></div>
                  </div>
                  <div className="slogan">AI私教</div>
                </div>
              }
            ></Empty>
          </div>
        );
      }
    }
    return (
      <Chat
        navbar={{ title: '和AI学Python' }}
        messages={messages}
        renderMessageContent={renderMessageContent}
        onSend={handleSend}
        loadMsg={loadMsg}
        renderBeforeMessageList={renderBeforeMessageList}
        recorder={{ canRecord: true }}
        placeholder={inputPlaceholder}
        inputOptions={{ disabled: inputDisabled }}
      />
    );
  }
);

export default ChatComponents;
