'use client'
import React from 'react';
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Bars3Icon,
  DocumentIcon,
} from '@heroicons/react/24/outline';
import Image from "next/image";
import Link from "next/link";
import UserProfile from '@/components/user-profile';
import { useTranslation } from 'react-i18next';

const MainInterface = ({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) => {
  const { t } = useTranslation();
  const menuItems: { type?: string, icon?: React.ReactNode, label?: string, href?: string, id?: string }[] = [
    { icon: <DocumentIcon className="w-4 h-4" />, label: t('common.shifu'), href: "/main" },
  ];


  const SidebarContent = () => (
    <div className="flex flex-col h-full relative shadow-md rounded-2xl bg-background">
      <h1 className="text-xl font-bold p-4">
        <Image
          className="dark:invert"
          src="/icons/logo.svg"
          alt="AI-Shifu"
          width={140}
          height={32}
          priority
        />
      </h1>
      <div className="p-2 flex-1">
        <nav className="space-y-1">
          {menuItems.map((item, index) => {
            if (item.type == 'divider') {
              return <div key={index} className='h-px bg-gray-200'></div>
            }
            return (
              <Link
                key={index}
                href={item.href || '#'}
                className="flex items-center space-x-2 px-2 py-2 rounded-lg hover:bg-gray-100"
              >
                {item.icon}
                <span>{item.label}</span>
              </Link>
            )
          })}
        </nav>
      </div>

      <div className='p-2 relative'>
        <UserProfile />
      </div>
    </div>
  );

  return (
    <div className="h-screen flex bg-stone-50">
      <div className="hidden md:flex w-64 border-r flex-col p-2">
        <SidebarContent />
      </div>
      <div className="flex-1 p-5  overflow-hidden">
        <div className="max-w-6xl mx-auto h-full overflow-hidden">
          {
            children
          }
        </div>
      </div>
      <div className="md:hidden w-full border-b p-4">
        <div className="flex items-center justify-between">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon">
                <Bars3Icon className="h-6 w-6" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-0">
              <SidebarContent />
            </SheetContent>
          </Sheet>
          <h1 className="text-xl font-bold">{t('common.home')}</h1>
          <div className="w-6" /> {/* Spacer for centering */}
        </div>
      </div>
    </div>
  );
};


export default MainInterface
