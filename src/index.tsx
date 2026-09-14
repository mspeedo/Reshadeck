import {
    ButtonItem,
    definePlugin,
    PanelSection,
    PanelSectionRow,
    ToggleField,
    Router,
    ServerAPI,
    staticClasses,
    Dropdown,
    DropdownOption,
    SingleDropdownOption,
    SliderField
} from "decky-frontend-lib";
import { VFC, useState, useEffect, useRef } from "react";
import { MdWbShade } from "react-icons/md";

// Global refresh function reference
let forceRefreshContent: (() => void) | null = null;

interface ShaderParameter {
    name: string;
    label: string;
    value: number;
    min: number;
    max: number;
    step: number;
}

const Content: VFC<{ serverAPI: ServerAPI }> = ({ serverAPI }) => {
    const baseShader = { data: "None", label: "No Shader" } as SingleDropdownOption;
    const [shadersEnabled, setShadersEnabled] = useState<boolean>(false);
    const [selectedShader, setSelectedShader] = useState<DropdownOption>(baseShader);
    const [shaderOptions, setShaderOptions] = useState<DropdownOption[]>([baseShader]);
    const [currentGameId, setCurrentGameId] = useState<string>("Unknown");
    const [currentGameName, setCurrentGameName] = useState<string>("Unknown");
    const [currentEffect, setCurrentEffect] = useState<string>("");
    const [shaderParameters, setShaderParameters] = useState<ShaderParameter[]>([]);
    const parameterTimeout = useRef<number | null>(null);
    const pendingParameterValues = useRef<Record<string, number>>({});
    const [reloadDisabled, setReloadDisabled] = useState(false);
    const [resetDisabled, setResetDisabled] = useState(false);
    const [refreshVersion, setRefreshVersion] = useState(0);

    const clearParameterTimeout = () => {
        if (parameterTimeout.current !== null) {
            clearTimeout(parameterTimeout.current);
            parameterTimeout.current = null;
        }
        pendingParameterValues.current = {};
    };

    forceRefreshContent = () => setRefreshVersion(v => v + 1);

    const getShaderOptions = (shaderList: string[], baseShaderOption: any) => {
        const options: DropdownOption[] = [baseShaderOption];
        for (const shader of shaderList) {
            options.push({ data: shader, label: shader } as SingleDropdownOption);
        }
        return options;
    };

    const loadShaderParameters = async (shaderName: string) => {
        if (!shaderName || shaderName === "None") {
            setShaderParameters([]);
            return;
        }

        const response = await serverAPI.callPluginMethod("get_shader_parameters", {
            shader_name: shaderName
        });
        const parameters = Array.isArray(response.result) ? response.result as ShaderParameter[] : [];
        setShaderParameters(parameters.map(parameter => ({
            ...parameter,
            value: Number(parameter.value),
            min: Number(parameter.min),
            max: Number(parameter.max),
            step: Number(parameter.step)
        })));
    };

    const refreshCurrentGameInfo = async () => {
        const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
        const appname = `${Router.MainRunningApp?.display_name || "Unknown"}`;
        setCurrentGameId(appid);
        setCurrentGameName(appname);

        await serverAPI.callPluginMethod("set_current_game_info", {
            appid,
            appname
        });
    };

    const initState = async () => {
        // This is the single frontend path that updates backend game state.
        await refreshCurrentGameInfo();

        const shaderList = (await serverAPI.callPluginMethod("get_shader_list", {})).result as string[];
        setShaderOptions(getShaderOptions(shaderList, baseShader));

        const enabledResp = await serverAPI.callPluginMethod("get_shader_enabled", {});
        const isEnabled: boolean = enabledResp.result === true || enabledResp.result === "true";
        setShadersEnabled(isEnabled);

        const curr = await serverAPI.callPluginMethod("get_current_shader", {});
        const currentShader = String(curr.result || "None");
        setSelectedShader({
            data: currentShader,
            label: (currentShader === "0" ? "None" : currentShader)
        } as SingleDropdownOption);
        await loadShaderParameters(currentShader);

        const eff = await serverAPI.callPluginMethod("get_current_effect", {});
        setCurrentEffect((eff.result as { effect: string }).effect || "");
    };

    useEffect(() => {
        initState();
    }, [refreshVersion]);

    useEffect(() => {
        return () => {
            clearParameterTimeout();
        };
    }, []);

    const decimalsForStep = (step: number) => {
        if (!isFinite(step) || step <= 0) return 2;
        const text = step.toFixed(6).replace(/0+$/, "");
        const decimal = text.indexOf(".");
        return decimal === -1 ? 0 : text.length - decimal - 1;
    };

    return (
        <PanelSection>
            <PanelSectionRow>
                <b>Current Running App</b>
            </PanelSectionRow>
            <PanelSectionRow>
                <div>
                    <div><b>ID:</b> {currentGameId}</div>
                    <div><b>Name:</b> {currentGameName}</div>
                    <div><b>Shader:</b> {currentEffect}</div>
                </div>
            </PanelSectionRow>
            <PanelSectionRow>
                <ToggleField
                    label="Enable Shaders"
                    checked={shadersEnabled}
                    onChange={async (enabled: boolean) => {
                        setShadersEnabled(enabled);
                        await serverAPI.callPluginMethod("set_shader_enabled", { isEnabled: enabled });
                        if (enabled) {
                            await serverAPI.callPluginMethod("toggle_shader", { shader_name: selectedShader.data });
                        } else {
                            await serverAPI.callPluginMethod("toggle_shader", { shader_name: "None" });
                        }
                        const eff = await serverAPI.callPluginMethod("get_current_effect", {});
                        setCurrentEffect((eff.result as { effect: string }).effect || "");
                    }}
                />
            </PanelSectionRow>
            <PanelSectionRow>
                <b>Select Shader</b>
            </PanelSectionRow>
            <PanelSectionRow>
                <Dropdown
                    menuLabel="Select shader"
                    strDefaultLabel={selectedShader.label as string}
                    rgOptions={shaderOptions}
                    selectedOption={selectedShader}
                    onChange={async (newSelectedShader: DropdownOption) => {
                        clearParameterTimeout();
                        setSelectedShader(newSelectedShader);
                        const shaderName = String(newSelectedShader.data);
                        await serverAPI.callPluginMethod("set_shader", { shader_name: shaderName });
                        await loadShaderParameters(shaderName);
                        const eff = await serverAPI.callPluginMethod("get_current_effect", {});
                        setCurrentEffect((eff.result as { effect: string }).effect || "");
                    }}
                />
            </PanelSectionRow>
            <PanelSectionRow>
                <ButtonItem
                    disabled={reloadDisabled}
                    onClick={async () => {
                        setReloadDisabled(true);
                        try {
                            await serverAPI.callPluginMethod("apply_shader", {});
                            const eff = await serverAPI.callPluginMethod("get_current_effect", {});
                            setCurrentEffect((eff.result as { effect: string }).effect || "");
                        } catch (error) {
                            console.error(error);
                        } finally {
                            setReloadDisabled(false);
                        }
                    }}
                >Reload Shader</ButtonItem>
            </PanelSectionRow>

            {shaderParameters.length > 0 && (
                <PanelSectionRow>
                    <b>{String(selectedShader.data)} parameters</b>
                </PanelSectionRow>
            )}

            {shaderParameters.map((parameter) => {
                const decimals = decimalsForStep(parameter.step);
                const scale = Math.pow(10, Math.min(decimals, 6));
                const sliderMin = Math.round(parameter.min * scale);
                const sliderMax = Math.round(parameter.max * scale);
                const sliderStep = Math.max(1, Math.round(parameter.step * scale));
                const sliderValue = Math.round(parameter.value * scale);

                return (
                    <PanelSectionRow key={parameter.name}>
                        <SliderField
                            bottomSeparator="none"
                            label={`${parameter.label}: ${parameter.value.toFixed(decimals)}`}
                            min={sliderMin}
                            max={sliderMax}
                            step={sliderStep}
                            value={sliderValue}
                            disabled={!shadersEnabled}
                            onChange={(val: number) => {
                                const realValue = val / scale;
                                setShaderParameters(current => current.map(item =>
                                    item.name === parameter.name ? { ...item, value: realValue } : item
                                ));

                                pendingParameterValues.current[parameter.name] = realValue;
                                if (parameterTimeout.current !== null) {
                                    clearTimeout(parameterTimeout.current);
                                }

                                const shaderName = String(selectedShader.data);
                                parameterTimeout.current = window.setTimeout(async () => {
                                    const values = { ...pendingParameterValues.current };
                                    pendingParameterValues.current = {};
                                    parameterTimeout.current = null;

                                    try {
                                        await serverAPI.callPluginMethod("set_shader_parameters", {
                                            shader_name: shaderName,
                                            values
                                        });
                                        const eff = await serverAPI.callPluginMethod("get_current_effect", {});
                                        setCurrentEffect((eff.result as { effect: string }).effect || "");
                                    } catch (error) {
                                        console.error(error);
                                    }
                                }, 500);
                            }}
                        />
                    </PanelSectionRow>
                );
            })}

            {shaderParameters.length > 0 && (
                <PanelSectionRow>
                    <ButtonItem
                        disabled={resetDisabled}
                        onClick={async () => {
                            clearParameterTimeout();
                            setResetDisabled(true);
                            const shaderName = String(selectedShader.data);
                            try {
                                await serverAPI.callPluginMethod("reset_shader_parameters", {
                                    shader_name: shaderName
                                });
                                await loadShaderParameters(shaderName);
                                const eff = await serverAPI.callPluginMethod("get_current_effect", {});
                                setCurrentEffect((eff.result as { effect: string }).effect || "");
                            } catch (error) {
                                console.error(error);
                            } finally {
                                setResetDisabled(false);
                            }
                        }}
                    >Reset Defaults</ButtonItem>
                </PanelSectionRow>
            )}

            <PanelSectionRow>
                <div>Place any custom shaders in <pre>~/.local/share/gamescope</pre><pre>/reshade/Shaders</pre> so that the .fx files are in the root of the Shaders folder.</div>
            </PanelSectionRow>
            <PanelSectionRow>
                <div>WARNING: Shaders can lead to dropped frames and possibly even severe performance problems.</div>
            </PanelSectionRow>
        </PanelSection>
    );
};

export default definePlugin((serverApi: ServerAPI) => {
    let lastAppId = `${Router.MainRunningApp?.appid || "Unknown"}`;
    const interval = setInterval(() => {
        const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;

        if (appid !== lastAppId) {
            lastAppId = appid;
            // initState() performs the one and only set_current_game_info RPC.
            if (forceRefreshContent) forceRefreshContent();
        }
    }, 5000);

    return {
        title: <div className={staticClasses.Title}>Reshadeck</div>,
        content: <Content serverAPI={serverApi} />,
        icon: <MdWbShade />,
        onDismount() {
            clearInterval(interval);
        },
        alwaysRender: true
    };
});
