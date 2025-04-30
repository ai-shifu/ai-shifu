/** inject Video to mc-editor */
import Button from '@/components/button';
import { Input } from '@/components/ui/input';
import React, { useState, useRef, useEffect } from 'react';

type VideoInjectProps = {
  onSelect: (resourceUrl: string) => void;
};

const VideoInject: React.FC<VideoInjectProps> = ({ onSelect }) => {
  const [inputUrl, setInputUrl] = useState('');
  const [embedUrl, setEmbedUrl] = useState('');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const lastUrlRef = useRef('');
  const [errorTips, setErrorTips] = useState('');

  const isValidBilibiliUrl = (url: string) => {
    return /^(https?:\/\/)?(www\.)?bilibili\.com\/video\/[a-zA-Z0-9]+/.test(
      url,
    );
  };

  const generateEmbedUrl = (url: string) => {
    const encoded = encodeURIComponent(url);
    return `https://if-cdn.com/api/iframe?url=${encoded}&key=a68bac8b6624d46b6d0ba46e5b3f8971`;
  };

  const handleRun = () => {
    if (!isValidBilibiliUrl(inputUrl)) {
      setErrorTips('⚠️ 请输入有效的B站视频地址');
      return;
    }

    const newEmbedUrl = generateEmbedUrl(inputUrl);

    if (lastUrlRef.current === newEmbedUrl) {
      checkVideoPlayback();
      return;
    }

    setEmbedUrl(newEmbedUrl);
    lastUrlRef.current = newEmbedUrl;
  };

  const handleSelect = () => {
    if (embedUrl) {
      onSelect(embedUrl);
    }
  };

  const checkVideoPlayback = () => {
    if (!iframeRef.current) return;
  };

  useEffect(() => {
    if (embedUrl) {
      setTimeout(checkVideoPlayback, 2000);
    }
  }, [embedUrl]);

  return (
    <div>
      <div className="flex items-center space-x-2">
        <Input
          type="text"
          value={inputUrl}
          onChange={(e) => setInputUrl(e.target.value?.trim())}
          placeholder="请输入B站视频地址"
          autoComplete="off"
        />
        <Button className="h-8" onClick={handleRun}>
          运行
        </Button>
        {embedUrl && (
          <Button className="h-8" onClick={handleSelect}>
            使用资源
          </Button>
        )}
      </div>
      {!!errorTips && <div>{errorTips}</div>}

      {embedUrl && (
        <div
          style={{ position: 'relative', paddingTop: '56.25%', marginTop: 16 }}
        >
          <iframe
            ref={iframeRef}
            src={embedUrl}
            style={{
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              position: 'absolute',
              border: 0,
            }}
            allowFullScreen
            allow="autoplay; encrypted-media"
            title="bilibili-video"
          />
        </div>
      )}
    </div>
  );
};

export default VideoInject;
