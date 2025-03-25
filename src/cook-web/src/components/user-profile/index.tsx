"use client"
import { ArrowRightOnRectangleIcon, ChatBubbleLeftRightIcon, PencilSquareIcon } from "@heroicons/react/24/outline";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { ChevronUpIcon, HeartIcon, MapIcon, MegaphoneIcon, ShieldCheckIcon } from "lucide-react";
import Social from "../social";
import { useEffect, useState } from "react";
import api from '@/api'


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


const UserProfileCard = () => {
    const [profile, setProfile] = useState(null);
    const init = async () => {
        const res = await api.getProfile({});
        setProfile(res.data);
    }
    useEffect(() => {
        init();
    }, [])
    return (
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
    )
};

export default UserProfileCard
