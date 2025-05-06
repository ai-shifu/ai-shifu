import React, { useEffect, useState } from "react";
import { Copy, Check, SlidersVertical, Plus } from "lucide-react";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { uploadFile } from "@/lib/file";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form";
import { useTranslation } from 'react-i18next'
import api from "@/api";
import { getSiteHost } from "@/config/runtime-config";
import { useScenario } from "@/store";

interface Scenario {
    scenario_description: string;
    scenario_id: string;
    scenario_keywords: string[];
    scenario_model: string;
    scenario_name: string;
    scenario_preview_url: string;
    scenario_price: number;
    scenario_teacher_avatar: string;
    scenario_url: string;
}


/****
 * Displays a dialog for creating or editing a course scenario, including form fields for course details, keywords, avatar upload, and model selection.
 *
 * Opens a modal dialog where users can input or modify course information such as name, description, keywords, avatar image, model, and price. Supports form validation, image upload with progress tracking, and internationalized UI text. On submission, saves the scenario details and invokes the provided callback.
 *
 * @param scenarioId - The ID of the scenario to edit.
 * @param onSave - Callback invoked after successfully saving the scenario.
 */
export default function CourseCreationDialog({ scenarioId, onSave }: { scenarioId: string, onSave: () => void }) {

    const [open, setOpen] = useState(false);
    const { t } = useTranslation();
    const [keywords, setKeywords] = useState(["AIGC"]);
    const [courseImage, setCourseImage] = useState<File | null>(null);
    const [imageError, setImageError] = useState("");
    const [uploadProgress, setUploadProgress] = useState(0);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadedImageUrl, setUploadedImageUrl] = useState("");
    const { models } = useScenario();
    const [copying, setCopying] = useState({
        previewUrl: false,
        url: false
    });
    const SITE_HOST = getSiteHost();
    // Initialize the form with react-hook-form and zod resolver

    // Define the validation schema using Zod
    const courseSchema = z.object({
        previewUrl: z.string(),
        url: z.string(),
        name: z.string()
            .min(1, t('course-setting.course-name-cannot-be-empty'))
            .max(50, t('course-setting.course-name-cannot-exceed-50-characters')),
        description: z.string()
            .min(1, t('course-setting.course-description-cannot-be-empty'))
            .max(300, t('course-setting.course-description-cannot-exceed-300-characters')),
        model: z.string().min(1, t('course-setting.please-select-model')),
        price: z.string()
            .min(1, t('course-setting.price-cannot-be-empty'))
            .regex(/^\d+(\.\d{1,2})?$/, t('course-setting.price-must-be-valid-number-format')),
    });

    const form = useForm({
        resolver: zodResolver(courseSchema),
        defaultValues: {
            previewUrl: "",
            url: "",
            name: "",
            description: "",
            model: "",
            price: ""
        },
    });

    // Handle copy to clipboard
    const handleCopy = (field) => {
        navigator.clipboard.writeText(form.getValues(field));
        setCopying({ ...copying, [field]: true });

        setTimeout(() => {
            setCopying({ ...copying, [field]: false });
        }, 2000);
    };

    // Handle keyword addition
    const handleAddKeyword = () => {
        const keyword = (document.getElementById("keywordInput") as any)?.value.trim();
        if (keyword && !keywords.includes(keyword)) {
            setKeywords([...keywords, keyword]);
            (document.getElementById("keywordInput") as any).value = "";
        }
    };

    // Handle keyword removal
    const handleRemoveKeyword = (keyword) => {
        setKeywords(keywords.filter(k => k !== keyword));
    };

    // Handle image upload
    const handleImageUpload = async (e) => {
        const file = e.target.files[0];
        if (file) {
            // Validate file size
            if (file.size > 2 * 1024 * 1024) {
                setImageError(t('course-setting.file-size-cannot-exceed-2mb'));
                setCourseImage(null);
                return;
            }

            // Validate file type
            if (!['image/jpeg', 'image/png'].includes(file.type)) {
                setImageError(t('course-setting.only-support-jpg-and-png-format'));
                setCourseImage(null);
                return;
            }

            setCourseImage(file);
            setImageError("");

            // Upload the file
            try {
                setIsUploading(true);
                setUploadProgress(0);

                // Use the uploadFile function from file.ts
                const response = await uploadFile(
                    file,
                        `${SITE_HOST}/api/scenario/upfile`,
                    undefined,
                    undefined,
                    (progress) => {
                        setUploadProgress(progress);
                    }
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
                console.error("Upload error:", error);
                setImageError(t('course-setting.upload-failed-please-try-again'));
            } finally {
                setIsUploading(false);
            }
        }
    };

    // Handle form submission
    const onSubmit = async (data) => {
        // Combine form data with keywords and image
        console.log("data", data)
        const fullFormData = {
            ...data,
            keywords,
            courseImage
        };

        await api.saveScenarioDetail({
            "scenario_description": data.description,
            "scenario_id": scenarioId,
            "scenario_keywords": keywords,
            "scenario_model": data.model,
            "scenario_name": data.name,
            "scenario_price": Number(data.price),
            "scenario_teacher_avatar": uploadedImageUrl
        })

        console.log("Form submitted:", fullFormData);
        if (onSave) {
            await onSave()
        }
        // Here you would typically make an API call to save the data
        setOpen(false);
    };
    const init = async () => {
        const result = await api.getScenarioDetail({
            scenario_id: scenarioId
        }) as Scenario;

        if (result) {
            form.reset({
                name: result.scenario_name,
                description: result.scenario_description,
                price: result.scenario_price + '',
                model: result.scenario_model,
                previewUrl: result.scenario_preview_url,
                url: result.scenario_url,
            })
            setKeywords(result.scenario_keywords)
            setUploadedImageUrl(result.scenario_teacher_avatar || "")
        }
    }
    useEffect(() => {
        if (!open) {
            return;
        }
        init()
    }, [scenarioId, open])
    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <SlidersVertical className='cursor-pointer h-4 w-4 text-gray-500' />
            </DialogTrigger>
            <DialogContent className="sm:max-w-md md:max-w-lg lg:max-w-xl">
                <DialogHeader>
                    <DialogTitle className="text-lg font-medium">{t('course-setting.title')}</DialogTitle>
                </DialogHeader>
                <Form {...form}>
                    <form onSubmit={form.handleSubmit(onSubmit)}>
                        <div className="h-[500px] py-2 px-4 overflow-auto space-y-2">
                            <FormField
                                control={form.control}
                                name="previewUrl"
                                render={({ field }) => (
                                    <FormItem className="grid grid-cols-4 items-center gap-2 space-y-0">
                                        <FormLabel className="text-right text-sm">{t('course-setting.preview-url')}</FormLabel>
                                        <div className="col-span-3 flex items-center space-x-2">
                                            <FormControl>
                                                <a href={field.value} target="_blank" className="px-1 w-full overflow-hidden text-ellipsis whitespace-nowrap ">
                                                    {field.value}
                                                </a>
                                            </FormControl>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => handleCopy("previewUrl")}
                                            >
                                                {copying.previewUrl ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                                            </Button>
                                        </div>
                                        <div className="col-span-3 col-start-2">
                                            <FormMessage />
                                        </div>
                                    </FormItem>
                                )}
                            />
                            <FormField
                                control={form.control}
                                name="url"
                                render={({ field }) => (
                                    <FormItem className="grid grid-cols-4 items-center gap-2 space-y-0">
                                        <FormLabel className="text-right text-sm">{t('course-setting.learning-url')}</FormLabel>
                                        <div className="col-span-3 flex items-center space-x-2">
                                            <FormControl>
                                                <a href={field.value} target="_blank" className="px-1 w-full overflow-hidden text-ellipsis whitespace-nowrap">
                                                    {field.value}
                                                </a>
                                            </FormControl>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => handleCopy("url")}
                                            >
                                                {copying.url ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                                            </Button>
                                        </div>
                                        <div className="col-span-3 col-start-2">
                                            <FormMessage />
                                        </div>
                                    </FormItem>
                                )}
                            />

                            <FormField
                                control={form.control}
                                name="name"
                                render={({ field }) => (
                                    <FormItem className="grid grid-cols-4 items-start gap-4 space-y-0">
                                        <FormLabel className="text-right text-sm pt-2">{t('course-setting.course-name')}</FormLabel>
                                        <div className="col-span-3">
                                            <FormControl>
                                                <Input {...field} maxLength={50} placeholder={t('course-setting.limit-50-characters')} />
                                            </FormControl>
                                            <p className="text-xs text-gray-500 mt-1">
                                                {field.value.length}/50
                                            </p>
                                            <FormMessage />
                                        </div>
                                    </FormItem>
                                )}
                            />
                            <FormField
                                control={form.control}
                                name="description"
                                render={({ field }) => (
                                    <FormItem className="grid grid-cols-4 items-start gap-4">
                                        <FormLabel className="text-right text-sm pt-2">{t('course-setting.course-description')}</FormLabel>
                                        <div className="col-span-3">
                                            <FormControl>
                                                <Textarea
                                                    {...field}
                                                    maxLength={300}
                                                    placeholder={t('course-setting.limit-300-characters')}
                                                    rows={4}
                                                />
                                            </FormControl>
                                            <p className="text-xs text-gray-500 mt-1">
                                                {field.value.length}/300
                                            </p>
                                            <FormMessage />
                                        </div>
                                    </FormItem>
                                )}
                            />
                            <div className="grid grid-cols-4 items-start gap-4">
                                <label className="text-right text-sm pt-2 font-semibold">{t('course-setting.keywords')}</label>
                                <div className="col-span-3">
                                    <div className="flex flex-wrap gap-2 mb-2">
                                        {keywords.map((keyword, index) => (
                                            <Badge
                                                key={index}
                                                variant="secondary"
                                                className="flex items-center gap-1"
                                            >
                                                {keyword}
                                                <button
                                                    type="button"
                                                    onClick={() => handleRemoveKeyword(keyword)}
                                                    className="text-xs ml-1 hover:text-red-500"
                                                >
                                                    ×
                                                </button>
                                            </Badge>
                                        ))}
                                    </div>
                                    <div className="flex gap-2">
                                        <Input
                                            id="keywordInput"
                                            placeholder={t('course-setting.input-keywords')}
                                            className="flex-grow h-8"
                                        />
                                        <Button
                                            type="button"
                                            className="h-8"
                                            onClick={handleAddKeyword}
                                            variant="outline"
                                            size="sm"
                                        >
                                            {t('course-setting.add-keyword')}
                                        </Button>
                                    </div>
                                </div>
                            </div>
                            <div className="grid grid-cols-4 items-start gap-4">
                                <label className="text-right text-sm pt-2 font-semibold">{t('course-setting.course-avatar')}</label>
                                <div className="col-span-3">
                                    {uploadedImageUrl ? (
                                        <div className="mb-2">
                                            <div className="relative w-24 l h-24 bg-gray-100 rounded-lg overflow-hidden">
                                                <img
                                                    src={uploadedImageUrl}
                                                    alt={t('course-setting.course-avatar')}
                                                    className="w-full h-full object-cover"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => document.getElementById("imageUpload")?.click()}
                                                    className="absolute bottom-2 right-2 bg-white p-1 rounded-full shadow-md hover:bg-gray-100"
                                                >
                                                    <Plus className="h-4 w-4" />
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div
                                            className="border-2 border-dashed rounded-lg w-24 h-24 flex flex-col items-center justify-center cursor-pointer"
                                            onClick={() => document.getElementById("imageUpload")?.click()}
                                        >
                                            <Plus className="h-8 w-8 mb-2 text-gray-400" />
                                            <p className="text-sm text-center">{t('course-setting.upload')}</p>
                                        </div>
                                    )}

                                    <input
                                        id="imageUpload"
                                        type="file"
                                        accept="image/jpeg,image/png"
                                        onChange={handleImageUpload}
                                        className="hidden"
                                    />

                                    <p className="text-xs text-gray-500 mt-1">
                                        {t('course-setting.support-jpg-png-format-file-less-than-2mb')}
                                    </p>

                                    {isUploading && (
                                        <div className="mt-2">
                                            <div className="w-full bg-gray-200 rounded-full h-2.5">
                                                <div
                                                    className="bg-primary h-2.5 rounded-full"
                                                    style={{ width: `${uploadProgress}%` }}
                                                ></div>
                                            </div>
                                            <p className="text-xs text-gray-500 mt-1 text-center">
                                                {t('course-setting.uploading')} {uploadProgress}%
                                            </p>
                                        </div>
                                    )}

                                    {imageError && (
                                        <p className="text-red-500 text-xs mt-1">{imageError}</p>
                                    )}

                                    {courseImage && !isUploading && !uploadedImageUrl && (
                                        <p className="text-green-500 text-xs mt-1">
                                            {t('course-setting.selected')}: {courseImage?.name}
                                        </p>
                                    )}
                                </div>
                            </div>
                            <FormField
                                control={form.control}
                                name="model"
                                render={({ field }) => (
                                    <FormItem className="grid grid-cols-4 items-center gap-4">
                                        <FormLabel className="text-right text-sm">{t('course-setting.select-model')}</FormLabel>
                                        <div className="col-span-3">
                                            <Select
                                                onValueChange={field.onChange}
                                                defaultValue={field.value}
                                            >
                                                <FormControl>
                                                    <SelectTrigger>
                                                        <SelectValue placeholder={t('course-setting.select-model')} />
                                                    </SelectTrigger>
                                                </FormControl>
                                                <SelectContent>
                                                    {
                                                        models.map((item, i) => {
                                                            return <SelectItem key={i} value={item}>{item}</SelectItem>
                                                        })
                                                    }
                                                </SelectContent>
                                            </Select>
                                            <FormMessage />
                                        </div>
                                    </FormItem>
                                )}
                            />
                            <FormField
                                control={form.control}
                                name="price"
                                render={({ field }) => (
                                    <FormItem className="grid grid-cols-4 items-center gap-4">
                                        <FormLabel className="text-right text-sm">{t('course-setting.price')}</FormLabel>
                                        <div className="col-span-3">
                                            <FormControl>
                                                <Input {...field} placeholder={t('course-setting.number')} />
                                            </FormControl>
                                            <FormMessage />
                                        </div>
                                    </FormItem>
                                )}
                            />

                        </div>
                        <DialogFooter className="sm:justify-end pt-4">
                            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                                {t('course-setting.cancel')}
                            </Button>
                            <Button
                                type="submit"
                                className="bg-purple-600 hover:bg-purple-700 text-white"
                                onClick={() => {
                                    onSubmit(form.getValues())
                                }}
                            >
                                {t('course-setting.save')}
                            </Button>
                        </DialogFooter>
                    </form>
                </Form>
            </DialogContent>
        </Dialog>
    );
}
