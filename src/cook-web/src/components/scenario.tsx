import { PlusIcon, ArrowDownTrayIcon } from '@heroicons/react/24/outline';
import { TrophyIcon, AcademicCapIcon, UserIcon, MusicalNoteIcon } from '@heroicons/react/24/solid';

const ScriptCard = ({ icon: Icon, title }) => (
    <div className="w-full md:w-[calc(50%-1rem)] lg:w-[calc(33.33%-1rem)] p-4 bg-white rounded-lg shadow-sm mb-4">
        <div className="flex items-start space-x-3">
            <div className="p-2 rounded-lg bg-purple-50">
                <Icon className="w-6 h-6 text-purple-600" />
            </div>
            <div className="flex-1">
                <h3 className="font-medium text-gray-900">{title}</h3>
                <p className="mt-1 text-sm text-gray-500">
                    剧本简述可能更长剧本简述可能更长，剧本简述可能更长剧本简述可能更长，剧本简述可能更长剧本简述可能更长。
                </p>
                <p className="mt-1 text-sm text-gray-500">
                    剧本简述可能更长剧本简述可能更长，剧本简述可能更长剧本简述可能更长，剧本简述可能更长剧本简述可能更长。
                </p>
            </div>
        </div>
    </div>
);

const ScriptManagementPage = () => {
    const scripts = [
        { id: 1, icon: TrophyIcon, title: '剧本标题可能会比较长，存在折行的情况' },
        { id: 2, icon: AcademicCapIcon, title: '剧本标题可能会比较长，存在折行的情况' },
        { id: 3, icon: UserIcon, title: '剧本标题可能会比较长，存在折行的情况' },
        { id: 4, icon: MusicalNoteIcon, title: '剧本标题可能会比较长，存在折行的情况' },
    ];

    return (
        <div className="min-h-screen bg-gray-50 p-6">
            <div className="max-w-7xl mx-auto">
                <div className="flex justify-between items-center mb-6">
                    <h1 className="text-2xl font-semibold text-gray-900">剧本</h1>
                    <div className="flex space-x-3">
                        <button className="inline-flex items-center px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2">
                            <ArrowDownTrayIcon className="w-5 h-5 mr-2" />
                            从模版创建
                        </button>
                        <button className="inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-gray-700 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2">
                            <PlusIcon className="w-5 h-5 mr-2" />
                            新建空白剧本
                        </button>
                        <button className="inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-gray-700 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2">
                            导入
                        </button>
                    </div>
                </div>

                <div className="flex space-x-4 mb-6">
                    <button className="inline-flex items-center px-3 py-2 text-sm font-medium text-purple-700 border-b-2 border-purple-700">
                        全部
                    </button>
                    <button className="inline-flex items-center px-3 py-2 text-sm font-medium text-gray-500 hover:text-gray-700">
                        收藏
                    </button>
                </div>

                <div className="flex flex-wrap gap-4">
                    {scripts.map((script) => (
                        <ScriptCard key={script.id} icon={script.icon} title={script.title} />
                    ))}
                </div>
            </div>
        </div>
    );
};

export default ScriptManagementPage;
