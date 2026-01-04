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
      <head></head>
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
