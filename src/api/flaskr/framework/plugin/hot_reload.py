import importlib
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from flask import Flask


class PluginHotReloader:
    def __init__(self, app: Flask):
        self.app = app
        self.plugin_dir = "flaskr/plugins"  # plugin dir
        self.watched_files = {}
        self.observer = Observer()

    def start(self):
        """1111111"""
        event_handler = PluginFileHandler(self)
        self.observer.schedule(event_handler, self.plugin_dir, recursive=True)
        self.observer.start()
        self.app.logger.info("Plugin hot reload started")

    def stop(self):
        """停止热加载监听"""
        self.observer.stop()
        self.observer.join()

    def reload_plugin(self, plugin_path: str):
        """重新加载单个插件"""
        try:
            # 1. unload plugin
            self._unload_plugin(plugin_path)

            # 2. reload module
            module_name = plugin_path.replace("/", ".").replace(".py", "")
            module = importlib.import_module(module_name)
            importlib.reload(module)

            # 3. register plugin
            self._register_plugin(module)

            self.app.logger.info(f"Hot reload plugin success: {plugin_path}")
        except Exception as e:
            self.app.logger.error(
                f"Hot reload plugin failed: {plugin_path}, error: {str(e)}"
            )

    def _unload_plugin(self, plugin_path: str):
        """Unload a plugin and clean up its resources

        Args:
            plugin_path: Path to the plugin file

        Steps:
            1. Get module name from path
            2. Find plugin instance
            3. Call lifecycle hooks
            4. Clean up registered extensions
            5. Remove from sys.modules
        """
        try:
            import sys
            from .plugin_manager import plugin_manager

            # Convert path to module name
            module_name = plugin_path.replace("/", ".").replace(".py", "")

            # Get module if it exists
            if module_name in sys.modules:
                module = sys.modules[module_name]
                # Call unload hook if plugin class exists
                if hasattr(module, "Plugin"):
                    plugin = module.Plugin()
                    if hasattr(plugin, "on_unload"):
                        plugin.on_unload()
                # Clean up registered extensions
                for func_name in list(plugin_manager.extension_functions.keys()):
                    if func_name.startswith(module_name):
                        plugin_manager.clear_extension(func_name)
                # Remove module from sys.modules
                del sys.modules[module_name]

            self.app.logger.info(f"Plugin unloaded: {module_name}")

        except Exception as e:
            self.app.logger.error(f"Failed to unload plugin {plugin_path}: {str(e)}")

    def _register_plugin(self, module):
        """Register a newly loaded plugin

        Args:
            module: The reloaded module object

        Steps:
            1. Initialize plugin class if exists
            2. Call lifecycle hooks
            3. Register new extensions
        """
        try:
            # Initialize plugin if Plugin class exists
            if hasattr(module, "Plugin"):
                plugin = module.Plugin()

                # Call load hooks
                if hasattr(plugin, "on_load"):
                    plugin.on_load()
                if hasattr(plugin, "on_reload"):
                    plugin.on_reload()

            self.app.logger.info(f"Plugin registered: {module.__name__}")

        except Exception as e:
            self.app.logger.error(
                f"Failed to register plugin {module.__name__}: {str(e)}"
            )


class PluginFileHandler(FileSystemEventHandler):
    def __init__(self, reloader: PluginHotReloader):
        self.reloader = reloader
        self.last_reload_time = {}  # Track last reload time per file
        self.min_reload_interval = 1.0  # Minimum seconds between reloads

    def on_modified(self, event):
        if event.is_directory:
            return

        if not event.src_path.endswith(".py"):
            return

        # Check if enough time has passed since last reload
        current_time = time.time()
        last_time = self.last_reload_time.get(event.src_path, 0)

        if current_time - last_time < self.min_reload_interval:
            return

        self.last_reload_time[event.src_path] = current_time
        self.reloader.reload_plugin(event.src_path)
