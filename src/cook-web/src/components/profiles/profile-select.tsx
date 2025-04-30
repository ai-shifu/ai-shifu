/** inject profile to mc-editor */
'use client';
import React, { useState, useCallback } from 'react';
import { Edit, Plus, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { Profile } from '@/components/profiles/type';
import ProfileSave from './profile-save';
import api from '@/api';
import useProfiles from './useProfiles';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface ProfileSelectProps {
  parentId?: string;
  onSelect?: (profile: Profile) => void;
}

const ProfileSelect: React.FC<ProfileSelectProps> = ({
  parentId,
  onSelect = () => {},
}) => {
  const [saveOpen, setSaveOpen] = useState<boolean>(false);
  const [editingProfile, setEditingProfile] = useState<Profile | undefined>();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [refreshFlag, setRefreshFlag] = useState(0);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deleteProfileId, setDeleteProfileId] = useState<string | null>(null);

  const handleDeleteProfile = useCallback(async (id: string) => {
    setDeleteProfileId(id);
    setShowDeleteDialog(true);
  }, []);

  const handleConfirmDelete = async () => {
    if (deleteProfileId) {
      const res = await api.deleteProfile({
        profile_id: deleteProfileId,
      });
      if (res) {
        setRefreshFlag(refreshFlag + 1);
      }
      setShowDeleteDialog(false);
      setDeleteProfileId(null);
    }
  };

  const [systemProfiles, customProfiles] = useProfiles({
    parentId,
    searchTerm,
    refreshFlag,
  });

  const handleSaveProfile = (isEdit: boolean, profile?: Profile) => {
    if (isEdit && profile) {
      setEditingProfile(profile);
    } else {
      setEditingProfile(undefined);
    }
    setSaveOpen(true);
  };

  const handleProfileSaveSuccess = () => {
    setRefreshFlag(refreshFlag + 1);
  };

  return (
    <div className="space-y-4 text-xs">
      <div className="relative">
        <Input
          placeholder="搜索变量..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full"
        />
        {searchTerm && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute right-2 top-1/2 -translate-y-1/2 h-6 w-6"
            onClick={() => setSearchTerm('')}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
      <ScrollArea className="h-[300px] rounded-md border">
        <div className="p-4 space-y-4">
          {!!systemProfiles?.length && (
            <div>
              <h4 className="mb-2 text-sm font-medium text-muted-foreground">
                系统变量
              </h4>
              <div className="space-y-1">
                {systemProfiles?.map((profile) => (
                  <div
                    key={profile.profile_id}
                    className="flex items-center justify-between p-2 rounded-md hover:bg-accent cursor-pointer"
                    onClick={() => onSelect(profile)}
                    onMouseEnter={() =>
                      setHoveredId(profile?.profile_id || null)
                    }
                    onMouseLeave={() => setHoveredId(null)}
                  >
                    <div className="flex flex-col">
                      <span>{profile.profile_key}</span>
                      {profile.profile_remark && (
                        <span className="text-xs text-muted-foreground">
                          {profile.profile_remark}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center">
                      <span className="text-xs text-muted-foreground mr-2">
                        {profile.profile_type === 'text' ? '字符串' : '枚举'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {!!customProfiles?.length && (
            <div>
              <h4 className="mb-2 text-sm font-medium text-muted-foreground">
                自定义变量
              </h4>
              <div className="space-y-1">
                {customProfiles?.map((profile) => (
                  <div
                    key={profile.profile_id}
                    className="flex items-center justify-between p-2 rounded-md hover:bg-accent cursor-pointer group"
                    onClick={() => onSelect(profile)}
                    onMouseEnter={() =>
                      setHoveredId(profile?.profile_id || null)
                    }
                    onMouseLeave={() => setHoveredId(null)}
                  >
                    <div className="flex flex-col">
                      <div className="flex items-center">
                        <span>{profile.profile_key}</span>
                        {hoveredId === profile.profile_id &&
                          profile.profile_type === 'text' &&
                          profile.defaultValue && (
                            <span className="text-xs text-muted-foreground ml-2 bg-muted px-1.5 py-0.5 rounded">
                              默认值: {profile.defaultValue}
                            </span>
                          )}
                      </div>
                      {profile.profile_remark && (
                        <span className="text-xs text-muted-foreground">
                          {profile.profile_remark}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center">
                      <span className="text-xs text-muted-foreground mr-2">
                        {profile.profile_type === 'text' ? '字符串' : '枚举'}
                      </span>

                      {hoveredId === profile.profile_id ? (
                        <div
                          className="flex"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSaveProfile(true, profile);
                            }}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteProfile(
                                profile.profile_id as unknown as string,
                              );
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!systemProfiles?.length && !customProfiles?.length && (
            <div className="py-6 text-center text-muted-foreground">
              未找到变量
            </div>
          )}
        </div>
      </ScrollArea>
      <Button
        variant="outline"
        className="w-full h-8"
        onClick={() => handleSaveProfile(false)}
      >
        <Plus className="h-4 w-4" />
        添加新变量
      </Button>
      <ProfileSave
        parentId={parentId}
        open={saveOpen}
        onOpenChange={setSaveOpen}
        value={editingProfile}
        onSaveSuccess={handleProfileSaveSuccess}
      />

      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              您的操作将会造成当前内容的丢失，是否确认？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmDelete}>
              确认
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
export default ProfileSelect;
