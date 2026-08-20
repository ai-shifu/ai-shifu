'use client';

import React from 'react';
import Link from 'next/link';
import { StarIcon } from '@heroicons/react/24/solid';
import { MoreHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { buildOnboardingTargetProps } from '@/lib/onboardingTargets';

interface ShifuCardProps {
  id: string;
  image: string | undefined;
  title: string;
  description: string;
  isFavorite: boolean;
  archived?: boolean;
  canManageArchive?: boolean;
  canManagePermissions?: boolean;
  onArchiveRequest?: () => void;
  onPermissionRequest?: () => void;
  onImportActivationRequest?: () => void;
  onRedemptionCodeRequest?: () => void;
  onboardingTargetId?: string;
}

const CARD_CONTAINER_CLASS =
  'w-full h-full min-h-[118px] rounded-[var(--border-radius-rounded-xl,14px)] border border-[var(--base-border,#E5E5E5)] bg-[var(--base-card,#FFF)] transition-colors duration-200 ease-in-out hover:bg-primary/[0.04]';
const CARD_CONTAINER_STYLE: React.CSSProperties = {
  boxShadow:
    'var(--shadow-sm-1-offset-x, 0) var(--shadow-sm-1-offset-y, 1px) var(--shadow-sm-1-blur-radius, 3px) var(--shadow-sm-1-spread-radius, 0) var(--shadow-sm-1-color, rgba(0, 0, 0, 0.10)), var(--shadow-sm-2-offset-x, 0) var(--shadow-sm-2-offset-y, 1px) var(--shadow-sm-2-blur-radius, 2px) var(--shadow-sm-2-spread-radius, -1px) var(--shadow-sm-2-color, rgba(0, 0, 0, 0.10))',
};
const CARD_CONTENT_CLASS = 'p-4 flex flex-col h-full cursor-pointer';
const COURSE_AVATAR_CLASS =
  'mr-3 flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px]';
const COURSE_AVATAR_EMPTY_STYLE: React.CSSProperties = {
  backgroundColor: '#CFCED4',
};

const ShifuCard = ({
  id,
  image,
  title,
  description,
  isFavorite,
  archived,
  canManageArchive,
  canManagePermissions,
  onArchiveRequest,
  onPermissionRequest,
  onImportActivationRequest,
  onRedemptionCodeRequest,
  onboardingTargetId,
}: ShifuCardProps) => {
  const { t } = useTranslation();
  const showMenu = Boolean(
    onRedemptionCodeRequest ||
    onImportActivationRequest ||
    canManageArchive ||
    canManagePermissions,
  );

  return (
    <div
      className='relative w-full h-full group'
      {...(onboardingTargetId
        ? buildOnboardingTargetProps(onboardingTargetId)
        : {})}
    >
      <Link
        href={`/shifu/${id}`}
        className='block w-full h-full'
      >
        <Card
          className={CARD_CONTAINER_CLASS}
          style={CARD_CONTAINER_STYLE}
        >
          <CardContent className={CARD_CONTENT_CLASS}>
            <div
              className={`mb-4 flex flex-row items-center justify-between ${showMenu ? 'pr-8' : ''}`}
            >
              <div className='flex min-w-0 flex-row items-center w-full'>
                <div
                  className={COURSE_AVATAR_CLASS}
                  style={!image ? COURSE_AVATAR_EMPTY_STYLE : undefined}
                >
                  {image ? (
                    <img
                      src={image}
                      alt='recipe'
                      className='h-full w-full rounded-[8px] object-cover'
                    />
                  ) : (
                    <img
                      src='/icons/logo.svg'
                      alt=''
                      aria-hidden='true'
                      className='h-[19px] w-4 object-contain'
                    />
                  )}
                </div>

                <h3 className='overflow-hidden text-ellipsis whitespace-nowrap text-[16px] font-medium leading-5 text-black'>
                  {title}
                </h3>
                {archived && (
                  <Badge className='ml-2 rounded-full bg-muted text-muted-foreground px-2 py-0 text-xs whitespace-nowrap'>
                    {t('common.core.archived')}
                  </Badge>
                )}
              </div>
              <div className='flex items-center gap-2'>
                {isFavorite && <StarIcon className='w-5 h-5 text-yellow-400' />}
              </div>
            </div>
            <p className='min-h-[1.25rem] break-words break-all text-sm font-normal leading-5 text-[color:rgba(10,10,10,0.65)] line-clamp-3'>
              {description || ''}
            </p>
          </CardContent>
        </Card>
      </Link>
      {showMenu && (
        <DropdownMenu>
          <div className='absolute right-2 top-2 z-10 flex h-8 w-8 items-center justify-center'>
            <DropdownMenuTrigger asChild>
              <Button
                type='button'
                variant='ghost'
                size='icon'
                className='h-8 w-8 bg-transparent text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:bg-muted data-[state=open]:bg-muted data-[state=open]:text-foreground'
                title={t('common.core.more')}
                aria-label={t('common.core.more')}
                onClick={event => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
              >
                <MoreHorizontal className='h-5 w-5' />
              </Button>
            </DropdownMenuTrigger>
          </div>
          <DropdownMenuContent
            align='end'
            sideOffset={4}
            className='min-w-[9rem]'
          >
            {onImportActivationRequest && (
              <DropdownMenuItem
                onSelect={event => {
                  event.stopPropagation();
                  onImportActivationRequest();
                }}
              >
                {t('module.order.importActivation.action')}
              </DropdownMenuItem>
            )}
            {onRedemptionCodeRequest && (
              <DropdownMenuItem
                onSelect={event => {
                  event.stopPropagation();
                  onRedemptionCodeRequest();
                }}
              >
                {t('module.order.redemptionCodes.action')}
              </DropdownMenuItem>
            )}
            {canManagePermissions && (
              <DropdownMenuItem
                onSelect={event => {
                  event.stopPropagation();
                  onPermissionRequest?.();
                }}
              >
                {t('module.shifuSetting.permissionManage')}
              </DropdownMenuItem>
            )}
            {canManageArchive && (
              <DropdownMenuItem
                onSelect={event => {
                  event.stopPropagation();
                  onArchiveRequest?.();
                }}
              >
                {archived
                  ? t('module.shifuSetting.unarchive')
                  : t('module.shifuSetting.archive')}
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
};

export default ShifuCard;
