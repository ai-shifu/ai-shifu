import React, { useCallback, useEffect, useState } from 'react';
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
import { useEnvStore } from '@/c-store';

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

const MIN_SHIFU_PRICE = 0.5;

export default function ShifuSettingDialog({
  shifuId,
  onSave,
}: {
  shifuId: string;
  onSave: () => void;
}) {
  const [open, setOpen] = useState(false);
  const { t } = useTranslation();
  const defaultLlmModel = useEnvStore(state => state.defaultLlmModel);
  const baseSelectModelHint = t('module.shifuSetting.selectModelHint');
  const resolvedDefaultModel = defaultLlmModel;
  const isCjk = /[\u4e00-\u9fff]/.test(baseSelectModelHint);
  const defatultLlmModel = defaultLlmModel
    ? isCjk
      ? `（${resolvedDefaultModel}）`
      : ` (${resolvedDefaultModel})`
    : '';
  const selectModelHint = `${baseSelectModelHint}${defatultLlmModel}`;
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

  // Define the validation schema using Zod
  const shifuSchema = z.object({
    previewUrl: z.string(),
    url: z.string(),
    name: z
      .string()
      .min(1, t('module.shifuSetting.shifuNameEmpty'))
      .max(100, t('module.shifuSetting.shifuNameMaxLength')),
    description: z
      .string()
      .min(0, t('module.shifuSetting.shifuDescriptionEmpty'))
      .max(500, t('module.shifuSetting.shifuDescriptionMaxLength')),
    model: z.string(),
    systemPrompt: z
      .string()
      .max(20000, t('module.shifuSetting.shifuPromptMaxLength')),
    price: z
      .string()
      .min(0.5, t('module.shifuSetting.shifuPriceEmpty'))
      .regex(/^\d+(\.\d{1,2})?$/, t('module.shifuSetting.shifuPriceFormat')),
    temperature: z
      .string()
      .regex(
        /^\d+(\.\d{1,2})?$/,
        t('module.shifuSetting.shifuTemperatureFormat'),
      ),
    temperature_min: z
      .number()
      .min(0, t('module.shifuSetting.shifuTemperatureMin')),
    temperature_max: z
      .number()
      .max(2, t('module.shifuSetting.shifuTemperatureMax')),
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
  const isDirty = form.formState.isDirty;

  const [formSnapshot, setFormSnapshot] = useState(form.getValues());

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
        setImageError(t('module.shifuSetting.fileSizeLimit'));
        setShifuImage(null);
        return;
      }

      // Validate file type
      if (!['image/jpeg', 'image/png'].includes(file.type)) {
        setImageError(t('module.shifuSetting.supportedFormats'));
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
        setImageError(t('module.shifuSetting.uploadFailed'));
      } finally {
        setIsUploading(false);
      }
    }
  };

  // Handle form submission
  const onSubmit = async (data: any, needClose = true) => {
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
    if (needClose) {
      setOpen(false);
    }
  };
  const init = async () => {
    const result = (await api.getShifuDetail({
      shifu_bid: shifuId,
    })) as Shifu;

    if (result) {
      form.reset({
        name: result.name,
        description: result.description,
        price: (result.price ?? 0).toFixed(2),
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
  }, [shifuId, open, init]);

  useEffect(() => {
    const subscription = form.watch((value: any) => {
      setFormSnapshot(value);
    });
    return () => subscription.unsubscribe();
  }, [form]);

  const submitForm = useCallback(
    async (needClose = true) => {
      const isNameValid = await form.trigger('name');
      const isPriceValid = await form.trigger('price');
      if (!isPriceValid) {
        if (needClose) {
          setOpen(true);
        }
        return false;
      }
      const priceValue = parseFloat(form.getValues('price') || '0');
      if (!Number.isNaN(priceValue) && priceValue < MIN_SHIFU_PRICE) {
        form.setError('price', {
          type: 'manual',
          message: t('server.shifu.shifuPriceTooLow', {
            min_shifu_price: MIN_SHIFU_PRICE,
          }),
        });
        if (needClose) {
          setOpen(true);
        }
        return false;
      }
      if (!isNameValid) {
        if (needClose) {
          setOpen(true);
        }
        return false;
      }
      await onSubmit(form.getValues(), needClose);
      return true;
    },
    [form, onSubmit, setOpen, t],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    if (!isDirty) {
      return;
    }
    const timer = setTimeout(() => {
      submitForm(false);
    }, 3000);
    return () => clearTimeout(timer);
  }, [formSnapshot, open, submitForm, isDirty]);

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        submitForm(true);
        return;
      }
      setOpen(true);
    },
    [submitForm, setOpen],
  );

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
      onOpenChange={handleOpenChange}
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
            {t('module.shifuSetting.title')}
          </SheetTitle>
        </SheetHeader>
        <div className='h-px w-full bg-border' />
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(data => onSubmit(data, true))}
            className='flex-1 flex flex-col overflow-hidden'
          >
            <div className='flex-1 overflow-y-auto px-6'>
              <FormField
                control={form.control}
                name='name'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <FormLabel className='text-sm font-medium text-foreground'>
                      {t('module.shifuSetting.shifuName')}
                    </FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        maxLength={100}
                        placeholder={t('module.shifuSetting.placeholder')}
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
                      {t('module.shifuSetting.shifuDescription')}
                    </FormLabel>
                    <FormControl>
                      <Textarea
                        {...field}
                        maxLength={500}
                        placeholder={t('module.shifuSetting.placeholder')}
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
                <p className='text-sm font-medium text-foreground'>
                  {t('module.shifuSetting.shifuAvatar')}
                </p>
                <span className='text-xs text-muted-foreground'>
                  {t('module.shifuSetting.imageFormatHint')}
                </span>
                <div className='flex flex-col gap-3'>
                  {uploadedImageUrl ? (
                    <div className='relative w-24 h-24 bg-gray-100 rounded-lg overflow-hidden'>
                      <img
                        src={uploadedImageUrl}
                        alt={t('module.shifuSetting.shifuAvatar')}
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
                        {t('module.shifuSetting.upload')}
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

                  {isUploading && (
                    <div className='space-y-2 mb-4'>
                      <div className='w-full bg-muted rounded-full h-2'>
                        <div
                          className='bg-primary h-2 rounded-full'
                          style={{ width: `${uploadProgress}%` }}
                        ></div>
                      </div>
                      <p className='text-xs text-muted-foreground text-center'>
                        {t('module.shifuSetting.uploading')} {uploadProgress}%
                      </p>
                    </div>
                  )}
                  {imageError && (
                    <p className='text-xs text-destructive'>{imageError}</p>
                  )}
                  {shifuImage && !isUploading && !uploadedImageUrl && (
                    <p className='text-xs text-emerald-600'>
                      {t('module.shifuSetting.selected')}: {shifuImage?.name}
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
                      {t('module.shifuSetting.previewUrl')}
                    </FormLabel>
                    <FormControl>
                      <div className='flex items-center gap-2'>
                        <input
                          type='hidden'
                          {...field}
                        />
                        <span
                          className='flex-1 text-sm underline whitespace-nowrap overflow-hidden text-ellipsis'
                          style={{
                            color: 'var(--base-muted-foreground, #737373)',
                          }}
                          title={field.value}
                        >
                          {field.value}
                        </span>
                        <button
                          type='button'
                          onClick={() => handleCopy('previewUrl')}
                          className='flex items-center justify-center text-muted-foreground hover:text-foreground focus:outline-none'
                          style={{ width: 20, height: 20 }}
                        >
                          {copying.previewUrl ? (
                            <Check className='w-[14px] h-[14px]' />
                          ) : (
                            <Copy className='w-[14px] h-[14px]' />
                          )}
                        </button>
                      </div>
                    </FormControl>
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
                      {t('module.shifuSetting.learningUrl')}
                    </FormLabel>
                    <FormControl>
                      <div className='flex items-center gap-2'>
                        <input
                          type='hidden'
                          {...field}
                        />
                        <span
                          className='flex-1 text-sm underline whitespace-nowrap overflow-hidden text-ellipsis'
                          style={{
                            color: 'var(--base-muted-foreground, #737373)',
                          }}
                          title={field.value}
                        >
                          {field.value}
                        </span>
                        <button
                          type='button'
                          onClick={() => handleCopy('url')}
                          className='flex items-center justify-center text-muted-foreground hover:text-foreground focus:outline-none'
                          style={{ width: 20, height: 20 }}
                        >
                          {copying.url ? (
                            <Check className='w-[14px] h-[14px]' />
                          ) : (
                            <Copy className='w-[14px] h-[14px]' />
                          )}
                        </button>
                      </div>
                    </FormControl>
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
                      {t('common.core.selectModel')}
                    </FormLabel>
                    <p className='text-xs text-muted-foreground'>
                      {selectModelHint}
                    </p>
                    <FormControl>
                      <ModelList
                        className='h-9'
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
                      {t('module.shifuSetting.shifuTemperature')}
                    </FormLabel>
                    <p className='text-xs text-muted-foreground'>
                      {t('module.shifuSetting.temperatureHint')}
                      <br />
                      {t('module.shifuSetting.temperatureHint2')}
                    </p>
                    <div className='flex items-center gap-2'>
                      <FormControl className='flex-1'>
                        <Input
                          {...field}
                          value={field.value}
                          onChange={field.onChange}
                          type='text'
                          inputMode='decimal'
                          placeholder={t('module.shifuSetting.number')}
                          className='h-9'
                        />
                      </FormControl>
                      <div className='flex items-center gap-2'>
                        <Button
                          type='button'
                          variant='outline'
                          size='icon'
                          onClick={() => adjustTemperature(-0.1)}
                          className='h-9 w-9'
                        >
                          <Minus className='h-4 w-4' />
                        </Button>
                        <Button
                          type='button'
                          variant='outline'
                          size='icon'
                          onClick={() => adjustTemperature(0.1)}
                          className='h-9 w-9'
                        >
                          <Plus className='h-4 w-4' />
                        </Button>
                      </div>
                    </div>
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
                        {t('module.shifuSetting.shifuPrompt')}
                      </FormLabel>
                      {/* <a
                        href='https://markdownflow.ai/docs/zh/specification/how-it-works/#2'
                        target='_blank'
                        rel='noopener noreferrer'
                      >
                        <CircleHelp className='h-4 w-4 text-muted-foreground' />
                      </a> */}
                    </div>
                    <p className='text-xs text-muted-foreground'>
                      {t('module.shifuSetting.shifuPromptHint')}
                    </p>
                    <FormControl>
                      <Textarea
                        {...field}
                        maxLength={20000}
                        placeholder={t(
                          'module.shifuSetting.shifuPromptPlaceholder',
                        )}
                        minRows={3}
                        maxRows={30}
                      />
                    </FormControl>
                    {/* <div className='text-xs text-muted-foreground text-right'>
                      {field.value?.length ?? 0}/10000
                    </div> */}
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className='space-y-2 mb-4'>
                <span className='text-sm font-medium text-foreground'>
                  {t('module.shifuSetting.keywords')}
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
                    placeholder={t('module.shifuSetting.inputKeywords')}
                    className='flex-1 h-9'
                  />
                  <Button
                    type='button'
                    onClick={handleAddKeyword}
                    variant='outline'
                    size='sm'
                  >
                    {t('module.shifuSetting.addKeyword')}
                  </Button>
                </div>
              </div>

              <FormField
                control={form.control}
                name='price'
                render={({ field }) => (
                  <FormItem className='space-y-2 mb-4'>
                    <FormLabel className='text-sm font-medium text-foreground'>
                      {t('module.shifuSetting.price')}
                    </FormLabel>
                    <FormControl>
                      <Input
                        className='h-9'
                        {...field}
                        placeholder={t('module.shifuSetting.number')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className='h-px w-full bg-border' />
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}
