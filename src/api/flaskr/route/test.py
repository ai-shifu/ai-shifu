

import time
from  ..dao import run_with_redis
from  .common import bypass_token_validation


def register_test_routes(app,prefix='/test'):
    @bypass_token_validation
    @app.route( prefix+'/test', methods=['GET'])
    def test():
        def func(i):
            time.sleep(5)
            return 1
        run_with_redis(app, 'test', 10,func, [1])
        return 'Hello, World!'
    return app