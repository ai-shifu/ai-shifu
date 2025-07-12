import { NextResponse } from 'next/server';
import { environment } from '@/config/environment';

export async function GET() {
  const config = {
    // ===== Core API Configuration =====
    apiBaseUrl: environment.apiBaseUrl,

    // ===== Course Configuration =====
    courseId: environment.courseId,

    // ===== WeChat Integration =====
    wechatAppId: environment.wechatAppId,
    enableWechatCode: environment.enableWechatCode,

    // ===== UI Configuration =====
    alwaysShowLessonTree: environment.alwaysShowLessonTree.toString(),
    logoHorizontal: environment.logoHorizontal,
    logoVertical: environment.logoVertical,

    // ===== Analytics =====
    umamiScriptSrc: environment.umamiScriptSrc,
    umamiWebsiteId: environment.umamiWebsiteId,

    // ===== Development Tools =====
    enableEruda: environment.enableEruda.toString(),
  };

  return NextResponse.json(config);
}
