import { useState, useRef, useCallback } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { FileText, Video, Mic, Upload, RefreshCw, Check, X } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { motion, AnimatePresence } from "framer-motion";
import { uploadFile, refreshAIMemory } from "@/lib/api";
import { cn } from "@/lib/utils";

export function FilesModal({ open, onOpenChange }) {
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [progress, setProgress] = useState(0);
    const [uploadedFiles, setUploadedFiles] = useState({ text: [], video: [], voice: [] });
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState(null);

    const textInputRef = useRef(null);
    const videoInputRef = useRef(null);
    const voiceInputRef = useRef(null);

    const handleRefresh = async () => {
        setIsRefreshing(true);
        setProgress(0);

        // Simulate progress while calling API
        const interval = setInterval(() => {
            setProgress(prev => {
                if (prev >= 90) return prev;
                return prev + 10;
            });
        }, 200);

        try {
            await refreshAIMemory();
            setProgress(100);
            setTimeout(() => setIsRefreshing(false), 1000);
        } catch (error) {
            console.error("Failed to refresh AI memory:", error);
            setIsRefreshing(false);
        } finally {
            clearInterval(interval);
        }
    };

    const handleFileUpload = async (file, fileType) => {
        setUploading(true);
        setUploadError(null);

        try {
            const result = await uploadFile(file, fileType);
            setUploadedFiles(prev => ({
                ...prev,
                [fileType]: [...prev[fileType], { name: file.name, savedAs: result.saved_as }]
            }));
        } catch (error) {
            console.error("Failed to upload file:", error);
            setUploadError(`Failed to upload ${file.name}`);
        } finally {
            setUploading(false);
        }
    };

    const handleFileSelect = (e, fileType) => {
        const file = e.target.files?.[0];
        if (file) {
            handleFileUpload(file, fileType);
        }
        e.target.value = '';
    };

    const handleDrop = useCallback((e, fileType) => {
        e.preventDefault();
        e.stopPropagation();

        const file = e.dataTransfer.files?.[0];
        if (file) {
            handleFileUpload(file, fileType);
        }
    }, []);

    const handleDragOver = (e) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const UploadZone = ({ fileType, icon: Icon, title, accept, inputRef }) => (
        <>
            <input
                type="file"
                ref={inputRef}
                onChange={(e) => handleFileSelect(e, fileType)}
                className="hidden"
                accept={accept}
            />
            <div
                className="border-2 border-dashed border-white/10 rounded-lg p-8 flex flex-col items-center justify-center text-center hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer group"
                onClick={() => inputRef.current?.click()}
                onDrop={(e) => handleDrop(e, fileType)}
                onDragOver={handleDragOver}
            >
                <div className={cn(
                    "w-12 h-12 rounded-full bg-white/5 flex items-center justify-center mb-4 transition-colors",
                    uploading ? "animate-pulse" : "group-hover:bg-primary/20 group-hover:text-primary"
                )}>
                    <Icon size={24} />
                </div>
                <p className="text-sm font-medium">{title}</p>
                <p className="text-xs text-muted-foreground mt-1">
                    {fileType === "text" ? "TXT, PDF, JSON supported" :
                        fileType === "video" ? "MP4, MOV up to 500MB" :
                            "MP3, WAV for voice synthesis"}
                </p>
                {uploading && <p className="text-xs text-primary mt-2">Uploading...</p>}
            </div>

            {/* Uploaded files list */}
            {uploadedFiles[fileType].length > 0 && (
                <div className="mt-4 space-y-2">
                    <Label className="text-xs text-muted-foreground">Uploaded Files</Label>
                    {uploadedFiles[fileType].map((file, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-xs bg-white/5 rounded p-2">
                            <Check size={14} className="text-green-500" />
                            <span className="truncate flex-1">{file.name}</span>
                        </div>
                    ))}
                </div>
            )}
        </>
    );

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[700px] bg-sidebar border-white/10 text-white shadow-2xl">
                <DialogHeader>
                    <DialogTitle className="text-xl font-display tracking-tight">Knowledge Base</DialogTitle>
                    <DialogDescription className="text-muted-foreground">
                        Manage the data sources used to reconstruct the personality.
                    </DialogDescription>
                </DialogHeader>

                {uploadError && (
                    <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                        <X size={16} />
                        {uploadError}
                    </div>
                )}

                <div className="mt-6">
                    <Tabs defaultValue="text" className="w-full">
                        <TabsList className="grid w-full grid-cols-3 bg-white/5 border border-white/5">
                            <TabsTrigger value="text" className="data-[state=active]:bg-primary/20 data-[state=active]:text-primary">
                                <FileText className="w-4 h-4 mr-2" />
                                Text Logs
                            </TabsTrigger>
                            <TabsTrigger value="video" className="data-[state=active]:bg-primary/20 data-[state=active]:text-primary">
                                <Video className="w-4 h-4 mr-2" />
                                Video
                            </TabsTrigger>
                            <TabsTrigger value="voice" className="data-[state=active]:bg-primary/20 data-[state=active]:text-primary">
                                <Mic className="w-4 h-4 mr-2" />
                                Voice
                            </TabsTrigger>
                        </TabsList>

                        <div className="p-6 border border-white/5 border-t-0 rounded-b-lg bg-black/20 min-h-[300px]">
                            <TabsContent value="text" className="space-y-4 mt-0">
                                <UploadZone
                                    fileType="text"
                                    icon={Upload}
                                    title="Drop chat logs or text files here"
                                    accept=".txt,.pdf,.json,.doc,.docx"
                                    inputRef={textInputRef}
                                />

                                <div className="space-y-3 pt-4">
                                    <Label>Additional Context</Label>
                                    <Textarea
                                        placeholder="Enter specific personality traits, key memories, or behavioral quirks here..."
                                        className="bg-white/5 border-white/10 focus-visible:ring-primary min-h-[120px]"
                                    />
                                </div>
                            </TabsContent>

                            <TabsContent value="video" className="mt-0">
                                <UploadZone
                                    fileType="video"
                                    icon={Video}
                                    title="Upload interviews or vlogs"
                                    accept=".mp4,.mov,.avi,.webm"
                                    inputRef={videoInputRef}
                                />
                            </TabsContent>

                            <TabsContent value="voice" className="mt-0">
                                <UploadZone
                                    fileType="voice"
                                    icon={Mic}
                                    title="Upload voice notes or recordings"
                                    accept=".mp3,.wav,.ogg,.m4a"
                                    inputRef={voiceInputRef}
                                />
                            </TabsContent>
                        </div>
                    </Tabs>
                </div>

                <div className="mt-6">
                    <AnimatePresence mode="wait">
                        {isRefreshing ? (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -10 }}
                                className="space-y-2"
                            >
                                <div className="flex justify-between text-xs font-medium text-primary">
                                    <span>Reindexing Neural Patterns...</span>
                                    <span>{progress}%</span>
                                </div>
                                <Progress value={progress} className="h-2 bg-white/10" />
                            </motion.div>
                        ) : (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                            >
                                <Button
                                    onClick={handleRefresh}
                                    className="w-full bg-gradient-to-r from-primary to-blue-600 hover:from-primary/90 hover:to-blue-600/90 text-white shadow-lg shadow-primary/20 h-12 text-md font-medium"
                                >
                                    <RefreshCw className="mr-2 w-5 h-5" />
                                    Refresh AI Memory
                                </Button>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </DialogContent>
        </Dialog>
    );
}
