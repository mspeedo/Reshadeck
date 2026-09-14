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

class ReshadeckLogic {
    serverAPI: ServerAPI;
    dataTakenAt: number = Date.now();

    constructor(serverAPI: ServerAPI) {
        this.serverAPI = serverAPI;
    }

    handleSuspend = async () => {
        // Do nothing or log if you want
    };

    handleResume = async () => {
//      await this.serverAPI.callPluginMethod("apply_shader", {});
    };
}

const Content: VFC<{ serverAPI: ServerAPI }> = ({ serverAPI }) => {
    const baseShader = { data: "None", label: "No Shader" } as SingleDropdownOption;
    const [shadersEnabled, setShadersEnabled] = useState<boolean>(false);
    const [shader_list, set_shader_list] = useState<string[]>([]);
    const [selectedShader, setSelectedShader] = useState<DropdownOption>(baseShader);
    const [shaderOptions, setShaderOptions] = useState<DropdownOption[]>([baseShader]);
    const [currentGameId, setCurrentGameId] = useState<string>("Unknown");
    const [currentGameName, setCurrentGameName] = useState<string>("Unknown");
    const [currentEffect, setCurrentEffect] = useState<string>("");
    const [shaderParameters, setShaderParameters] = useState<ShaderParameter[]>([]);
    const parameterTimeouts = useRef<Record<string, number>>({});
    const [applyDisabled, setApplyDisabled] = useState(false);

    const [refreshVersion, setRefreshVersion] = useState(0);
    forceRefreshContent = () => setRefreshVersion(v => v + 1);

    const getShaderOptions = (le_list: string[], baseShaderOrSS: any) => {
        let options: DropdownOption[] = [];
        options.push(baseShaderOrSS);
        for (let i = 0; i < le_list.length; i++) {
            let option = { data: le_list[i], label: le_list[i] } as SingleDropdownOption;
            options.push(option);
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
        await refreshCurrentGameInfo();

        let shaderList = (await serverAPI.callPluginMethod("get_shader_list", {})).result as string[];
        set_shader_list(shaderList);
        setShaderOptions(getShaderOptions(shaderList, baseShader));

        let enabledResp = await serverAPI.callPluginMethod("get_shader_enabled", {});
        let isEnabled: boolean = enabledResp.result === true || enabledResp.result === "true";
        setShadersEnabled(isEnabled);

        let curr = await serverAPI.callPluginMethod("get_current_shader", {});
        const currentShader = String(curr.result || "None");
        setSelectedShader({ data: currentShader, label: (currentShader === "0" ? "None" : currentShader) } as SingleDropdownOption);
        await loadShaderParameters(currentShader);

        let eff = await serverAPI.callPluginMethod("get_current_effect", {});
        setCurrentEffect((eff.result as { effect: string }).effect || "");
    };

    useEffect(() => {
        initState();
    }, [refreshVersion]);

    useEffect(() => {
        return () => {
            Object.values(parameterTimeouts.current).forEach(timeout => clearTimeout(timeout));
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
                        let eff = await serverAPI.callPluginMethod("get_current_effect", {});
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
                        setSelectedShader(newSelectedShader);
                        const shaderName = String(newSelectedShader.data);
                        await serverAPI.callPluginMethod("set_shader", { shader_name: shaderName });
                        await loadShaderParameters(shaderName);
                        let eff = await serverAPI.callPluginMethod("get_current_effect", {});
                        setCurrentEffect((eff.result as { effect: string }).effect || "");
                    }}
                />
            </PanelSectionRow>
            <PanelSectionRow>
                <ButtonItem
                    disabled={applyDisabled}
                    onClick={async () => {
                        setApplyDisabled(true);
                        setTimeout(() => setApplyDisabled(false), 1000);
                        await serverAPI.callPluginMethod("apply_shader", {});
                        let eff = await serverAPI.callPluginMethod("get_current_effect", {});
                        setCurrentEffect((eff.result as { effect: string }).effect || "");
                    }}
                >Apply Shader</ButtonItem>
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

                                const timeoutKey = `${String(selectedShader.data)}:${parameter.name}`;
                                if (parameterTimeouts.current[timeoutKey]) {
                                    clearTimeout(parameterTimeouts.current[timeoutKey]);
                                }
                                parameterTimeouts.current[timeoutKey] = window.setTimeout(() => {
                                    serverAPI.callPluginMethod("set_shader_parameter", {
                                        shader_name: String(selectedShader.data),
                                        parameter_name: parameter.name,
                                        value: realValue
                                    }).catch(console.error);
                                }, 350);
                            }}
                        />
                    </PanelSectionRow>
                );
            })}

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
    let logic = new ReshadeckLogic(serverApi);
//  let suspend_registers = [
//      window.SteamClient.System.RegisterForOnSuspendRequest(logic.handleSuspend),
//      window.SteamClient.System.RegisterForOnResumeFromSuspend(logic.handleResume),
//  ];

    let lastAppId = `${Router.MainRunningApp?.appid || "Unknown"}`;
    const interval = setInterval(async () => {
        const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
        const appname = `${Router.MainRunningApp?.display_name || "Unknown"}`;

        if (appid !== lastAppId) {
            lastAppId = appid;
            await serverApi.callPluginMethod("set_current_game_info", {
                appid,
                appname,
            });
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
