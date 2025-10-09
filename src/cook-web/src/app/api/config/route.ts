import { NextRequest, NextResponse } from 'next/server';
import { environment } from '@/config/environment';

export async function GET(request: NextRequest) {
  const origin = request.nextUrl.origin;

  const config = {
    // ===== Core API Configuration =====
    apiBaseUrl: environment.apiBaseUrl,

    // ===== Course Configuration =====
    courseId: environment.courseId,

    // ===== WeChat Integration =====
    wechatAppId: environment.wechatAppId,
    enableWechatCode: environment.enableWechatCode,

    // ===== UI Configuration =====
    alwaysShowLessonTree: environment.alwaysShowLessonTree,
    logoHorizontal: environment.logoHorizontal,
    logoVertical: environment.logoVertical,

    // ===== Analytics =====
    umamiScriptSrc: environment.umamiScriptSrc,
    umamiWebsiteId: environment.umamiWebsiteId,

    // ===== Development Tools =====
    enableEruda: environment.enableEruda,

    // ===== Authentication =====
    loginMethodsEnabled: environment.loginMethodsEnabled,
    defaultLoginMethod: environment.defaultLoginMethod,
    googleOauthRedirect: `${origin.replace(/\/$/, '')}/login/google-callback`,
  };

  return NextResponse.json(config);
}
