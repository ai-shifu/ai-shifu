import { Geist, Geist_Mono } from 'next/font/google';
import { Toaster } from '@/components/ui/Toaster';
import { AlertProvider } from '@/components/ui/UseAlert';
import './globals.css';
import { ConfigProvider } from '@/components/config-provider';
import UmamiLoader from '@/components/analytics/UmamiLoader';
import RuntimeConfigInitializer from '@/components/RuntimeConfigInitializer';
import { UserProvider } from '@/store';
import '@/i18n';
import I18nGlobalLoading from '@/components/I18nGlobalLoading';
import 'markdown-flow-ui/dist/markdown-flow-ui.css';
// fix: dont't use, it will cause logo in dark mode is not blue
// import 'markdown-flow-ui/dist/markdown-flow-ui-lib.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang='en'>
      <head>
        <script
          // Inline guard to block iOS <=15 before the app bundles execute
          dangerouslySetInnerHTML={{
            __html: `(() => {
  try {
    const ua = navigator.userAgent || '';
    const isIOS = /iP(hone|od|ad)/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const match = ua.match(/OS (\d+)[._]/i);
    const major = match ? parseInt(match[1], 10) : 0;

    const showNotice = () => {
      const container = document.createElement('div');
      container.setAttribute('style', 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:#fff;');
      container.innerHTML = '<div style="padding:16px 20px;border:1px solid #e5e5e5;border-radius:12px;text-align:center;font-size:15px;color:#111;max-width:320px;line-height:1.5;">' +
        '<div style="font-weight:600;margin-bottom:8px;">系统版本过低</div>' +
        '<div>当前 iOS 版本不支持，请升级到最新版本（>=16）再访问。</div>' +
        '</div>';
      document.body.innerHTML = '';
      document.body.appendChild(container);
    };

    const shouldBlock = isIOS && major > 0 && major <= 15;
    if (shouldBlock) {
      showNotice();
      window.stop?.();
    }

    const attachErrorNotice = () => {
      const handler = () => {
        if (shouldBlock) {
          showNotice();
        }
      };
      window.addEventListener('error', handler);
      window.addEventListener('unhandledrejection', handler);
    };

    attachErrorNotice();
  } catch (_) {
    // Fail silently to avoid blocking rendering on unexpected errors
  }
})();`,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} overflow-hidden`}
      >
        <div id='root'>
          <ConfigProvider>
            <RuntimeConfigInitializer />
            <UmamiLoader />
            <UserProvider>
              <AlertProvider>
                <I18nGlobalLoading />
                {children}
                <Toaster />
              </AlertProvider>
            </UserProvider>
          </ConfigProvider>
        </div>
      </body>
    </html>
  );
}
