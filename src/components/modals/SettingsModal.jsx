import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    getSettings, updateSettings,
    getWaveSpeedKeyStatus, saveWaveSpeedKey, deleteWaveSpeedKey,
    getGeminiKeyStatus, saveGeminiKey, deleteGeminiKey
} from "@/lib/api";
import { Loader2, Check, X, Eye, EyeOff, KeyRound, Trash2, Info, AlertTriangle, Cpu, Brain, Database, Shield } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export function SettingsModal({ open, onOpenChange }) {
    // General Settings
    const [settings, setSettings] = useState({
        chatbot_model: "gemini-flash-latest",
        training_model: "gemini-3-flash-preview",
        embedding_model: "gemini-embedding-001"
    });
    const [isSaving, setIsSaving] = useState(false);
    const [isLoading, setIsLoading] = useState(true);

    // API Key States
    const [geminiKey, setGeminiKey] = useState("");
    const [geminiKeyConfigured, setGeminiKeyConfigured] = useState(false);
    const [showGeminiKey, setShowGeminiKey] = useState(false);
    const [isSavingGeminiKey, setIsSavingGeminiKey] = useState(false);
    const [geminiKeyStatus, setGeminiKeyStatus] = useState(null);

    const [wavespeedKey, setWavespeedKey] = useState("");
    const [wavespeedKeyConfigured, setWavespeedKeyConfigured] = useState(false);
    const [showWavespeedKey, setShowWavespeedKey] = useState(false);
    const [isSavingWavespeedKey, setIsSavingWavespeedKey] = useState(false);
    const [wavespeedKeyStatus, setWavespeedKeyStatus] = useState(null);

    // Fetch settings when modal opens
    useEffect(() => {
        if (open) {
            async function fetchAllSettings() {
                setIsLoading(true);
                try {
                    // Fetch main settings
                    const data = await getSettings();
                    setSettings(data);

                    // Fetch Key Statuses
                    const gStatus = await getGeminiKeyStatus();
                    setGeminiKeyConfigured(gStatus.configured);
                    setGeminiKey("");

                    const wStatus = await getWaveSpeedKeyStatus();
                    setWavespeedKeyConfigured(wStatus.configured);
                    setWavespeedKey("");
                } catch (error) {
                    console.error("Failed to fetch settings:", error);
                } finally {
                    setIsLoading(false);
                }
            }
            fetchAllSettings();
        }
    }, [open]);

    // Handle Main Settings Save
    const handleSaveSettings = async () => {
        setIsSaving(true);
        try {
            await updateSettings(settings);
            onOpenChange(false);
        } catch (error) {
            console.error("Failed to save settings:", error);
            alert("Failed to save settings.");
        } finally {
            setIsSaving(false);
        }
    };

    const handleResetDefaults = async () => {
        if (!confirm("Reset all model preferences to default? API keys will NOT be removed.")) return;
        const defaults = {
            chatbot_model: "gemini-flash-latest",
            training_model: "gemini-3-flash-preview",
            embedding_model: "gemini-embedding-001"
        };
        setSettings(defaults);
    };

    // --- Gemini Key Handlers ---
    const handleSaveGeminiKey = async () => {
        if (!geminiKey.trim()) return;
        setIsSavingGeminiKey(true);
        setGeminiKeyStatus(null);
        try {
            await saveGeminiKey(geminiKey);
            setGeminiKeyConfigured(true);
            setGeminiKey("");
            setGeminiKeyStatus('success');
            setTimeout(() => setGeminiKeyStatus(null), 3000);
        } catch (error) {
            console.error(error);
            setGeminiKeyStatus('error');
        } finally {
            setIsSavingGeminiKey(false);
        }
    };

    const handleDeleteGeminiKey = async () => {
        if (!confirm("Remove Gemini API Key? The app will stop working.")) return;
        try {
            await deleteGeminiKey();
            setGeminiKeyConfigured(false);
            setGeminiKey("");
        } catch (error) { console.error(error); }
    };

    // --- WaveSpeed Key Handlers ---
    const handleSaveWavespeedKey = async () => {
        if (!wavespeedKey.trim()) return;
        setIsSavingWavespeedKey(true);
        setWavespeedKeyStatus(null);
        try {
            await saveWaveSpeedKey(wavespeedKey);
            setWavespeedKeyConfigured(true);
            setWavespeedKey("");
            setWavespeedKeyStatus('success');
            setTimeout(() => setWavespeedKeyStatus(null), 3000);
        } catch (error) {
            console.error(error);
            setWavespeedKeyStatus('error');
        } finally {
            setIsSavingWavespeedKey(false);
        }
    };

    const handleDeleteWavespeedKey = async () => {
        if (!confirm("Remove WaveSpeed Key? Voice features will be disabled.")) return;
        try {
            await deleteWaveSpeedKey();
            setWavespeedKeyConfigured(false);
            setWavespeedKey("");
        } catch (error) { console.error(error); }
    };


    // Shared Components
    const ApiKeyInput = ({
        label, configured, value, onChange, show, onToggleShow,
        onSave, onDelete, isSaving, status, optional
    }) => (
        <div className="space-y-2">
            <div className="flex items-center justify-between">
                <Label className="flex items-center gap-2">
                    {label}
                    {optional && <span className="text-[10px] bg-white/10 px-1.5 py-0.5 rounded text-muted-foreground">Optional</span>}
                </Label>
                {configured && (
                    <span className="flex items-center gap-1 text-xs text-green-400">
                        <Check className="w-3 h-3" />
                        Configured
                    </span>
                )}
            </div>
            <div className="flex gap-2">
                <div className="relative flex-1">
                    <Input
                        type={show ? "text" : "password"}
                        value={value}
                        onChange={(e) => onChange(e.target.value)}
                        placeholder={configured ? "Key stored securely. Enter new to update..." : "Enter API Key..."}
                        className="bg-white/5 border-white/10 font-mono pr-10"
                    />
                    <button
                        type="button"
                        onClick={onToggleShow}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-white transition-colors"
                    >
                        {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                </div>
                <Button
                    size="icon"
                    onClick={onSave}
                    disabled={!value.trim() || isSaving}
                    className="bg-primary hover:bg-primary/90 shrink-0"
                >
                    {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> :
                        status === 'success' ? <Check className="w-4 h-4" /> :
                            status === 'error' ? <X className="w-4 h-4" /> :
                                <Check className="w-4 h-4" />}
                </Button>
                {configured && (
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={onDelete}
                        className="text-red-400 hover:text-red-300 hover:bg-red-400/10 shrink-0"
                    >
                        <Trash2 className="w-4 h-4" />
                    </Button>
                )}
            </div>
        </div>
    );

    const ModelSelect = ({ label, icon: Icon, value, options, onChange, tooltip }) => (
        <div className="grid gap-2">
            <div className="flex items-center gap-2">
                <Icon className="w-4 h-4 text-muted-foreground" />
                <Label>{label}</Label>
                <TooltipProvider delayDuration={0}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Info className="w-3 h-3 text-muted-foreground hover:text-white cursor-pointer" />
                        </TooltipTrigger>
                        <TooltipContent side="right" className="bg-black border-white/20 text-xs">
                            <p className="max-w-[200px]">{tooltip}</p>
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </div>
            <Select value={value} onValueChange={onChange}>
                <SelectTrigger className="bg-white/5 border-white/10">
                    <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-sidebar border-white/10 text-white">
                    {options.map(opt => (
                        <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    );

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px] max-h-[85vh] overflow-y-auto bg-sidebar border-white/10 text-white scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                <DialogHeader>
                    <DialogTitle className="font-display tracking-tight flex items-center gap-2">
                        <Shield className="w-5 h-5 text-primary" />
                        System Settings
                    </DialogTitle>
                </DialogHeader>

                {isLoading ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    </div>
                ) : (
                    <div className="grid gap-8 py-4">
                        {/* API Keys Section */}
                        <div className="space-y-4">
                            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                <KeyRound className="w-3 h-3" /> API Configuration
                            </h4>

                            <ApiKeyInput
                                label="Gemini API Key"
                                configured={geminiKeyConfigured}
                                value={geminiKey}
                                onChange={setGeminiKey}
                                show={showGeminiKey}
                                onToggleShow={() => setShowGeminiKey(!showGeminiKey)}
                                onSave={handleSaveGeminiKey}
                                onDelete={handleDeleteGeminiKey}
                                isSaving={isSavingGeminiKey}
                                status={geminiKeyStatus}
                            />

                            <ApiKeyInput
                                label="WaveSpeed API Key"
                                optional
                                configured={wavespeedKeyConfigured}
                                value={wavespeedKey}
                                onChange={setWavespeedKey}
                                show={showWavespeedKey}
                                onToggleShow={() => setShowWavespeedKey(!showWavespeedKey)}
                                onSave={handleSaveWavespeedKey}
                                onDelete={handleDeleteWavespeedKey}
                                isSaving={isSavingWavespeedKey}
                                status={wavespeedKeyStatus}
                            />
                        </div>

                        {/* Models Section */}
                        <div className="space-y-4">
                            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                <Brain className="w-3 h-3" /> Model Selection
                            </h4>

                            <ModelSelect
                                label="Chatbot Model"
                                icon={Cpu}
                                value={settings.chatbot_model}
                                options={["gemini-flash-latest", "gemini-3-flash-preview", "gemini-flash-lite-latest"]}
                                onChange={(v) => setSettings(prev => ({ ...prev, chatbot_model: v }))}
                                tooltip="The model used for generating real-time chat responses and voice synthesis text."
                            />

                            <ModelSelect
                                label="Persona Training Model"
                                icon={Brain}
                                value={settings.training_model}
                                options={["gemini-3-flash-preview", "gemini-3-pro-preview", "gemini-2.5-pro", "gemini-flash-latest"]}
                                onChange={(v) => setSettings(prev => ({ ...prev, training_model: v }))}
                                tooltip="The model used to analyze huge volumes of chat logs to learn the persona's style. 'Pro' models are better but slower."
                            />

                            <ModelSelect
                                label="Memory Embedding Model"
                                icon={Database}
                                value={settings.embedding_model}
                                options={["gemini-embedding-001"]}
                                onChange={(v) => setSettings(prev => ({ ...prev, embedding_model: v }))}
                                tooltip="The model used to convert text into vector content for memory retrieval. Changing this requires re-processing memories."
                            />

                            <ModelSelect
                                label="Image Generation Model"
                                icon={Eye}
                                value={settings.image_model || "gemini-2.5-flash-image"}
                                options={["gemini-2.5-flash-image", "gemini-3-pro-image-preview"]}
                                onChange={(v) => setSettings(prev => ({ ...prev, image_model: v }))}
                                tooltip="The model used by the persona to generate images during chat."
                            />
                        </div>

                        {/* General / Danger Zone */}
                        <div className="pt-4 border-t border-white/5 flex items-center justify-between">
                            <Button
                                variant="ghost"
                                size="sm"
                                className="text-yellow-500 hover:text-yellow-400 hover:bg-yellow-500/10 h-8 text-xs"
                                onClick={handleResetDefaults}
                            >
                                <AlertTriangle className="w-3 h-3 mr-1.5" />
                                Reset Defaults
                            </Button>
                        </div>
                    </div>
                )}

                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button
                        onClick={handleSaveSettings}
                        className="bg-primary text-white hover:bg-primary/90"
                        disabled={isSaving || isLoading}
                    >
                        {isSaving ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Saving...
                            </>
                        ) : (
                            "Save Changes"
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
