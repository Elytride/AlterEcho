import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { getSettings, updateSettings } from "@/lib/api";
import { Loader2 } from "lucide-react";

export function SettingsModal({ open, onOpenChange }) {
    const [settings, setSettings] = useState({
        model_version: "v2.4",
        temperature: 0.7,
        api_key: "sk-........................"
    });
    const [isSaving, setIsSaving] = useState(false);
    const [isLoading, setIsLoading] = useState(true);

    // Fetch settings when modal opens
    useEffect(() => {
        if (open) {
            async function fetchSettings() {
                setIsLoading(true);
                try {
                    const data = await getSettings();
                    setSettings(data);
                } catch (error) {
                    console.error("Failed to fetch settings:", error);
                } finally {
                    setIsLoading(false);
                }
            }
            fetchSettings();
        }
    }, [open]);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            await updateSettings(settings);
            onOpenChange(false);
        } catch (error) {
            console.error("Failed to save settings:", error);
            alert("Failed to save settings. Please try again.");
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px] bg-sidebar border-white/10 text-white">
                <DialogHeader>
                    <DialogTitle className="font-display tracking-tight">System Settings</DialogTitle>
                </DialogHeader>

                {isLoading ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    </div>
                ) : (
                    <div className="grid gap-6 py-4">
                        <div className="space-y-4">
                            <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Appearance</h4>
                            <div className="flex items-center justify-between">
                                <Label htmlFor="theme" className="flex flex-col gap-1">
                                    <span>Dark Mode</span>
                                    <span className="font-normal text-xs text-muted-foreground">Always active in Nulltale</span>
                                </Label>
                                <Switch id="theme" checked disabled />
                            </div>
                        </div>

                        <div className="space-y-4">
                            <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">AI Configuration</h4>

                            <div className="grid gap-2">
                                <Label>Model Version</Label>
                                <Select
                                    value={settings.model_version}
                                    onValueChange={(value) => setSettings(prev => ({ ...prev, model_version: value }))}
                                >
                                    <SelectTrigger className="bg-white/5 border-white/10">
                                        <SelectValue placeholder="Select model" />
                                    </SelectTrigger>
                                    <SelectContent className="bg-sidebar border-white/10 text-white">
                                        <SelectItem value="v2.4">Nulltale v2.4 (Stable)</SelectItem>
                                        <SelectItem value="v3.0">Nulltale v3.0 (Beta)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="grid gap-4">
                                <div className="flex items-center justify-between">
                                    <Label>Creativity Temperature</Label>
                                    <span className="text-xs text-muted-foreground">{settings.temperature.toFixed(1)}</span>
                                </div>
                                <Slider
                                    value={[settings.temperature]}
                                    onValueChange={([value]) => setSettings(prev => ({ ...prev, temperature: value }))}
                                    max={1}
                                    step={0.1}
                                    className="[&>span:first-child]:bg-primary"
                                />
                            </div>
                        </div>

                        <div className="space-y-4">
                            <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">API Keys</h4>
                            <div className="grid gap-2">
                                <Label>OpenAI API Key</Label>
                                <Input
                                    type="password"
                                    value={settings.api_key}
                                    onChange={(e) => setSettings(prev => ({ ...prev, api_key: e.target.value }))}
                                    className="bg-white/5 border-white/10 font-mono"
                                />
                            </div>
                        </div>
                    </div>
                )}

                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button
                        onClick={handleSave}
                        className="bg-primary text-white hover:bg-primary/90"
                        disabled={isSaving || isLoading}
                    >
                        {isSaving ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Saving...
                            </>
                        ) : (
                            "Save Settings"
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
