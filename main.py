import decky_plugin
from pathlib import Path
import json
import os
import subprocess
import shutil
import asyncio
import re

logger = decky_plugin.logger

destination_folder = decky_plugin.DECKY_USER_HOME + "/.local/share/gamescope/reshade/Shaders"
shaders_folder = decky_plugin.DECKY_PLUGIN_DIR + "/shaders"
config_file = decky_plugin.DECKY_PLUGIN_SETTINGS_DIR + "/config.json"

class Plugin:
    _enabled = False
    _current = "None"
    _appid = "Unknown"
    _appname = "Unknown"
    _contrast = 0.0
    _sharpness = 1.0
    _uniform_patterns = {
        name: re.compile(
            rf"(uniform\s+float\s+{name}\s*=[^0-9.\-+]*)([-+]?\d+\.\d{{6}})(\s*;)",
            re.ASCII
        )
        for name in ("Contrast","Sharpness")
    }
    
    async def set_contrast(self, value: float):
        Plugin._contrast = value

    async def set_sharpness(self, value: float):
        Plugin._sharpness = value
        
    async def update_cas_shader(self):
        await Plugin._update_uniform_in_fx("Contrast", Plugin._contrast)
        await Plugin._update_uniform_in_fx("Sharpness", Plugin._sharpness)

    @staticmethod
    async def _update_uniform_in_fx(uniform_name: str, value: float):
        # logger.info(f"Updating {uniform_name} to {value}")
        fx_file   = Path(destination_folder) / "CAS.fx"
        if not fx_file.exists():
            logger.error(f"Cannot patch—{fx_file} not found")
            return
        pattern   = Plugin._uniform_patterns[uniform_name]
        new_val   = f"{value:0>2.6f}".encode("ascii")
        try:
            with open(fx_file, "r+b") as f:
                header = f.read(512)
                # use the compiled pattern directly
                match = pattern.search(header.decode("ascii"))
                if not match:
                    logger.warning(f"{uniform_name} not found in {fx_file.name}")
                    return
                start, end = match.start(2), match.end(2)
                # seek back to absolute offset of the number
                f.seek(start)
                f.write(new_val)
                f.flush()
                logger.info(f"{uniform_name} → {new_val.decode()} in place")
        except Exception as e:
            logger.error(f"Patch FX failed: {e}")
            
    async def get_contrast(self):
        return Plugin._contrast
        # return await asyncio.to_thread(Plugin._read_uniform_from_fx, "Contrast")
    
    async def get_sharpness(self):
        return Plugin._sharpness
        # return await asyncio.to_thread(Plugin._read_uniform_from_fx, "Sharpness")

    @staticmethod
    def _read_uniform_from_fx(uniform_name: str) -> float | None:
        fx_file = Path(destination_folder) / "CAS.fx"
        if not fx_file.exists():
            logger.error(f"Cannot read—{fx_file} not found")
            return None
        pattern = Plugin._uniform_patterns[uniform_name]
        try:
            with open(fx_file, "r", encoding="ascii") as f:
                header = f.read(512)
                match = pattern.search(header)
                if match:
                    value = float(match.group(2))
                    logger.info(f"Read {uniform_name} = {value}")
                    return value
                else:
                    logger.warning(f"{uniform_name} not found in {fx_file.name}")
                    return None
        except Exception as e:
            logger.error(f"Failed to read {uniform_name}: {e}")
            return None

    @staticmethod
    def load_config():
        try:
            if not os.path.exists(config_file):
                return
            with open(config_file, "r") as f:
                data = json.load(f)
                app_config = data.get(Plugin._appid, {})
                Plugin._enabled = app_config.get("enabled", False)
                Plugin._current = app_config.get("current", "None")
                Plugin._contrast = app_config.get("contrast", 0.0)
                Plugin._sharpness = app_config.get("sharpness", 1.0)
        except Exception as e:
            logger.error(f"Failed to read config: {e}")

    @staticmethod
    def save_config():
        try:
            Path(os.path.dirname(config_file)).mkdir(parents=True, exist_ok=True)
            data = {}
            if os.path.exists(config_file):
                with open(config_file, "r") as f:
                    data = json.load(f)
            data[Plugin._appid] = {
                "appname": Plugin._appname,
                "enabled": Plugin._enabled,
                "current": Plugin._current,
                "contrast": Plugin._contrast,
                "sharpness": Plugin._sharpness
            }
            with open(config_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
            
    @staticmethod        
    def _get_all_shaders():
        temp_pattern = re.compile(r"^CAS_[0-9]{4}[A-Za-z0-9]{4}\.fx$")
        return sorted(
            str(p.name)
            for p in Path(destination_folder).glob("*.fx")
            if not temp_pattern.match(p.name)
        )

    async def get_shader_list(self):
        shaders = Plugin._get_all_shaders()
        return shaders

    async def get_shader_enabled(self):
        return Plugin._enabled        

    async def get_current_shader(self):
        return Plugin._current
        
    async def set_current_game_info(self, appid: str, appname: str):
        Plugin._appid = appid
        Plugin._appname = appname
        decky_plugin.logger.info(f"Current game info received: AppID={appid}, Name={appname}")
        prevEnabled = Plugin._enabled
        prevCurrent = Plugin._current
        Plugin.load_config()
        if Plugin._enabled and not prevEnabled:
            await Plugin.apply_shader(self)
        elif prevEnabled and not Plugin._enabled:
            await Plugin.toggle_shader(self, "None")
        elif Plugin._enabled and (Plugin._current != prevCurrent or Plugin._current == "CAS.fx"):
            await Plugin.apply_shader(self, force="false")

    async def set_shader_enabled(self, isEnabled):
        Plugin._enabled = isEnabled
        Plugin.save_config()

    async def apply_shader(self, force: str = "true"):
        if Plugin._enabled:
            shader = Plugin._current
            if shader == "CAS.fx":
                Plugin.save_config()
                await Plugin.update_cas_shader(self)
            logger.info("Applying shader " + shader)
            try:
                ret = subprocess.run([shaders_folder + "/set_shader.sh", shader, destination_folder, force], capture_output=True)
                logger.info(ret)
            except Exception:
                logger.exception("Apply shader")

    async def set_shader(self, shader_name):
        Plugin._current = shader_name
        Plugin.save_config()
        if Plugin._enabled:
            if shader_name == "CAS.fx":
                await Plugin.update_cas_shader(self)
            logger.info("Setting and applying shader " + shader_name)
            try:
                ret = subprocess.run([shaders_folder + "/set_shader.sh", shader_name, destination_folder], capture_output=True)
                decky_plugin.logger.info(ret)
            except Exception:
                decky_plugin.logger.exception("Set shader")

    async def toggle_shader(self, shader_name):
        if shader_name == "CAS.fx":
            await Plugin.update_cas_shader(self)
        logger.info("Applying shader " + shader_name)
        try:
            ret = subprocess.run([shaders_folder + "/set_shader.sh", shader_name, destination_folder], capture_output=True)
            decky_plugin.logger.info(ret)
        except Exception:
            decky_plugin.logger.exception("Toggle shader")
            
    async def get_current_effect(self):
        try:
            result = subprocess.run(
                ['xprop', '-root', 'GAMESCOPE_RESHADE_EFFECT'],
                env={"DISPLAY": ":0"},
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and "=" in result.stdout:
                effect = result.stdout.split('=', 1)[1].strip().strip('"')
                return {"effect": effect}
            else:
                return {"effect": "None"}
        except Exception as e:
            logger.error(f"Failed to get current effect: {e}")
            return {"effect": "None"}

    async def _main(self):
        try:
            Path(destination_folder).mkdir(parents=True, exist_ok=True)
            for item in Path(shaders_folder).glob("*.fx"):
                try:
                    dest_path = shutil.copy(item, destination_folder)
                    os.chmod(dest_path, 0o644)
                except Exception:
                    decky_plugin.logger.debug(f"could not copy {item}")
            decky_plugin.logger.info("Initialized")
            decky_plugin.logger.info(str(await Plugin.get_shader_list(self)))
            Plugin.load_config()
            if Plugin._enabled:
                await asyncio.sleep(5)
                await Plugin.apply_shader(self)
        except Exception:
            decky_plugin.logger.exception("main")
