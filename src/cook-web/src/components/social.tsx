import React from 'react';
import Image from "next/image";

const SocialLinks = () => {
    return (
        <div className="w-64 bg-white rounded-lg shadow-md p-4">
            {/* Header */}
            <h2 className="text-gray-600 text-sm mb-3">参与社区</h2>

            {/* Social Links */}
            <div className="space-y-3">
                <a href="https://github.com/ai-shifu/ai-shifu" className="flex items-center space-x-2 text-gray-700 hover:bg-gray-50 p-2 rounded-md transition-colors">
                    <Image src="/icons/github.svg" alt='github' width="20" height="20" />
                    <span>Github</span>
                </a>

                {/* <a href="#" className="flex items-center space-x-2 text-gray-700 hover:bg-gray-50 p-2 rounded-md transition-colors">
                    <Image src="/icons/discord.svg" alt='github' width="20" height="20" />
                    <span>Discord</span>
                </a> */}

            </div>
            <div className="border-t border-gray-200 my-3"></div>

            <h2 className="text-gray-600 text-sm mb-3">关于我们</h2>

            {/* Social Links */}
            <div className="space-y-3">
                <a href="#" className="flex items-center space-x-2 text-gray-700 hover:bg-gray-50 p-2 rounded-md transition-colors">
                    <Image src="/icons/sina.svg" alt='github' width="20" height="20" />
                    <span>Weibo</span>
                </a>

                <a href="#" className="flex items-center space-x-2 text-gray-700 hover:bg-gray-50 p-2 rounded-md transition-colors">
                    <Image src="/icons/x.svg" alt='github' width="20" height="20" />
                    <span>X</span>
                </a>
            </div>

            {/* Divider */}
            <div className="border-t border-gray-200 my-3"></div>

            {/* QR Code Section */}
            <div className="text-sm text-gray-600 mb-2">关注官方微信公众号</div>
            <div className="w-full h-32 bg-gray-100 rounded-md flex items-center justify-center">
                <svg className="w-8 h-8 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </div>
        </div>
    );
};

export default SocialLinks;
