import React, { useState } from 'react';
import { Input } from '../ui/input';
import { Plus, Trash } from 'lucide-react';
import { Button } from '../ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/alert-dialog';

interface ButtonProps {
  properties: {
    option_name: string;
    option_key: string;
    profile_key: string;
    buttons: {
      properties: {
        button_name: string;
        button_key: string;
      };
      type: string;
    }[];
  };
  onChange: (properties: any) => void;
}

export default function Option(props: ButtonProps) {
  const { properties } = props;
  const { option_name, buttons } = properties;
  const [tempValue, setTempValue] = useState(option_name);
  const [tempButtons, setTempButtons] = useState(
    buttons.length === 0
      ? [
          {
            properties: {
              button_name: '全部',
              button_key: '全部',
            },
            type: 'button',
          },
        ]
      : buttons,
  );
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);

  const onValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempValue(e.target.value);
  };

  const onButtonValueChange = (
    index: number,
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    setTempButtons(
      tempButtons.map((button: any, i: number) => {
        if (i === index) {
          return {
            ...button,
            properties: {
              ...button.properties,
              button_key: e.target.value,
            },
          };
        }
        return button;
      }),
    );
  };

  const onButtonTextChange = (
    index: number,
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    setTempButtons(
      tempButtons.map((button: any, i: number) => {
        if (i === index) {
          return {
            ...button,
            properties: {
              ...button.properties,
              button_name: e.target.value,
            },
          };
        }
        return button;
      }),
    );
  };

  const onAdd = (index: number) => {
    const newButton = {
      properties: {
        button_name: '全部',
        button_key: '全部',
      },
      type: 'button',
    };
    setTempButtons([
      ...tempButtons.slice(0, index + 1),
      newButton,
      ...tempButtons.slice(index + 1),
    ]);
  };

  const onDelete = (index: number) => {
    if (tempButtons.length === 1) {
      setDeleteIndex(index);
      setShowDeleteDialog(true);
    } else {
      setTempButtons(tempButtons.filter((_: any, i: number) => i !== index));
    }
  };

  const handleConfirmDelete = () => {
    if (deleteIndex !== null) {
      setTempButtons(
        tempButtons.filter((_: any, i: number) => i !== deleteIndex),
      );
      setShowDeleteDialog(false);
      setDeleteIndex(null);
    }
  };

  const handleConfirm = () => {
    if (tempButtons.length === 0) {
      const defaultButton = {
        properties: {
          button_name: '全部',
          button_key: '全部',
        },
        type: 'button',
      };
      setTempButtons([defaultButton]);
    }
    props.onChange({
      ...properties,
      option_name: tempValue,
      option_key: tempValue,
      buttons: tempButtons,
    });
  };

  return (
    <div className="flex flex-col space-y-1">
      <div className="flex flex-row items-center">
        <span className="flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0">
          变量：
        </span>
        <Input
          className="h-8 w-[400px]"
          placeholder="请输入"
          value={tempValue}
          onChange={onValueChange}
        ></Input>
      </div>
      <div className="flex flex-col space-y-2">
        {tempButtons.length === 0 ? (
          <div className="flex flex-row items-center">
            <span className="flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0">
              值：
            </span>
            <Input
              className="w-40"
              placeholder="请输入值"
              value="全部"
              onChange={(e) => {
                const newButton = {
                  properties: {
                    button_name: '全部',
                    button_key: e.target.value,
                  },
                  type: 'button',
                };
                setTempButtons([newButton]);
              }}
            ></Input>
            <span className="flex flex-row items-center whitespace-nowrap  w-[50px] ml-4">
              标题：
            </span>
            <Input
              className="w-40 ml-4"
              placeholder="请输入标题"
              value="全部"
              onChange={(e) => {
                const newButton = {
                  properties: {
                    button_name: e.target.value,
                    button_key: '全部',
                  },
                  type: 'button',
                };
                setTempButtons([newButton]);
              }}
            ></Input>
            <Button
              className="h-8 w-8"
              variant="ghost"
              onClick={() => onAdd(-1)}
            >
              <Plus />
            </Button>
          </div>
        ) : (
          tempButtons.map((button: any, index: number) => {
            return (
              <div key={index} className="flex flex-row items-center">
                <span className="flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0">
                  值：
                </span>
                <Input
                  value={button.properties.button_key}
                  className="w-40"
                  onChange={onButtonValueChange.bind(null, index)}
                ></Input>
                <span className="flex flex-row items-center whitespace-nowrap  w-[50px] ml-4">
                  标题：
                </span>
                <Input
                  value={button.properties.button_name}
                  className="w-40 ml-4"
                  onChange={onButtonTextChange.bind(null, index)}
                ></Input>
                <Button
                  className="h-8 w-8"
                  variant="ghost"
                  onClick={onAdd.bind(null, index)}
                >
                  <Plus />
                </Button>
                <Button
                  className="h-8 w-8"
                  variant="ghost"
                  onClick={onDelete.bind(null, index)}
                >
                  <Trash />
                </Button>
              </div>
            );
          })
        )}
      </div>
      <div className="flex flex-row items-center">
        <span className="flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0"></span>
        <Button className="h-8 w-20" onClick={handleConfirm}>
          完成
        </Button>
      </div>
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
}
