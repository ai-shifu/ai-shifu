import React, { createContext, useContext, useState, ReactNode, useEffect } from "react";
import api from '@/api';

import { useUserStore } from "@/c-store/useUserStore";

export type AuthContextType = {
    profile: any;
    actions: {
        setProfile: (profile: any) => void;
    }
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [profile, setProfile] = useState(null);
    const updateUserInfo = useUserStore((state) => state.updateUserInfo);
    const _setHasLogin = useUserStore((state) => state._setHasLogin);

    useEffect(() => {
        const fetchProfile = async () => {
            if (!profile) {
                try {
                    const userInfo = await api.getUserInfo({});
                    setProfile(userInfo);
                    updateUserInfo(userInfo)
                    _setHasLogin(true);
                } catch (error) {
                    console.error('Failed to fetch user profile:', error);
                }
            }
        };

        fetchProfile();
    }, [profile]);

    const value: AuthContextType = {
        profile,
        actions: {
            setProfile
        }
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextType => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error("useAuth must be used within a AuthProvider");
    }
    return context;
};

export const useAuthActions = (): AuthContextType['actions'] => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error("useAuth must be used within a AuthProvider");
    }
    return context.actions;
};
