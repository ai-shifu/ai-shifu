import styles from './MarkdownBubble.module.scss';

import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

import { Bubble } from '../ForkChatUI/components/Bubble';

// import { Image } from 'antd';

import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import classNames from 'classnames';

import CopyButton from './CopyButton';

export const MarkdownBubble = (props) => {
  const { mobileStyle, onImageLoaded } = props;

  const onCopy = (content) => {
    navigator.clipboard.writeText(content);
  };

  return (
    <>
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
                  <CopyButton content={children} />
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
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  {...imgProps}
                  src={imgProps.src}
                  alt={imgProps.alt || ''}
                  width={imgProps.style?.width || '100%'}
                  // preview={!props.isStreaming}
                  style={{ borderRadius: '5px' }}
                  onLoad={onImageLoaded}
                />
              );
            },
          }}
        />
      </Bubble>
    </>
  );
};

export default memo(MarkdownBubble);
