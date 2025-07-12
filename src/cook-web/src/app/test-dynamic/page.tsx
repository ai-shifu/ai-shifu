'use client';

import { useEffect, useState } from 'react';
import { getDynamicApiBaseUrl } from '@/config/environment';
import http from '@/lib/request';

export default function TestDynamicPage() {
  const [dynamicApiUrl, setDynamicApiUrl] = useState<string>('');
  const [apiResult, setApiResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 测试动态获取API基础URL
    const testDynamicApiUrl = async () => {
      try {
        const apiUrl = await getDynamicApiBaseUrl();
        setDynamicApiUrl(apiUrl);
      } catch (err: any) {
        setError(err.message || '获取动态API地址失败');
      }
    };

    testDynamicApiUrl();
  }, []);

  const testApiCall = async () => {
    setLoading(true);
    setError(null);
    try {
      // 测试API调用
      const result = await http.get('/user/info');
      setApiResult(result);
    } catch (err: any) {
      setError(err.message || 'API调用失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">动态API基础URL测试</h1>

      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold">动态获取的API基础URL</h2>
          <p className="text-sm text-gray-600">{dynamicApiUrl || '加载中...'}</p>
        </div>

        <div>
          <button
            onClick={testApiCall}
            disabled={loading}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? '请求中...' : '测试 /user/info API'}
          </button>
        </div>

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
            <strong>错误:</strong> {error}
          </div>
        )}

        {apiResult && (
          <div>
            <h2 className="text-lg font-semibold mb-2">API响应结果:</h2>
            <pre className="bg-gray-100 p-4 rounded text-sm overflow-auto">
              {JSON.stringify(apiResult, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
