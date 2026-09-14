# Reshadeck

Reshadeck is a Decky Loader plugin for selecting and applying Gamescope ReShade shaders on Steam Deck and other compatible handhelds.

The plugin ships with a small curated shader set. Additional `.fx` shaders can be placed directly in:

```text
~/.local/share/gamescope/reshade/Shaders
```

## Features

- Select and enable a shader for the currently running app.
- Store shader selection, enabled state, and configurable parameter values per Steam AppID.
- Automatically discover initialized scalar `uniform float` parameters from compatible ReShade shaders.
- Use ReShade `ui_label`, `ui_min`, `ui_max`, and `ui_step` annotations when provided.
- Apply parameter changes automatically after a 500 ms debounce.
- Batch multiple parameter changes into a single shader reload when they are adjusted close together.
- Reset a shader's saved parameters to the defaults defined in the original `.fx` file.
- Force a fresh shader compilation with **Reload Shader**, even when the parameter values have not changed.
- Keep original shader files unchanged. Per-game parameter values are applied to temporary shader copies.
- Synchronize the currently running Steam app when the plugin frontend starts, then check it every 5 seconds and load the saved shader state when its AppID changes.

## Shader parameters

Reshadeck exposes initialized scalar float uniforms such as:

```hlsl
uniform float Sharpness <
    ui_label = "Sharpness";
    ui_min = 0.0;
    ui_max = 2.0;
    ui_step = 0.05;
> = 1.0;
```

Runtime-provided uniforms using a ReShade `source` annotation are ignored, for example:

```hlsl
uniform float iGlobalTime < source = "timer"; >;
```

If a configurable float does not provide UI range annotations, Reshadeck generates a reasonable fallback slider range from its default value.

Parameter overrides are stored per game. Returning a parameter to its shader-defined default removes the stored override. **Reset Defaults** is only available when the selected shader currently has overrides to reset.

At present, the generic parameter UI is intended for scalar `float` uniforms. Integer, boolean, vector, color, combo, and other ReShade UI types are not exposed by the plugin.

## Applying shaders

Selecting a shader applies it automatically when shaders are enabled. Parameter adjustments also apply automatically after the debounce period.

**Reload Shader** is therefore primarily a manual force-reload control. It creates a fresh temporary shader filename so Gamescope recompiles the effect even when no parameter changed. The button is disabled when shaders are disabled or no shader is selected.

The polling controller reads `Router.MainRunningApp`, performs one immediate synchronization when the plugin frontend starts, and then checks again every 5 seconds. When the AppID differs from the last successfully synchronized AppID, it calls the backend directly with the new AppID and app name. The backend then loads that app's saved configuration and applies or disables the shader state as required. This path does not depend on the Reshadeck panel being open.

Opening or refreshing the Reshadeck UI does not update backend app state. The panel only reads the current Router app for display and reads the already synchronized shader state from the backend. App switching therefore has a single control path: the polling controller.

## Custom shaders

Place custom `.fx` files directly in the root of:

```text
~/.local/share/gamescope/reshade/Shaders
```

Subdirectories are not scanned by the plugin.

## Caveats

- Shader compatibility depends on the Gamescope ReShade implementation; not every ReShade feature or shader is supported.
- Some shaders can significantly reduce performance, cause dropped frames, or in extreme cases destabilize Gamescope.
- The configurable parameter parser currently targets initialized scalar float uniforms rather than the complete ReShade UI type system.
- Gamescope applies the shader as a post-process effect, so some system overlays or capture paths may not include the shader output.

## Steam Deck OLED fringing shader

The subpixel layout of some Steam Deck OLED panels can produce visible color fringing for some users. Reshadeck includes a shader based on the approach described here:

https://gist.github.com/safijari/1b936cbbdebe341fbe340bcfecb04450

## More shaders

Useful shader collections include:

- https://github.com/Matsilagi/RSRetroArch/tree/main/Shaders
- https://framedsc.com/ReshadeGuides/shaderscatalogue.htm
