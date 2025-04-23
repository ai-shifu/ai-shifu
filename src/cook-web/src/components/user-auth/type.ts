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

interface LoginResponse {
    token: string;
    userInfo: UserInfo;
}

export type {
    UserInfo,
    LoginResponse
}