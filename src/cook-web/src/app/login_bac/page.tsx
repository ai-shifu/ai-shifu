"use client"
import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import Button from '@/components/button';
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline'
import Image from "next/image";
import api from '@/api'
import { setToken } from '@/local/local';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';


interface UserInfo {
    email: string;
    language: string;
    mobile: string;
    name: string;
    user_avatar: string;
    user_id: string;
    user_state: string;
    username: string;
}

interface Response {
    token: string;
    userInfo: UserInfo;
}


const LoginPage = () => {
    const { t } = useTranslation();
    const [showPassword, setShowPassword] = React.useState(false);
    const [formData, setFormData] = React.useState({
        username: '',
        password: ''
    });
    const [errors, setErrors] = React.useState({
        username: '',
        password: ''
    });

    const router = useRouter();
    const validateUsername = (username: string) => {
        if (!username.trim()) {
            return t("login.username-not-empty");
        }
        return '';
    };

    const validatePassword = (password: string) => {
        if (password.length < 8) {
            return t("login.password-length-at-least-8");
        }
        if (!/[A-Za-z]/.test(password)) {
            return t("login.password-must-contain-letters");
        }
        if (!/[0-9]/.test(password)) {
            return t("login.password-must-contain-numbers");
        }
        if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
            return t("login.password-must-contain-special-characters");
        }
        return '';
    };

    const handleSubmit = async (e: React.MouseEvent<HTMLButtonElement, MouseEvent>) => {
        e.preventDefault();
        const usernameError = validateUsername(formData.username);
        const passwordError = validatePassword(formData.password);

        setErrors({
            username: usernameError,
            password: passwordError
        });

        if (!usernameError && !passwordError) {
            await onLogin();
        }
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));

        // Real-time validation
        if (name === 'username') {
            setErrors(prev => ({
                ...prev,
                username: validateUsername(value)
            }));
        } else if (name === 'password') {
            setErrors(prev => ({
                ...prev,
                password: validatePassword(value)
            }));
        }
    };
    const onLogin = async () => {
        const result: Response = await api.login({
            username: formData.username,
            password: formData.password
        });
        const token = result.token;
        setToken(token);

        router.push('/main');

    }

    return (
        <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6">
            <div className="w-full max-w-md space-y-2">
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
                        <form className="space-y-6">
                            <div className="space-y-1">
                                <Label htmlFor="username">{t("login.username")}</Label>
                                <div className="space-y-1">
                                    <Input
                                        autoComplete='off'
                                        id="username"
                                        name="username"
                                        placeholder={t("login.username-placeholder")}
                                        value={formData.username}
                                        onChange={handleChange}
                                        className={errors.username ? "border-red-500" : ""}
                                    />
                                    {errors.username && (
                                        <p className="text-red-500 text-sm">{errors.username}</p>
                                    )}
                                </div>
                            </div>

                            <div className="space-y-1">
                                <div className="flex justify-between items-center">
                                    <Label htmlFor="password">{t("login.password")}</Label>
                                    {/* <Button
                                        variant="link"
                                        className="px-0 text-sm text-gray-500 hover:text-purple-500"
                                    >
                                        忘记密码?
                                    </Button> */}
                                </div>
                                <div className="relative">
                                    <div className="space-y-1">
                                        <Input
                                            id="password"
                                            name="password"
                                            type={showPassword ? "text" : "password"}
                                            value={formData.password}
                                            onChange={handleChange}
                                            className={errors.password ? "border-red-500" : ""}
                                        />
                                        {errors.password && (
                                            <p className="text-red-500 text-sm">{errors.password}</p>
                                        )}
                                    </div>
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        className="absolute right-0 top-0 h-8 px-3 hover:bg-transparent"
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

                            <Button
                                onClick={handleSubmit}
                                className="w-full bg-purple-600 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                disabled={!!errors.username || !!errors.password || !formData.username || !formData.password}
                            >
                                {t("login.login")}
                            </Button>

                            <div className="text-center  text-stone-900 text-base">
                                {t("login.want-to-experience-creation")} <a className='underline cursor-pointer hover:text-purple-500' href="http://">{t("login.apply-for-admission")}</a>
                            </div>
                        </form>
                    </CardContent>
                </Card>
                <div className="text-xs text-stone-500 text-center">
                    {t("login.click-login-to-represent-you-have-agreed-to")}
                    <a className="px-1 text-xs text-stone-900 underline cursor-pointer hover:text-purple-500" href="/privacy">
                        {t("login.user-agreement")}
                    </a>
                    {t("login.and")}
                    <a className="px-1 text-xs text-stone-900 underline cursor-pointer hover:text-purple-500" href="/agreement">
                        {t("login.service-agreement")}
                    </a>
                </div>
            </div>
        </div>
    );
};

export default LoginPage;
