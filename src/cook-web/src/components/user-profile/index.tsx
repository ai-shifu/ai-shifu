"use client"
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { ChevronUpIcon, HeartIcon, LogOut } from "lucide-react";
import Social from "../social";
import { useEffect, useState } from "react";
import api from '@/api'
import { useTranslation } from 'react-i18next';
import LanguageSelect from '@/components/language-select';
import i18n from '@/i18n';
import { useUserStore } from '@/c-store/useUserStore';



const UserProfileCard = () => {
    const { t } = useTranslation();
    const [language, setLanguage] = useState<string>(i18n.language);
    const { logout, userInfo, isInitialized } = useUserStore();

    const normalizeLanguage = (lang: string): string => {
        const supportedLanguages = Object.values(i18n.options.fallbackLng || {}).flat();
        const normalizedLang = lang.replace('_', '-');
        if (supportedLanguages.includes(normalizedLang)) {
            return normalizedLang;
        }
        return 'en-US';
    }

    // Use userInfo from store instead of making API call
    useEffect(() => {
        if (isInitialized && userInfo?.language) {
            const normalizedLang = normalizeLanguage(userInfo.language);
            setLanguage(normalizedLang);
        }
    }, [isInitialized, userInfo?.language]);

    useEffect(() => {
        if (language !== i18n.language) {
            i18n.changeLanguage(language);
        }
    }, [language]);

    if (!isInitialized || !userInfo) {
        return null;
    }


    const updateLanguage = (language: string) => {
        const normalizedLang = normalizeLanguage(language);
        setLanguage(normalizedLang);
        api.updateUserInfo({language: normalizedLang});
    }





    const userMenuItems: { icon: React.ReactNode, label: string, href: string, id?: string }[] = [
        { icon: <HeartIcon className="w-4 h-4" />, id: 'follow', label: t('common.follow'), href: "#" },
    ];

    return (
        <Popover>
            <PopoverTrigger asChild>
                <div className="flex items-center space-x-2 p-2 rounded-lg hover:bg-gray-100 cursor-pointer transition-all duration-200 group">
                    <Avatar>
                        <AvatarImage src="https://github.com/shadcn.png" />
                        <AvatarFallback>CN</AvatarFallback>
                    </Avatar>
                    <div className="flex-1">
                        <div className="font-medium">
                            {userInfo.name}
                        </div>
                        <div className="text-sm text-gray-500">
                            {userInfo.email}
                        </div>
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
                        <div className="font-medium">
                            {userInfo.name}
                        </div>
                        <div className="text-sm text-gray-500">
                            {userInfo.email}
                        </div>
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
                    <LanguageSelect  language={language} onSetLanguage={updateLanguage} variant='standard' />
                </div>
                <hr />
                <div
                    onClick={() => {
                        logout()
                    }}
                    className="flex items-center space-x-2 px-3 py-2 rounded-lg hover:bg-gray-100 cursor-pointer"
                >
                    <LogOut className="w-4 h-4" />
                    <span>{t('common.logout')}</span>
                </div>
            </PopoverContent>
        </Popover>
    )
};

export default UserProfileCard
