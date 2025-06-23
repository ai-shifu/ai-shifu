import { NextResponse } from 'next/server';

export async function GET() {
  const res = {
    NEXT_PUBLIC_BASEURL: process.env.NEXT_PUBLIC_BASEURL || '/',
    NEXT_PUBLIC_UMAMI_SCRIPT_SRC: process.env.NEXT_PUBLIC_UMAMI_SCRIPT_SRC  || '',
    NEXT_PUBLIC_UMAMI_WEBSITE_ID: process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID || '',
    NEXT_PUBLIC_COURSE_ID: process.env.NEXT_PUBLIC_COURSE_ID || '',
    NEXT_PUBLIC_ALWAYS_SHOW_LESSON_TREE: process.env.NEXT_PUBLIC_ALWAYS_SHOW_LESSON_TREE || false,
    NEXT_PUBLIC_APP_ID: process.env.NEXT_PUBLIC_APP_ID || '',
    NEXT_PUBLIC_ERUDA: process.env.NEXT_PUBLIC_ERUDA || false,
    NEXT_PUBLIC_LOGO_HORIZONTAL: process.env.NEXT_PUBLIC_LOGO_HORIZONTAL || '',
    NEXT_PUBLIC_LOGO_VERTICAL: process.env.NEXT_PUBLIC_LOGO_VERTICAL || '',
    NEXT_PUBLIC_ENABLE_WXCODE: process.env.NEXT_PUBLIC_ENABLE_WXCODE !== undefined ? process.env.NEXT_PUBLIC_ENABLE_WXCODE === 'true' : true,
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL || '/',
  }

  return NextResponse.json(res);
}
