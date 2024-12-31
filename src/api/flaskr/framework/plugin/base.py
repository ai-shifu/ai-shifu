class BasePlugin:
    name: str = None

    def __init__(self):
        self.name = self.__class__.__name__
        self.migration_dir = None  # plugin migration dir

    def on_load(self):

        if self.migration_dir:
            self._run_migrations()

    def _run_migrations(self):
        """执行插件的migrations"""
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", self.migration_dir)
        alembic_cfg.set_main_option(
            "version_locations", self.migration_dir + "/versions"
        )

        command.upgrade(alembic_cfg, "head")

    def on_unload(self):
        """插件卸载时调用"""
        pass

    def on_reload(self):
        """插件重载时调用"""
        pass
