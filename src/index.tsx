import {
    ButtonItem,
    definePlugin,
    DialogButton,
    Menu,
    MenuItem,
    PanelSection,
    PanelSectionRow,
    ToggleField,
    Router,
    ServerAPI,
    showContextMenu,
    staticClasses,
    Dropdown,
    DropdownOption,
    SingleDropdownOption,
	SliderField
} from "decky-frontend-lib";
import { VFC, useState, useEffect, useRef  } from "react";
import { MdWbShade } from "react-icons/md";
import logo from "../assets/logo.png";

// Global refresh function reference
let forceRefreshContent: (() => void) | null = null;

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
		await this.serverAPI.callPluginMethod("apply_shader", {});
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
	const [contrast, setContrast] = useState<number>(0.0);
    const [sharpness, setSharpness] = useState<number>(1.0);
	const contrastTimeout = useRef<number | null>(null);
	const sharpnessTimeout = useRef<number | null>(null);
	const [applyDisabled, setApplyDisabled] = useState(false);

    // --- Add refreshVersion state for UI refreshes ---
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
    }
	
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
		
        let shader_list = (await serverAPI.callPluginMethod("get_shader_list", {})).result as string[];
        set_shader_list(shader_list)
        setShaderOptions(getShaderOptions(shader_list, baseShader));
		
        let enabledResp = await serverAPI.callPluginMethod("get_shader_enabled", {});
        let isEnabled: boolean = enabledResp.result === true || enabledResp.result === "true";
        setShadersEnabled(isEnabled);

        let curr = await serverAPI.callPluginMethod("get_current_shader", {});
        setSelectedShader({ data: curr.result, label: (curr.result == "0" ? "None" : curr.result) } as SingleDropdownOption);
		
		let eff = await serverAPI.callPluginMethod("get_current_effect", {});
		setCurrentEffect((eff.result as { effect: string }).effect || "");

		let contrastResp = await serverAPI.callPluginMethod("get_contrast", {});
		let cVal = Number(contrastResp.result);
		if (!isNaN(cVal)) {
			setContrast(parseFloat(cVal.toFixed(6)));
		}
		
		let sharpnessResp = await serverAPI.callPluginMethod("get_sharpness", {});
		let sVal = Number(sharpnessResp.result);
		if (!isNaN(sVal)) {
			setSharpness(parseFloat(sVal.toFixed(6)));
		}
    }

    // --- Init state on mount and on refreshVersion bump ---
    useEffect(() => {
        initState();
    }, [refreshVersion]);
	
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
                        await serverAPI.callPluginMethod("set_shader", { "shader_name": newSelectedShader.data });
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
						setTimeout(() => setApplyDisabled(false), 1000); // 1 second lockout
						await serverAPI.callPluginMethod("apply_shader", {});
						let eff = await serverAPI.callPluginMethod("get_current_effect", {});
						setCurrentEffect((eff.result as { effect: string }).effect || "");
				}}
				>Apply Shader</ButtonItem>
            </PanelSectionRow>
			<PanelSectionRow>
				<b>CAS.fx parameters</b>
			</PanelSectionRow>
            {/* Contrast Slider */}
            <PanelSectionRow>
                <SliderField
                    bottomSeparator="none"
                    label={`Contrast: ${contrast.toFixed(2)}`}
                    min={0}
                    max={20}
					step={1}
                    value={Math.round(contrast * 10)}
					disabled={!(shadersEnabled && selectedShader.data === "CAS.fx")}
                    onChange={async (val: number) => {
                        const real = val / 10;
                        setContrast(real);
						if (contrastTimeout.current) clearTimeout(contrastTimeout.current);
						contrastTimeout.current = window.setTimeout(() => {
							serverAPI.callPluginMethod("set_contrast", { value: real }).catch(console.error);
						}, 1000);
                    }}
                />
            </PanelSectionRow>
            {/* Sharpness Slider */}
            <PanelSectionRow>
                <SliderField
                    bottomSeparator="none"
                    label={`Sharpness: ${sharpness.toFixed(2)}`}
                    min={0}
                    max={20}
					step={1}
                    value={Math.round(sharpness * 10)}
					disabled={!(shadersEnabled && selectedShader.data === "CAS.fx")}
                    onChange={async (val: number) => {
                        const real = val / 10;
                        setSharpness(real);
						if (sharpnessTimeout.current) clearTimeout(sharpnessTimeout.current);
						sharpnessTimeout.current = window.setTimeout(() => {
							serverAPI.callPluginMethod("set_sharpness", { value: real }).catch(console.error);
						}, 1000);
                    }}
                />
            </PanelSectionRow>
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

	let suspend_registers = [
		window.SteamClient.System.RegisterForOnSuspendRequest(logic.handleSuspend),
		window.SteamClient.System.RegisterForOnResumeFromSuspend(logic.handleResume),
	];

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
            // --- Notify UI to refresh if overlay is open ---
            if (forceRefreshContent) forceRefreshContent();
        }
    }, 5000);

    return {
        title: <div className={staticClasses.Title}>Reshadeck</div>,
        content: <Content serverAPI={serverApi} />,
        icon: <MdWbShade />,
        onDismount() {
            suspend_registers[0].unregister();
            suspend_registers[1].unregister();

            clearInterval(interval);
        },
        alwaysRender: true
    };
});

