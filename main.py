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
    _shader_parameters = {}

    _uniform_pattern = re.compile(
        r"^\s*uniform\s+float\s+([A-Za-z_]\w*)\s*"
        r"(?:<(?P<annotations>.*?)>)?\s*=\s*"
        r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*;",
        re.MULTILINE | re.DOTALL,
    )

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
        # Keep the legacy CAS controls behaving as before while still giving
        # unannotated scalar uniforms a useful generic range.
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

            # ReShade runtime-provided uniforms (timer, frametime, etc.) are not
            # user parameters even if a shader happens to give them an initializer.
            if re.search(r"\bsource\s*=", annotations, re.IGNORECASE):
                continue

            value = float(match.group("value"))
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

    async def get_shader_parameters(self, shader_name: str):
        parameters = Plugin._parse_shader_parameters(shader_name)
        stored = Plugin._stored_parameters_for(shader_name)
        for parameter in parameters:
            if parameter["name"] in stored:
                parameter["value"] = float(stored[parameter["name"]])
        return parameters

    @staticmethod
    def _write_shader_parameters(shader_name: str, values: dict):
        if not values:
            return

        fx_file = Plugin._shader_path(shader_name)
        if fx_file is None or not fx_file.exists():
            return

        try:
            text = fx_file.read_text(encoding="utf-8", errors="replace")
            changed = False

            for name, value in values.items():
                pattern = re.compile(
                    rf"(^\s*uniform\s+float\s+{re.escape(name)}\s*"
                    rf"(?:<.*?>)?\s*=\s*)"
                    rf"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
                    rf"(\s*;)",
                    re.MULTILINE | re.DOTALL,
                )
                replacement_value = f"{float(value):.6f}"
                text, count = pattern.subn(
                    lambda m: m.group(1) + replacement_value + m.group(3),
                    text,
                    count=1,
                )
                if count:
                    changed = True
                else:
                    logger.warning(f"Uniform {name} not found in {shader_name}")

            if changed:
                fx_file.write_text(text, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to update shader parameters in {shader_name}: {e}")

    @staticmethod
    def _apply_stored_parameters(shader_name: str):
        Plugin._write_shader_parameters(shader_name, Plugin._stored_parameters_for(shader_name))

    async def set_shader_parameter(self, shader_name: str, parameter_name: str, value: float):
        definitions = {p["name"]: p for p in Plugin._parse_shader_parameters(shader_name)}
        definition = definitions.get(parameter_name)
        if definition is None:
            logger.warning(f"Unknown shader parameter {parameter_name} for {shader_name}")
            return False

        numeric_value = float(value)
        numeric_value = max(float(definition["min"]), min(float(definition["max"]), numeric_value))

        if shader_name not in Plugin._shader_parameters or not isinstance(Plugin._shader_parameters[shader_name], dict):
            Plugin._shader_parameters[shader_name] = {}
        Plugin._shader_parameters[shader_name][parameter_name] = numeric_value
        Plugin._write_shader_parameters(shader_name, {parameter_name: numeric_value})
        Plugin.save_config()

        if Plugin._enabled and Plugin._current == shader_name:
            await Plugin._run_shader_script(shader_name, "true")
        return True

    @staticmethod
    def load_config():
        try:
            Plugin._shader_parameters = {}
            if not os.path.exists(config_file):
                return
            with open(config_file, "r") as f:
                data = json.load(f)
                app_config = data.get(Plugin._appid, {})
                Plugin._enabled = app_config.get("enabled", False)
                Plugin._current = app_config.get("current", "None")
                Plugin._shader_parameters = app_config.get("shader_parameters", {})
                if not isinstance(Plugin._shader_parameters, dict):
                    Plugin._shader_parameters = {}

                # One-time compatibility with the previous CAS-only config format.
                if "CAS.fx" not in Plugin._shader_parameters:
                    legacy = {}
                    if "contrast" in app_config:
                        legacy["Contrast"] = float(app_config["contrast"])
                    if "sharpness" in app_config:
                        legacy["Sharpness"] = float(app_config["sharpness"])
                    if legacy:
                        Plugin._shader_parameters["CAS.fx"] = legacy
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
                "shader_parameters": Plugin._shader_parameters,
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
        return Plugin._get_all_shaders()

    async def get_shader_enabled(self):
        return Plugin._enabled

    async def get_current_shader(self):
        return Plugin._current

    async def set_current_game_info(self, appid: str, appname: str):
        Plugin._appid = appid
        Plugin._appname = appname
        decky_plugin.logger.info(f"Current game info received: AppID={appid}, Name={appname}")
        prev_enabled = Plugin._enabled
        prev_current = Plugin._current
        Plugin.load_config()
        if Plugin._enabled and not prev_enabled:
            await Plugin.apply_shader(self)
        elif prev_enabled and not Plugin._enabled:
            await Plugin.toggle_shader(self, "None")
        elif Plugin._enabled and Plugin._current != prev_current:
            await Plugin.apply_shader(self, force="false")
        elif Plugin._enabled and Plugin._current != "None":
            # Re-apply because changing games may have loaded a different set of
            # persisted parameters for the same shader.
            await Plugin.apply_shader(self, force="false")

    async def set_shader_enabled(self, isEnabled):
        Plugin._enabled = isEnabled
        Plugin.save_config()

    @staticmethod
    async def _run_shader_script(shader_name: str, force: str = "true"):
        logger.info("Applying shader " + shader_name)
        try:
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = ""
            args = [shaders_folder + "/set_shader.sh", shader_name, destination_folder]
            if force is not None:
                args.append(force)
            ret = subprocess.run(args, capture_output=True, env=env)
            logger.info(ret)
        except Exception:
            logger.exception("Apply shader")

    async def apply_shader(self, force: str = "true"):
        if Plugin._enabled:
            shader = Plugin._current
            if shader != "None":
                Plugin._apply_stored_parameters(shader)
            Plugin.save_config()
            await Plugin._run_shader_script(shader, force)

    async def set_shader(self, shader_name):
        Plugin._current = shader_name
        Plugin.save_config()
        if Plugin._enabled:
            if shader_name != "None":
                Plugin._apply_stored_parameters(shader_name)
            await Plugin._run_shader_script(shader_name, None)

    async def toggle_shader(self, shader_name):
        if shader_name != "None":
            Plugin._apply_stored_parameters(shader_name)
        await Plugin._run_shader_script(shader_name, None)

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
