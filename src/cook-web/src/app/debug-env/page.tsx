'use client';

import { environment } from '@/config/environment';
import { useEffect, useState } from 'react';

export default function DebugEnvPage() {
  const [isClient, setIsClient] = useState(false);
  const [envData, setEnvData] = useState<any>(null);

  useEffect(() => {
    setIsClient(true);

    // 获取环境变量数据
    const fetchEnvData = async () => {
      try {
        const response = await fetch('/api/env', {
          method: 'POST',
        });
        if (response.ok) {
          const data = await response.json();
          setEnvData(data);
        }
      } catch (error) {
        console.error('Failed to fetch env data:', error);
      }
    };

    fetchEnvData();
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">环境变量调试</h1>

      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold mb-2">Environment 模块</h2>
          <div className="bg-gray-100 p-4 rounded">
            <p><strong>apiBaseUrl:</strong> {environment.apiBaseUrl}</p>
            <p><strong>courseId:</strong> {environment.courseId}</p>
            <p><strong>wechatAppId:</strong> {environment.wechatAppId}</p>
            <p><strong>enableWechatCode:</strong> {environment.enableWechatCode.toString()}</p>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">运行时环境变量</h2>
          <div className="bg-gray-100 p-4 rounded">
            <p><strong>NEXT_PUBLIC_API_BASE_URL:</strong> {process.env.NEXT_PUBLIC_API_BASE_URL || '未设置'}</p>
            <p><strong>NEXT_PUBLIC_DEFAULT_COURSE_ID:</strong> {process.env.NEXT_PUBLIC_DEFAULT_COURSE_ID || '未设置'}</p>
            <p><strong>NEXT_PUBLIC_WECHAT_APP_ID:</strong> {process.env.NEXT_PUBLIC_WECHAT_APP_ID || '未设置'}</p>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">API 环境变量数据</h2>
          <div className="bg-gray-100 p-4 rounded">
            {envData ? (
              <pre className="text-sm overflow-auto">
                {JSON.stringify(envData, null, 2)}
              </pre>
            ) : (
              <p>加载中...</p>
            )}
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">运行环境</h2>
          <div className="bg-gray-100 p-4 rounded">
            <p><strong>是否客户端:</strong> {isClient ? '是' : '否'}</p>
            <p><strong>当前URL:</strong> {typeof window !== 'undefined' ? window.location.href : 'N/A'}</p>
            <p><strong>当前域名:</strong> {typeof window !== 'undefined' ? window.location.hostname : 'N/A'}</p>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">测试API请求</h2>
          <button
            onClick={async () => {
              try {
                const response = await fetch('/api/config');
                const data = await response.json();
                alert(`API配置: ${JSON.stringify(data, null, 2)}`);
              } catch (error) {
                alert(`API请求失败: ${error}`);
              }
            }}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            测试 /api/config
          </button>
        </div>
      </div>
    </div>
  );
}
