import { NextRequest, NextResponse } from 'next/server';

const MIN_IOS_MAJOR = 16;
const MIN_IOS_MINOR = 4;

const IOS_OS_VERSION_PATTERN = /OS (\d+)[._](\d+)(?:[._](\d+))?/i;
const SAFARI_VERSION_PATTERN = /Version\/(\d+)\.(\d+)(?:\.(\d+))?/i;

const isIosWebKit = (userAgent: string): boolean => {
  if (/iPhone|iPad|iPod/i.test(userAgent)) {
    return true;
  }

  // iPadOS 13+ can report itself as Macintosh while still being iOS WebKit.
  return /Macintosh/i.test(userAgent) && /Mobile/i.test(userAgent);
};

const parseIosVersion = (userAgent: string): [number, number] | null => {
  const osMatch = userAgent.match(IOS_OS_VERSION_PATTERN);
  if (osMatch) {
    return [
      Number.parseInt(osMatch[1], 10) || 0,
      Number.parseInt(osMatch[2], 10) || 0,
    ];
  }

  const safariMatch = userAgent.match(SAFARI_VERSION_PATTERN);
  if (safariMatch) {
    return [
      Number.parseInt(safariMatch[1], 10) || 0,
      Number.parseInt(safariMatch[2], 10) || 0,
    ];
  }

  return null;
};

const isSupportedIosVersion = (major: number, minor: number): boolean => {
  if (major > MIN_IOS_MAJOR) {
    return true;
  }
  if (major < MIN_IOS_MAJOR) {
    return false;
  }
  return minor >= MIN_IOS_MINOR;
};

export function middleware(request: NextRequest) {
  const userAgent = request.headers.get('user-agent') ?? '';
  if (!isIosWebKit(userAgent)) {
    return NextResponse.next();
  }

  const version = parseIosVersion(userAgent);
  if (!version) {
    return NextResponse.next();
  }

  if (isSupportedIosVersion(version[0], version[1])) {
    return NextResponse.next();
  }

  const redirectUrl = request.nextUrl.clone();
  redirectUrl.pathname = '/unsupported-browser.html';
  redirectUrl.search = '';
  return NextResponse.redirect(redirectUrl);
}

export const config = {
  matcher: ['/c/:path*'],
};
