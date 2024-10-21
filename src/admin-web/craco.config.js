const cracoAlias = require("craco-alias");

module.exports = {
    // webpack: {
    //     configure:(webpackConfig, { env, paths }) => {
    //         webpackConfig.entry = './src/index.tsx';
    //         return webpackConfig;
    //     },
    // },
    plugins: [
        {
            plugin: cracoAlias,
            options: {
                baseUrl: "./src",
                source: "jsconfig",
            }
        }
    ],
    devServer:{
        client:{
            overlay: {
                errors: true,
                warnings: false,
                runtimeErrors: false, // 停止运行时错误的 overlay 提示
            }
        },

        // proxy:{
        //     'http://192.168.50.47:5800/':{
        //         target: 'http://192.168.50.47:5800',
        //         changeOrigin:true,
        //         /**
        //          * @desc 收到响应的钩子， 拦截来自后台的 response 获取其中的 cookie，并转发
        //          * @param {*} proxyRes
        //          * @param {*} req
        //          * @param {*} res
        //          */
        //         onProxyRes(proxyRes, req, res){

        //             const cookies = proxyRes.headers['set-cookie'];
        //             console.log(cookies);
        //             delete proxyRes.headers['set-cookie'];
        //             proxyRes.headers['set-cookie'] = cookies;
        //         },
        //         // onProxyReq(proxyReq){

        //         // }
        //     }
        // }

    }
}
