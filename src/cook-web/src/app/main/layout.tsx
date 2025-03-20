import React from 'react';
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Bars3Icon,
  BookOpenIcon,
  BoltIcon,
  LightBulbIcon,
  ChatBubbleLeftRightIcon,
  ChevronUpIcon,
  ArrowRightOnRectangleIcon,
  HeartIcon,
  MegaphoneIcon,
  DocumentIcon,
  CheckBadgeIcon,
  MapIcon,
  PencilSquareIcon,
  ShieldCheckIcon
} from '@heroicons/react/24/outline';
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import Image from "next/image";
import Link from "next/link";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import Social from '@/components/social'

const MainInterface = ({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) => {
  const menuItems: { type?: string, icon?: React.ReactNode, label?: string, href?: string, id?: string }[] = [
    { icon: <DocumentIcon className="w-4 h-4" />, label: "剧本", href: "/main" },
    { icon: <BookOpenIcon className="w-4 h-4" />, label: "知识库", href: "/main/knowledge" },
    { type: 'divider' },
    { icon: <BoltIcon className="w-4 h-4" />, label: "模版", href: "/main/template" },
    { icon: <LightBulbIcon className="w-4 h-4" />, label: "灵感", href: "/main/inspiration" },
    { icon: <CheckBadgeIcon className="w-4 h-4" />, label: "最佳实践", href: "/main/best-practice" },
  ];

  const userMenuItems: { icon: React.ReactNode, label: string, href: string, id?: string }[] = [
    {
      icon: <PencilSquareIcon className="w-4 h-4" />, label: "个人信息", href: "#"
    },
    { icon: <ShieldCheckIcon className="w-4 h-4" />, label: "安全设置", href: "#" },
    { icon: <MegaphoneIcon className="w-4 h-4" />, label: "最近更新", href: "#" },
    { icon: <MapIcon className="w-4 h-4" />, label: "路线图", href: "#" },
    { icon: <ChatBubbleLeftRightIcon className="w-4 h-4" />, label: "问题反馈", href: "#" },
    { icon: <HeartIcon className="w-4 h-4" />, id: 'follow', label: "关注我们", href: "#" },
  ];

  const UserProfileCard = () => (
    <Popover>
      <PopoverTrigger asChild>
        <div className="flex items-center space-x-2 p-2 rounded-lg hover:bg-gray-100 cursor-pointer transition-all duration-200 group">
          <Avatar>
            <AvatarImage src="https://github.com/shadcn.png" />
            <AvatarFallback>CN</AvatarFallback>
          </Avatar>
          <div className="flex-1">
            <div className="font-medium">Kenrick</div>
            <div className="text-sm text-gray-500">kenrick.zhou@gmail.com</div>
          </div>
          <ChevronUpIcon className="w-4 h-4 text-gray-500 transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </div>
      </PopoverTrigger>
      <PopoverContent side='top' align='start' className="w-64 p-2 border rounded-lg bg-background shadow-md animate-in slide-in-from-bottom-2 duration-200" sideOffset={5}>
        <div className="flex items-center space-x-2 p-2">
          <Avatar>
            <AvatarImage src="https://github.com/shadcn.png" />
            <AvatarFallback>CN</AvatarFallback>
          </Avatar>
          <div>
            <div className="font-medium">Kenrick</div>
            <div className="text-sm text-gray-500">kenrick.zhou@gmail.com</div>
          </div>
        </div>
        <hr />
        <div className="space-y-1">
          {userMenuItems.map((item, index) => {
            if (item.id == 'follow') {
              return (
                <div key={index} className=' relative group'>
                  <a
                    key={index}
                    href={item.href}
                    className="flex items-center space-x-2 px-3 py-2 rounded-lg hover:bg-gray-100"
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </a>
                  {
                    item.id == 'follow' && (
                      <div className=' absolute bottom-0 left-1/2 hidden  group-hover:block  group-hover:animate-in  group-hover:slide-in-from-bottom-2  group-hover:duration-200'>
                        <Social />
                      </div>
                    )
                  }
                </div>
              )
            }
            return (
              <a
                key={index}
                href={item.href}
                className="flex items-center space-x-2 px-3 py-2 rounded-lg hover:bg-gray-100"
              >
                {item.icon}
                <span>{item.label}</span>
              </a>
            )

          })}
        </div>
        <hr />
        <a
          href={'/logout'}
          className="flex items-center space-x-2 px-3 py-2 rounded-lg hover:bg-gray-100"
        >
          <ArrowRightOnRectangleIcon className="w-4 h-4" />
          <span>退出登录</span>
        </a>
      </PopoverContent>
    </Popover>
  );

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
        <UserProfileCard />
      </div>
    </div>
  );

  return (
    <div className="h-screen flex bg-stone-50">
      {/* Desktop Sidebar */}
      <div className="hidden md:flex w-64 border-r flex-col p-2">
        <SidebarContent />
      </div>
      {/* Main Content */}
      <div className="flex-1 p-5">
        <div className="max-w-6xl mx-auto">
          {
            children
          }
        </div>
      </div>

      {/* Mobile Header */}
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
          <h1 className="text-xl font-bold">首页</h1>
          <div className="w-6" /> {/* Spacer for centering */}
        </div>
      </div>
    </div>
  );
};


export default MainInterface
