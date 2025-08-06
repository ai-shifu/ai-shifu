import React, { useEffect, useState } from 'react';
import { Copy, Check, SlidersVertical, Plus } from 'lucide-react';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { uploadFile } from '@/lib/file';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Textarea } from '@/components/ui/Textarea';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/Form';
import { useTranslation } from 'react-i18next';
import api from '@/api';

import ModelList from '@/components/model-list';

interface Shifu {
  description: string;
  bid: string;
  keywords: string[];
  model: string;
  name: string;
  preview_url: string;
  price: number;
  avatar: string;
  url: string;
  temperature: number;
}

export default function ShifuSettingDialog({
  shifuId,
  onSave,
}: {
  shifuId: string;
  onSave: () => void;
}) {
  const [open, setOpen] = useState(false);
  const { t } = useTranslation();
  const [keywords, setKeywords] = useState(['AIGC']);
  const [shifuImage, setShifuImage] = useState<File | null>(null);
  const [imageError, setImageError] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedImageUrl, setUploadedImageUrl] = useState('');
  const [copying, setCopying] = useState({
    previewUrl: false,
    url: false,
  });
  // Initialize the form with react-hook-form and zod resolver

  // Define the validation schema using Zod
  const shifuSchema = z.object({
    previewUrl: z.string(),
    url: z.string(),
    name: z
      .string()
      .min(1, t('shifuSetting.shifuNameEmpty'))
      .max(50, t('shifuSetting.shifuNameMaxLength')),
    description: z
      .string()
      .min(1, t('shifuSetting.shifuDescriptionEmpty'))
      .max(300, t('shifuSetting.shifuDescriptionMaxLength')),
    model: z.string(),
    price: z
      .string()
      .min(1, t('shifuSetting.shifuPriceEmpty'))
      .regex(/^\d+(\.\d{1,2})?$/, t('shifuSetting.shifuPriceFormat')),
    temperature: z
      .string()
      .regex(/^\d+(\.\d{1,2})?$/, t('shifuSetting.shifuTemperatureFormat')),
    temperature_min: z.number().min(0, t('shifuSetting.shifuTemperatureMin')),
    temperature_max: z.number().max(2, t('shifuSetting.shifuTemperatureMax')),
  });

  const form = useForm({
    resolver: zodResolver(shifuSchema),
    defaultValues: {
      previewUrl: '',
      url: '',
      name: '',
      description: '',
      model: '',
      price: '',
      temperature: '',
    },
  });

  // Handle copy to clipboard
  const handleCopy = field => {
    navigator.clipboard.writeText(form.getValues(field));
    setCopying({ ...copying, [field]: true });

    setTimeout(() => {
      setCopying({ ...copying, [field]: false });
    }, 2000);
  };

  // Handle keyword addition
  const handleAddKeyword = () => {
    const keyword = (
      document.getElementById('keywordInput') as any
    )?.value.trim();
    if (keyword && !keywords.includes(keyword)) {
      setKeywords([...keywords, keyword]);
      (document.getElementById('keywordInput') as any).value = '';
    }
  };

  // Handle keyword removal
  const handleRemoveKeyword = keyword => {
    setKeywords(keywords.filter(k => k !== keyword));
  };

  // Handle image upload
  const handleImageUpload = async e => {
    const file = e.target.files[0];
    if (file) {
      // Validate file size
      if (file.size > 2 * 1024 * 1024) {
        setImageError(t('shifuSetting.fileSizeLimit'));
        setShifuImage(null);
        return;
      }

      // Validate file type
      if (!['image/jpeg', 'image/png'].includes(file.type)) {
        setImageError(t('shifuSetting.supportedFormats'));
        setShifuImage(null);
        return;
      }

      setShifuImage(file);
      setImageError('');

      // Upload the file
      try {
        setIsUploading(true);
        setUploadProgress(0);

        // Use the uploadFile function from file.ts
        const response = await uploadFile(
          file,
          '/api/shifu/upfile',
          undefined,
          undefined,
          progress => {
            setUploadProgress(progress);
          },
        );

        if (!response.ok) {
          throw new Error(`Upload failed: ${response.statusText}`);
        }

        const res = await response.json();
        if (res.code !== 0) {
          throw new Error(res.message);
        }
        setUploadedImageUrl(res.data); // Assuming the API returns the image URL in a 'url' field
      } catch (error) {
        console.error('Upload error:', error);
        setImageError(t('shifuSetting.uploadFailed'));
      } finally {
        setIsUploading(false);
      }
    }
  };

  // Handle form submission
  const onSubmit = async data => {
    await api.saveShifuDetail({
      description: data.description,
      shifu_bid: shifuId,
      keywords: keywords,
      model: data.model,
      name: data.name,
      price: Number(data.price),
      avatar: uploadedImageUrl,
      temperature: Number(data.temperature),
    });

    if (onSave) {
      await onSave();
    }
    setOpen(false);
  };
  const init = async () => {
    const result = (await api.getShifuDetail({
      shifu_bid: shifuId,
    })) as Shifu;

    if (result) {
      form.reset({
        name: result.name,
        description: result.description,
        price: result.price + '',
        model: result.model || '',
        previewUrl: result.preview_url,
        url: result.url,
        temperature: result.temperature + '',
      });
      setKeywords(result.keywords);
      setUploadedImageUrl(result.avatar || '');
    }
  };
  useEffect(() => {
    if (!open) {
      return;
    }
    init();
  }, [shifuId, open]);
  return (
    <Dialog
      open={open}
      onOpenChange={setOpen}
    >
      <DialogTrigger asChild>
        <SlidersVertical className='cursor-pointer h-4 w-4 text-gray-500' />
      </DialogTrigger>
      <DialogContent className='sm:max-w-md md:max-w-lg lg:max-w-xl'>
        <DialogHeader>
          <DialogTitle className='text-lg font-medium'>
            {t('shifuSetting.title')}
          </DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <div className='h-[500px] py-2 px-4 overflow-auto space-y-2'>
              <FormField
                control={form.control}
                name='previewUrl'
                render={({ field }) => (
                  <FormItem className='grid grid-cols-4 items-center gap-2 space-y-0'>
                    <FormLabel className='text-right text-sm'>
                      {t('shifuSetting.previewUrl')}
                    </FormLabel>
                    <div className='col-span-3 flex items-center space-x-2'>
                      <FormControl>
                        <a
                          href={field.value}
                          target='_blank'
                          className='px-1 w-full overflow-hidden text-ellipsis whitespace-nowrap '
                        >
                          {field.value}
                        </a>
                      </FormControl>
                      <Button
                        type='button'
                        variant='ghost'
                        size='icon'
                        onClick={() => handleCopy('previewUrl')}
                      >
                        {copying.previewUrl ? (
                          <Check className='h-4 w-4' />
                        ) : (
                          <Copy className='h-4 w-4' />
                        )}
                      </Button>
                    </div>
                    <div className='col-span-3 col-start-2'>
                      <FormMessage />
                    </div>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name='url'
                render={({ field }) => (
                  <FormItem className='grid grid-cols-4 items-center gap-2 space-y-0'>
                    <FormLabel className='text-right text-sm'>
                      {t('shifuSetting.learningUrl')}
                    </FormLabel>
                    <div className='col-span-3 flex items-center space-x-2'>
                      <FormControl>
                        <a
                          href={field.value}
                          target='_blank'
                          className='px-1 w-full overflow-hidden text-ellipsis whitespace-nowrap'
                        >
                          {field.value}
                        </a>
                      </FormControl>
                      <Button
                        type='button'
                        variant='ghost'
                        size='icon'
                        onClick={() => handleCopy('url')}
                      >
                        {copying.url ? (
                          <Check className='h-4 w-4' />
                        ) : (
                          <Copy className='h-4 w-4' />
                        )}
                      </Button>
                    </div>
                    <div className='col-span-3 col-start-2'>
                      <FormMessage />
                    </div>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='name'
                render={({ field }) => (
                  <FormItem className='grid grid-cols-4 items-start gap-4 space-y-0'>
                    <FormLabel className='text-right text-sm pt-2'>
                      {t('shifuSetting.shifuName')}
                    </FormLabel>
                    <div className='col-span-3'>
                      <FormControl>
                        <Input
                          {...field}
                          maxLength={50}
                          placeholder={t('shifuSetting.limit50Characters')}
                        />
                      </FormControl>
                      <p className='text-xs text-gray-500 mt-1'>
                        {field.value.length}/50
                      </p>
                      <FormMessage />
                    </div>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name='description'
                render={({ field }) => (
                  <FormItem className='grid grid-cols-4 items-start gap-4'>
                    <FormLabel className='text-right text-sm pt-2'>
                      {t('shifuSetting.shifuDescription')}
                    </FormLabel>
                    <div className='col-span-3'>
                      <FormControl>
                        <Textarea
                          {...field}
                          maxLength={300}
                          placeholder={t('shifuSetting.limit300Characters')}
                          rows={4}
                        />
                      </FormControl>
                      <p className='text-xs text-gray-500 mt-1'>
                        {field.value.length}/300
                      </p>
                      <FormMessage />
                    </div>
                  </FormItem>
                )}
              />
              <div className='grid grid-cols-4 items-start gap-4'>
                <label className='text-right text-sm pt-2'>
                  {t('shifuSetting.keywords')}
                </label>
                <div className='col-span-3'>
                  <div className='flex flex-wrap gap-2 mb-2'>
                    {keywords.map((keyword, index) => (
                      <Badge
                        key={index}
                        variant='secondary'
                        className='flex items-center gap-1'
                      >
                        {keyword}
                        <button
                          type='button'
                          onClick={() => handleRemoveKeyword(keyword)}
                          className='text-xs ml-1 hover:text-red-500'
                        >
                          ×
                        </button>
                      </Badge>
                    ))}
                  </div>
                  <div className='flex gap-2'>
                    <Input
                      id='keywordInput'
                      placeholder={t('shifuSetting.inputKeywords')}
                      className='flex-grow h-8'
                    />
                    <Button
                      type='button'
                      className='h-8'
                      onClick={handleAddKeyword}
                      variant='outline'
                      size='sm'
                    >
                      {t('shifuSetting.addKeyword')}
                    </Button>
                  </div>
                </div>
              </div>
              <div className='grid grid-cols-4 items-start gap-4'>
                <label className='text-right text-sm pt-2'>
                  {t('shifuSetting.shifuAvatar')}
                </label>
                <div className='col-span-3'>
                  {uploadedImageUrl ? (
                    <div className='mb-2'>
                      <div className='relative w-24 h-24 bg-gray-100 rounded-lg overflow-hidden'>
                        <img
                          src={uploadedImageUrl}
                          alt={t('shifuSetting.shifuAvatar')}
                          className='w-full h-full object-cover'
                        />
                        <button
                          type='button'
                          onClick={() =>
                            document.getElementById('imageUpload')?.click()
                          }
                          className='absolute bottom-2 right-2 bg-white p-1 rounded-full shadow-md hover:bg-gray-100'
                        >
                          <Plus className='h-4 w-4' />
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div
                      className='border-2 border-dashed rounded-lg w-24 h-24 flex flex-col items-center justify-center cursor-pointer'
                      onClick={() =>
                        document.getElementById('imageUpload')?.click()
                      }
                    >
                      <Plus className='h-8 w-8 mb-2 text-gray-400' />
                      <p className='text-sm text-center'>
                        {t('shifuSetting.upload')}
                      </p>
                    </div>
                  )}

                  <input
                    id='imageUpload'
                    type='file'
                    accept='image/jpeg,image/png'
                    onChange={handleImageUpload}
                    className='hidden'
                  />

                  <p className='text-xs text-gray-500 mt-1'>
                    {t(
                      'shifu-setting.support-jpg-png-format-file-less-than-2mb',
                    )}
                  </p>

                  {isUploading && (
                    <div className='mt-2'>
                      <div className='w-full bg-gray-200 rounded-full h-2.5'>
                        <div
                          className='bg-primary h-2.5 rounded-full'
                          style={{ width: `${uploadProgress}%` }}
                        ></div>
                      </div>
                      <p className='text-xs text-gray-500 mt-1 text-center'>
                        {t('shifuSetting.uploading')} {uploadProgress}%
                      </p>
                    </div>
                  )}

                  {imageError && (
                    <p className='text-red-500 text-xs mt-1'>{imageError}</p>
                  )}

                  {shifuImage && !isUploading && !uploadedImageUrl && (
                    <p className='text-green-500 text-xs mt-1'>
                      {t('shifuSetting.selected')}: {shifuImage?.name}
                    </p>
                  )}
                </div>
              </div>
              <FormField
                control={form.control}
                name='model'
                render={({ field }) => (
                  <FormItem className='grid grid-cols-4 items-center gap-4'>
                    <FormLabel className='text-right text-sm'>
                      {t('common.selectModel')}
                    </FormLabel>
                    <div className='col-span-3'>
                      <FormControl>
                        <ModelList
                          value={field.value}
                          onChange={field.onChange}
                        />
                      </FormControl>
                      <FormMessage />
                    </div>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name='temperature'
                render={({ field }) => (
                  <FormItem className='grid grid-cols-4 items-center gap-4'>
                    <FormLabel className='text-right text-sm'>
                      {t('shifuSetting.shifuTemperature')}
                    </FormLabel>
                    <div className='col-span-3'>
                      <FormControl>
                        <Input
                          {...field}
                          placeholder={t('shifuSetting.number')}
                          type='number'
                          min={0}
                          max={2}
                          step={0.1}
                        />
                      </FormControl>
                      <FormMessage />
                    </div>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name='price'
                render={({ field }) => (
                  <FormItem className='grid grid-cols-4 items-center gap-4'>
                    <FormLabel className='text-right text-sm'>
                      {t('shifuSetting.price')}
                    </FormLabel>
                    <div className='col-span-3'>
                      <FormControl>
                        <Input
                          {...field}
                          placeholder={t('shifuSetting.number')}
                        />
                      </FormControl>
                      <FormMessage />
                    </div>
                  </FormItem>
                )}
              />
            </div>
            <DialogFooter className='sm:justify-end pt-4'>
              <Button
                type='button'
                variant='outline'
                onClick={() => setOpen(false)}
              >
                {t('shifuSetting.cancel')}
              </Button>
              <Button
                type='submit'
                className='bg-primary hover:bg-primary-lighter text-white'
                onClick={() => {
                  onSubmit(form.getValues());
                }}
              >
                {t('shifuSetting.save')}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
