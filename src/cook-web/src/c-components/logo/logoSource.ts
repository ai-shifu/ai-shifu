import type { StaticImageData } from 'next/image';
import defaultWideLogo from '@/c-assets/logos/ai-shifu-logo-horizontal.png';

export const DEFAULT_WIDE_LOGO = defaultWideLogo;

export const resolveWideLogoSource = (
  logoWideUrl: string,
  logoHorizontal: string,
): string | StaticImageData =>
  logoWideUrl || logoHorizontal || DEFAULT_WIDE_LOGO;
