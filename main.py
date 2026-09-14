import decky_plugin
from pathlib import Path
import json
import os
import subprocess
import shutil
import asyncio
import re
import tempfile

logger = decky_plugin.logger

destination_folder = decky_plugin.DECKY_USER_HOME + "/.local/share/gamescope/reshade/Shaders"
shaders_folder = decky_plugin.DECKY_PLUGIN_DIR + "/shaders"
config_file = decky_plugin.DECKY_PLUGIN_SETTINGS_DIR + "/config.json"


class Plugin:
    _enabled = False
    _current = "None"
    _appid = "Unknown"
    _appname = "Unknown"
    _shader_parameters = {}
    _game_info_initialized = False
    _apply_lock = None

    # Match one uniform declaration only. The initializer is optional so runtime
    # uniforms such as "source = timer" cannot consume a later user uniform.
    _uniform_pattern = re.compile(
        r"^\s*uniform\s+float\s+([A-Za-z_]\w*)\s*"
        r"(?:<(?P<annotations>[^>]*)>)?\s*"
        r"(?:=\s*(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?))?\s*;",
        re.MULTILINE,
    )

    @staticmethod
    def _get_apply_lock():
        if Plugin._apply_lock is None:
            Plugin._apply_lock = asyncio.Lock()
        return Plugin._apply_lock

    @staticmethod
    def _shader_path(shader_name: str) -> Path | None:
        if not shader_name or shader_name == "None":
            return None
        if Path(shader_name).name != shader_name or shader_name not in Plugin._get_all_shaders():
            logger.warning(f"Invalid shader name: {shader_name}")
            return None
        return Path(destination_folder) / shader_name

    @staticmethod
    def _annotation_number(annotations: str, name: str) -> float | None:
        match = re.search(
            rf"\b{name}\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*;?",
            annotations,
            re.IGNORECASE,
        )
        return float(match.group(1)) if match else None

    @staticmethod
    def _annotation_string(annotations: str, name: str) -> str | None:
        match = re.search(rf'\b{name}\s*=\s*"([^"]*)"\s*;?', annotations, re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def _fallback_slider_range(value: float) -> tuple[float, float, float]:
        if 0.0 <= value <= 2.0:
            return 0.0, 2.0, 0.1
        if value >= 0.0:
            maximum = max(1.0, value * 2.0)
            return 0.0, maximum, max(0.01, maximum / 100.0)
        extent = max(1.0, abs(value) * 2.0)
        return -extent, extent, max(0.01, (extent * 2.0) / 100.0)

    @staticmethod
    def _parse_shader_parameters(shader_name: str) -> list[dict]:
        fx_file = Plugin._shader_path(shader_name)
        if fx_file is None or not fx_file.exists():
            return []

        try:
            text = fx_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read shader parameters from {shader_name}: {e}")
            return []

        parameters = []
        for match in Plugin._uniform_pattern.finditer(text):
            name = match.group(1)
            annotations = match.group("annotations") or ""
            value_text = match.group("value")

            if re.search(r"\bsource\s*=", annotations, re.IGNORECASE):
                continue
            if value_text is None:
                continue

            value = float(value_text)
            minimum = Plugin._annotation_number(annotations, "ui_min")
            maximum = Plugin._annotation_number(annotations, "ui_max")
            step = Plugin._annotation_number(annotations, "ui_step")
            label = Plugin._annotation_string(annotations, "ui_label") or name

            fallback_min, fallback_max, fallback_step = Plugin._fallback_slider_range(value)
            if minimum is None:
                minimum = fallback_min
            if maximum is None:
                maximum = fallback_max
            if maximum < minimum:
                minimum, maximum = maximum, minimum
            if step is None or step <= 0:
                step = fallback_step

            parameters.append({
                "name": name,
                "label": label,
                "value": value,
                "min": minimum,
                "max": maximum,
                "step": step,
            })

        return parameters

    @staticmethod
    def _stored_parameters_for(shader_name: str) -> dict:
        stored = Plugin._shader_parameters.get(shader_name, {})
        return stored if isinstance(stored, dict) else {}

    @staticmethod
    def _validated_stored_parameters(shader_name: str, persist: bool = True) -> dict:
        definitions = {p["name"]: p for p in Plugin._parse_shader_parameters(shader_name)}
        stored = Plugin._stored_parameters_for(shader_name)
        validated = {}
        changed = False

        for name, raw_value in list(stored.items()):
            definition = definitions.get(name)
            if definition is None:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                logger.warning(f"Ignoring invalid stored value for {shader_name}:{name}")
                continue

            clamped = max(float(definition["min"]), min(float(definition["max"]), value))
            validated[name] = clamped
            if raw_value != clamped:
                stored[name] = clamped
                changed = True

        if changed:
            Plugin._shader_parameters[shader_name] = stored
            if persist:
                Plugin.save_config()

        return validated

    async def get_shader_parameters(self, shader_name: str):
        parameters = Plugin._parse_shader_parameters(shader_name)
        stored = Plugin._validated_stored_parameters(shader_name)
        for parameter in parameters:
            if parameter["name"] in stored:
                parameter["value"] = stored[parameter["name"]]
        return parameters

    @staticmethod
    def _patch_shader_bytes(shader_name: str, values: dict) -> bytes | None:
        fx_file = Plugin._shader_path(shader_name)
        if fx_file is None or not fx_file.exists():
            return None

        try:
            data = fx_file.read_bytes()
            for name, value in values.items():
                name_bytes = re.escape(name.encode("ascii"))
                pattern = re.compile(
                    rb"(^[ \t]*uniform[ \t]+float[ \t]+" + name_bytes +
                    rb"[ \t]*(?:<[^>]*>)?[ \t\r\n]*=[ \t]*)"
                    rb"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
                    rb"([ \t]*;)",
                    re.MULTILINE,
                )
                replacement_value = f"{float(value):.6f}".encode("ascii")
                data, count = pattern.subn(
                    lambda m: m.group(1) + replacement_value + m.group(3),
                    data,
                    count=1,
                )
                if count != 1:
                    logger.error(f"Uniform {name} could not be patched in {shader_name}")
                    return None
            return data
        except Exception as e:
            logger.error(f"Failed to prepare shader {shader_name}: {e}")
            return None

    @staticmethod
    def _create_staged_shader(shader_name: str, values: dict) -> str | None:
        data = Plugin._patch_shader_bytes(shader_name, values)
        if data is None:
            return None

        path = None
        try:
            fd, path = tempfile.mkstemp(prefix="reshadeck_", suffix=".fx")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            return path
        except Exception as e:
            logger.error(f"Failed to stage shader {shader_name}: {e}")
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            return None

    @staticmethod
    def load_config():
        try:
            Plugin._shader_parameters = {}
            if not os.path.exists(config_file):
                Plugin._enabled = False
                Plugin._current = "None"
                return

            with open(config_file, "r") as f:
                data = json.load(f)

            app_config = data.get(Plugin._appid, {})
            Plugin._enabled = app_config.get("enabled", False)
            Plugin._current = app_config.get("current", "None")
            Plugin._shader_parameters = app_config.get("shader_parameters", {})
            if not isinstance(Plugin._shader_parameters, dict):
                Plugin._shader_parameters = {}

            if "CAS.fx" not in Plugin._shader_parameters:
                legacy = {}
                if "contrast" in app_config:
                    legacy["Contrast"] = float(app_config["contrast"])
                if "sharpness" in app_config:
                    legacy["Sharpness"] = float(app_config["sharpness"])
                if legacy:
                    Plugin._shader_parameters["CAS.fx"] = legacy

            if Plugin._current != "None" and Plugin._current not in Plugin._get_all_shaders():
                logger.warning(f"Configured shader {Plugin._current} is missing; selecting None")
                Plugin._current = "None"
                Plugin.save_config()
        except Exception as e:
            logger.error(f"Failed to read config: {e}")
            Plugin._enabled = False
            Plugin._current = "None"
            Plugin._shader_parameters = {}

    @staticmethod
    def save_config():
        temp_path = None
        try:
            settings_dir = Path(os.path.dirname(config_file))
            settings_dir.mkdir(parents=True, exist_ok=True)

            data = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    data = {}

            data[Plugin._appid] = {
                "appname": Plugin._appname,
                "enabled": Plugin._enabled,
                "current": Plugin._current,
                "shader_parameters": Plugin._shader_parameters,
            }

            fd, temp_path = tempfile.mkstemp(
                prefix=".config_",
                suffix=".json",
                dir=str(settings_dir),
                text=True,
            )
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, config_file)
            temp_path = None
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    @staticmethod
    def _get_all_shaders():
        legacy_cas_temp = re.compile(r"^CAS_[0-9]{4}[A-Za-z0-9]{4}\.fx$")
        previous_generic_temp = re.compile(r"^RESHADCK_.+_[0-9a-f]{10}(?:_[A-Za-z0-9]{4})?\.fx$")
        previous_hash_temp = re.compile(r"^.+_[0-9a-f]{10}[A-Za-z0-9]{4}\.fx$")
        current_temp = re.compile(r"^(.+)_([A-Za-z0-9]{4})\.fx$")

        shader_dir = Path(destination_folder)

        def is_temp(name: str) -> bool:
            if legacy_cas_temp.match(name) or previous_generic_temp.match(name) or previous_hash_temp.match(name):
                return True
            match = current_temp.match(name)
            if not match:
                return False
            original_name = match.group(1) + ".fx"
            return (shader_dir / original_name).is_file()

        return sorted(
            str(p.name)
            for p in shader_dir.glob("*.fx")
            if not is_temp(p.name)
        )

    async def get_shader_list(self):
        return Plugin._get_all_shaders()

    async def get_shader_enabled(self):
        return Plugin._enabled

    async def get_current_shader(self):
        return Plugin._current

    async def set_current_game_info(self, appid: str, appname: str):
        appid = str(appid)
        appname = str(appname)

        if Plugin._game_info_initialized and appid == Plugin._appid:
            Plugin._appname = appname
            return False

        prev_enabled = Plugin._enabled
        Plugin._appid = appid
        Plugin._appname = appname
        Plugin._game_info_initialized = True
        logger.info(f"Current game info received: AppID={appid}, Name={appname}")

        Plugin.load_config()

        if Plugin._enabled:
            await Plugin.apply_shader(self, force="false")
        elif prev_enabled:
            await Plugin._apply_shader_effect(
                "None",
                expected_appid=Plugin._appid,
            )
        return True

    async def set_shader_enabled(self, isEnabled):
        Plugin._enabled = bool(isEnabled)
        Plugin.save_config()

    @staticmethod
    async def _run_shader_script(
        shader_name: str,
        force: str | None = None,
        source_override: str | None = None,
    ) -> bool:
        logger.info("Applying shader " + shader_name)
        try:
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = ""
            args = [shaders_folder + "/set_shader.sh", shader_name, destination_folder]
            if force is not None:
                args.append(force)
                if source_override is not None:
                    args.append(source_override)

            ret = await asyncio.to_thread(
                subprocess.run,
                args,
                capture_output=True,
                env=env,
                text=True,
            )
            if ret.returncode != 0:
                logger.error(
                    f"Shader apply failed ({ret.returncode}) for {shader_name}: "
                    f"{ret.stderr.strip() or ret.stdout.strip()}"
                )
                return False

            if ret.stdout.strip():
                logger.info(ret.stdout.strip())
            return True
        except Exception:
            logger.exception("Apply shader")
            return False

    @staticmethod
    async def _apply_shader_effect(
        shader_name: str,
        force_reload: bool = False,
        expected_appid: str | None = None,
    ) -> bool:
        async with Plugin._get_apply_lock():
            if expected_appid is not None and Plugin._appid != expected_appid:
                logger.warning(
                    f"Ignoring stale shader apply for AppID={expected_appid}; "
                    f"current AppID={Plugin._appid}"
                )
                return False

            if shader_name == "None":
                return await Plugin._run_shader_script("None")

            fx_file = Plugin._shader_path(shader_name)
            if fx_file is None or not fx_file.exists():
                logger.error(f"Cannot apply missing shader {shader_name}")
                if Plugin._current == shader_name:
                    Plugin._current = "None"
                    Plugin.save_config()
                return await Plugin._run_shader_script("None")

            values = Plugin._validated_stored_parameters(shader_name)
            if not values and not force_reload:
                return await Plugin._run_shader_script(shader_name)

            staged_path = Plugin._create_staged_shader(shader_name, values)
            if staged_path is None:
                return False

            try:
                return await Plugin._run_shader_script(
                    shader_name,
                    "true",
                    staged_path,
                )
            finally:
                try:
                    os.unlink(staged_path)
                except OSError:
                    pass

    async def set_shader_parameter(
        self,
        shader_name: str,
        parameter_name: str,
        value: float,
    ):
        definitions = {p["name"]: p for p in Plugin._parse_shader_parameters(shader_name)}
        definition = definitions.get(parameter_name)
        if definition is None:
            logger.warning(f"Unknown shader parameter {parameter_name} for {shader_name}")
            return False

        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return False

        numeric_value = max(
            float(definition["min"]),
            min(float(definition["max"]), numeric_value),
        )

        if shader_name not in Plugin._shader_parameters or not isinstance(
            Plugin._shader_parameters[shader_name], dict
        ):
            Plugin._shader_parameters[shader_name] = {}

        Plugin._shader_parameters[shader_name][parameter_name] = numeric_value
        Plugin.save_config()

        if Plugin._enabled and Plugin._current == shader_name:
            return await Plugin._apply_shader_effect(
                shader_name,
                force_reload=True,
            )
        return True

    async def reset_shader_parameters(self, shader_name: str):
        shader_name = str(shader_name)
        if not Plugin._parse_shader_parameters(shader_name):
            return False

        Plugin._shader_parameters.pop(shader_name, None)
        Plugin.save_config()

        if Plugin._enabled and Plugin._current == shader_name:
            return await Plugin._apply_shader_effect(
                shader_name,
                force_reload=True,
            )
        return True

    async def apply_shader(self, force: str = "true"):
        if not Plugin._enabled:
            return False

        shader = Plugin._current
        Plugin.save_config()
        return await Plugin._apply_shader_effect(
            shader,
            force_reload=(force == "true"),
            expected_appid=Plugin._appid,
        )

    async def set_shader(self, shader_name):
        shader_name = str(shader_name)
        if shader_name != "None" and Plugin._shader_path(shader_name) is None:
            logger.warning(f"Cannot select missing shader {shader_name}")
            Plugin._current = "None"
            Plugin.save_config()
            if Plugin._enabled:
                await Plugin._apply_shader_effect(
                    "None",
                    expected_appid=Plugin._appid,
                )
            return False

        Plugin._current = shader_name
        Plugin.save_config()
        if Plugin._enabled:
            return await Plugin._apply_shader_effect(
                shader_name,
                force_reload=False,
                expected_appid=Plugin._appid,
            )
        return True

    async def toggle_shader(self, shader_name):
        shader_name = str(shader_name)
        if shader_name != "None" and Plugin._shader_path(shader_name) is None:
            logger.warning(f"Cannot toggle missing shader {shader_name}")
            if Plugin._current == shader_name:
                Plugin._current = "None"
                Plugin.save_config()
            return await Plugin._apply_shader_effect(
                "None",
                expected_appid=Plugin._appid,
            )

        return await Plugin._apply_shader_effect(
            shader_name,
            force_reload=False,
            expected_appid=Plugin._appid,
        )

    async def get_current_effect(self):
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["xprop", "-root", "GAMESCOPE_RESHADE_EFFECT"],
                env={"DISPLAY": ":0"},
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and "=" in result.stdout:
                effect = result.stdout.split("=", 1)[1].strip().strip('"')
                return {"effect": effect}
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
                await Plugin.apply_shader(self, force="false")
        except Exception:
            decky_plugin.logger.exception("main")
