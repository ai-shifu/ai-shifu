import React, { useEffect, useState } from 'react';
import {
  Copy,
  Check,
  SlidersVertical,
  Plus,
  Minus,
  CircleHelp,
} from 'lucide-react';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { uploadFile } from '@/lib/file';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
  SheetTrigger,
} from '@/components/ui/Sheet';
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
  system_prompt?: string;
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
    systemPrompt: z.string().max(300, t('shifuSetting.systemPromptMaxLength')),
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
      systemPrompt: '',
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
      system_prompt: data.systemPrompt,
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
        systemPrompt: result.system_prompt || '',
      });
      setKeywords(result.keywords || []);
      setUploadedImageUrl(result.avatar || '');
    }
  };
  useEffect(() => {
    if (!open) {
      return;
    }
    init();
  }, [shifuId, open]);

  const adjustTemperature = (delta: number) => {
    const currentValue = parseFloat(form.getValues('temperature') || '0');
    const safeValue = Number.isNaN(currentValue) ? 0 : currentValue;
    const nextValue = Math.min(
      2,
      Math.max(0, parseFloat((safeValue + delta).toFixed(1))),
    );
    form.setValue('temperature', nextValue.toString(), {
      shouldDirty: true,
      shouldValidate: true,
    });
  };

  return (
    <Sheet
      open={open}
      onOpenChange={setOpen}
    >
      <SheetTrigger asChild>
        <SlidersVertical className='cursor-pointer h-4 w-4 text-gray-500' />
      </SheetTrigger>
      <SheetContent
        side='right'
        className='w-full sm:w-[420px] md:w-[480px] h-full flex flex-col p-0'
      >
        <SheetHeader className='px-6 pt-6'>
          <SheetTitle className='text-lg font-medium'>
            {t('shifuSetting.title')}
          </SheetTitle>
        </SheetHeader>
        <div className='h-px w-full bg-border' />
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className='flex-1 flex flex-col overflow-hidden'
          >
            <div className='flex-1 overflow-y-auto px-6'>
              <FormField
                control={form.control}
                name='name'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <FormLabel className='text-sm font-medium text-foreground'>
                      {t('shifuSetting.shifuName')}
                    </FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        maxLength={20}
                        placeholder={t('shifuSetting.limit20Characters')}
                      />
                    </FormControl>
                    {/* <div className='text-xs text-muted-foreground text-right'>
                      {(field.value?.length ?? 0)}/50
                    </div> */}
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='description'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <FormLabel className='text-sm font-medium text-foreground'>
                      {t('shifuSetting.shifuDescription')}
                    </FormLabel>
                    <FormControl>
                      <Textarea
                        {...field}
                        maxLength={300}
                        placeholder={t('shifuSetting.limit300Characters')}
                        rows={4}
                      />
                    </FormControl>
                    {/* <div className='text-xs text-muted-foreground text-right'>
                      {(field.value?.length ?? 0)}/300
                    </div> */}
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className='space-y-3 mb-4'>
                <span className='text-sm font-medium text-foreground'>
                  {t('shifuSetting.shifuAvatar')}
                </span>
                <div className='flex flex-col gap-3'>
                  {uploadedImageUrl ? (
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
                        className='absolute inset-0 flex items-center justify-center bg-black/30 text-white opacity-0 transition-opacity hover:opacity-100'
                      >
                        <Plus className='h-5 w-5' />
                      </button>
                    </div>
                  ) : (
                    <div
                      className='border-2 border-dashed border-muted-foreground/30 rounded-lg w-24 h-24 flex flex-col items-center justify-center cursor-pointer bg-muted/20'
                      onClick={() =>
                        document.getElementById('imageUpload')?.click()
                      }
                    >
                      <Plus className='h-6 w-6 mb-1 text-muted-foreground' />
                      <p className='text-xs text-muted-foreground'>
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
                  <p className='text-xs text-muted-foreground'>
                    {t('shifuSetting.imageFormatHint')}
                  </p>
                  {isUploading && (
                    <div className='space-y-2 mb-4'>
                      <div className='w-full bg-muted rounded-full h-2'>
                        <div
                          className='bg-primary h-2 rounded-full'
                          style={{ width: `${uploadProgress}%` }}
                        ></div>
                      </div>
                      <p className='text-xs text-muted-foreground text-center'>
                        {t('shifuSetting.uploading')} {uploadProgress}%
                      </p>
                    </div>
                  )}
                  {imageError && (
                    <p className='text-xs text-destructive'>{imageError}</p>
                  )}
                  {shifuImage && !isUploading && !uploadedImageUrl && (
                    <p className='text-xs text-emerald-600'>
                      {t('shifuSetting.selected')}: {shifuImage?.name}
                    </p>
                  )}
                </div>
              </div>

              <FormField
                control={form.control}
                name='previewUrl'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <FormLabel className='text-sm font-medium text-foreground'>
                      {t('shifuSetting.previewUrl')}
                    </FormLabel>
                    <div className='flex items-center gap-2'>
                      <FormControl>
                        <Input
                          {...field}
                          placeholder='https://ai-shifu.com/...'
                        />
                      </FormControl>
                      <Button
                        type='button'
                        variant='outline'
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
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='url'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <FormLabel className='text-sm font-medium text-foreground'>
                      {t('shifuSetting.learningUrl')}
                    </FormLabel>
                    <div className='flex items-center gap-2'>
                      <FormControl>
                        <Input
                          {...field}
                          placeholder='https://ai-shifu.com/...'
                        />
                      </FormControl>
                      <Button
                        type='button'
                        variant='outline'
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
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='model'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <FormLabel className='text-sm font-medium text-foreground'>
                      {t('common.selectModel')}
                    </FormLabel>
                    <FormControl>
                      <ModelList
                        value={field.value}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='temperature'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <FormLabel className='text-sm font-medium text-foreground'>
                      {t('shifuSetting.shifuTemperature')}
                    </FormLabel>
                    <div className='flex items-center gap-2'>
                      <Button
                        type='button'
                        variant='outline'
                        size='icon'
                        onClick={() => adjustTemperature(-0.1)}
                      >
                        <Minus className='h-4 w-4' />
                      </Button>
                      <FormControl>
                        <Input
                          {...field}
                          value={field.value}
                          onChange={field.onChange}
                          className='text-center'
                          type='number'
                          step='0.1'
                          min={0}
                          max={2}
                          placeholder={t('shifuSetting.number')}
                        />
                      </FormControl>
                      <Button
                        type='button'
                        variant='outline'
                        size='icon'
                        onClick={() => adjustTemperature(0.1)}
                      >
                        <Plus className='h-4 w-4' />
                      </Button>
                    </div>
                    <p className='text-xs text-muted-foreground'>
                      {t('shifuSetting.temperatureHint')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name='systemPrompt'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <div className='flex items-center gap-2'>
                      <FormLabel className='text-sm font-medium text-foreground'>
                        {t('shifuSetting.systemPrompt')}
                      </FormLabel>
                      <a
                        href='https://markdownflow.ai/docs/zh/specification/how-it-works/#2'
                        target='_blank'
                        rel='noopener noreferrer'
                      >
                        <CircleHelp className='h-4 w-4 text-muted-foreground' />
                      </a>
                    </div>
                    <p className='text-xs text-muted-foreground'>
                      {t('shifuSetting.systemPromptHint')}
                    </p>
                    <FormControl>
                      <Textarea
                        {...field}
                        maxLength={300}
                        placeholder={t('shifuSetting.systemPromptPlaceholder')}
                        rows={6}
                      />
                    </FormControl>
                    <div className='text-xs text-muted-foreground text-right'>
                      {field.value?.length ?? 0}/300
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className='space-y-2 mb-4'>
                <span className='text-sm font-medium text-foreground'>
                  {t('shifuSetting.keywords')}
                </span>
                <div className='flex flex-wrap gap-2'>
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
                        className='text-xs ml-1 hover:text-destructive'
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
                    className='flex-1'
                  />
                  <Button
                    type='button'
                    onClick={handleAddKeyword}
                    variant='outline'
                    size='sm'
                  >
                    {t('shifuSetting.addKeyword')}
                  </Button>
                </div>
              </div>

              <FormField
                control={form.control}
                name='price'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <FormLabel className='text-sm font-medium text-foreground'>
                      {t('shifuSetting.price')}
                    </FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        placeholder={t('shifuSetting.number')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className='h-px w-full bg-border' />
            <SheetFooter className='flex-shrink-0 px-6 py-4'>
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
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}
