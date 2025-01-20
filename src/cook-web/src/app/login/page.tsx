"use client"
import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline'
import Image from "next/image";

const LoginPage = () => {
    const [showPassword, setShowPassword] = React.useState(false);
    const [formData, setFormData] = React.useState({
        username: '',
        password: ''
    });

    const handleSubmit = (e) => {
        e.preventDefault();
        console.log('Login attempt:', formData);
    };

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));
    };

    return (
        <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6">
            <div className="w-full max-w-md space-y-6">
                <div className="flex flex-col items-center space-y-2">
                    <h2 className="text-purple-600 text-2xl flex items-center font-semibold">
                        <Image
                            className="dark:invert"
                            src="/logo.svg"
                            alt="AI-Shifu"
                            width={140}
                            height={30}
                            priority
                        />
                    </h2>
                </div>
                <Card>
                    <CardHeader>
                        <CardTitle className="text-xl text-center text-stone-900  font-extrabold">登录制课中心</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <form onSubmit={handleSubmit} className="space-y-6">
                            <div className="space-y-2">
                                <Label htmlFor="username">账号</Label>
                                <Input
                                    id="username"
                                    name="username"
                                    placeholder="请输入邮箱/手机号"
                                    value={formData.username}
                                    onChange={handleChange}
                                />
                            </div>

                            <div className="space-y-2">
                                <div className="flex justify-between items-center">
                                    <Label htmlFor="password">密码</Label>
                                    <Button
                                        variant="link"
                                        className="px-0 text-sm text-gray-500 hover:text-purple-500"
                                    >
                                        忘记密码?
                                    </Button>
                                </div>
                                <div className="relative">
                                    <Input
                                        id="password"
                                        name="password"
                                        type={showPassword ? "text" : "password"}
                                        value={formData.password}
                                        onChange={handleChange}
                                    />
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                                        onClick={() => setShowPassword(!showPassword)}
                                    >
                                        {showPassword ? (
                                            <EyeSlashIcon className="h-4 w-4 text-gray-500" />
                                        ) : (
                                            <EyeIcon className="h-4 w-4 text-gray-500" />
                                        )}
                                    </Button>
                                </div>
                            </div>

                            <Button type="submit" className="w-full bg-purple-600 hover:bg-purple-700">
                                登录
                            </Button>

                            <div className="text-center  text-stone-900 text-base">
                                想要体验创作？ <a className='underline cursor-pointer hover:text-purple-500' href="http://">申请入驻</a>
                            </div>
                        </form>
                    </CardContent>
                </Card>
                <div className="text-xs text-stone-500 text-center">
                    点击登录即代表您已同意
                    <a className="px-1 text-xs text-stone-900 underline cursor-pointer hover:text-purple-500">
                        用户协议
                    </a>
                    和
                    <a className="px-1 text-xs text-stone-900 underline cursor-pointer hover:text-purple-500">
                        服务协议
                    </a>
                </div>
            </div>
        </div>
    );
};

export default LoginPage;
