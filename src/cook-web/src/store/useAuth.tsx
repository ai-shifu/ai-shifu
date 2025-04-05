import React, { createContext, useContext, useState, ReactNode } from "react";

export type AuthContextType = {
    profile: any;
    actions: {
        setProifle: (profile: any) => void;
    }
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [profile, setProifle] = useState(null);


    // console.log(blockContentProperties)
    // console.log(blockUIProperties)
    const value: AuthContextType = {
        profile,
        actions: {
            setProifle
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
