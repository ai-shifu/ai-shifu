import { Toaster } from '@/components/ui/Toaster';
import { AlertProvider } from '@/components/ui/UseAlert';
import './globals.css';
import { ConfigProvider } from '@/components/config-provider';
import UmamiLoader from '@/components/analytics/UmamiLoader';
import RuntimeConfigInitializer from '@/components/RuntimeConfigInitializer';
import DomReconcilerGuard from '@/components/DomReconcilerGuard';
import { UserProvider } from '@/store/userProvider';
import '@/i18n';
import I18nGlobalLoading from '@/components/I18nGlobalLoading';
import 'markdown-flow-ui/dist/markdown-flow-ui.css';
export { metadata, viewport } from './metadata';
// fix: dont't use, it will cause logo in dark mode is not blue
// import 'markdown-flow-ui/dist/markdown-flow-ui-lib.css';

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang='en'
      translate='no'
    >
      <body className='min-h-screen overflow-x-hidden overscroll-none'>
        <div
          id='root'
          className='min-h-screen'
        >
          <DomReconcilerGuard />
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
