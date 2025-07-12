import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/toaster"
import { AlertProvider } from '@/components/ui/use-alert';
import "./globals.css";
import '@/assets/css/md-editor.css';
import '@/assets/css/markdown.css';
import { ConfigProvider } from '@/components/config-provider';
import { UserProvider } from '@/c-store/userProvider';
import '@/i18n';

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased overflow-hidden`}
      >
        <ConfigProvider>
          <UserProvider>
            <AlertProvider>
              {children}
              <Toaster />
            </AlertProvider>
          </UserProvider>
        </ConfigProvider>
      </body>
    </html>
  );
}
