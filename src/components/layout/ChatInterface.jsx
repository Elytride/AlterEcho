import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Send, Paperclip, Mic, User, Phone, PhoneOff, Volume2, Eye, Trash2, Image as ImageIcon, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { sendMessage, getMessages, streamVoiceCall, warmupModels, clearChatHistory } from "@/lib/api";

export function ChatInterface({ sessionId = "1", sessionName = "Alan Turing" }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [attachment, setAttachment] = useState(null); // New attachment state
    const [mode, setMode] = useState("text");
    const [isCallActive, setIsCallActive] = useState(false);
    const [callDuration, setCallDuration] = useState(0);
    const [isLoading, setIsLoading] = useState(false);
    const [isListening, setIsListening] = useState(false);
    const [isDragging, setIsDragging] = useState(false); // Drag state
    const scrollRef = useRef(null);
    const fileInputRef = useRef(null);
    const audioContextRef = useRef(null);
    const audioQueueRef = useRef([]);
    const isPlayingRef = useRef(false);

    // Fetch messages on mount or session change
    useEffect(() => {
        async function fetchMessages() {
            try {
                const data = await getMessages(sessionId);
                setMessages(data.messages || []);
            } catch (error) {
                console.error("Failed to fetch messages:", error);
                // Start with empty messages
                setMessages([]);
            }
        }
        fetchMessages();
    }, [sessionId, sessionName]);

    const handleClearChat = async () => {
        if (!confirm("Are you sure you want to clear the current chat history? This cannot be undone.")) return;

        try {
            await clearChatHistory(sessionId);
            setMessages([]);
        } catch (error) {
            console.error("Failed to clear chat:", error);
            alert("Failed to clear chat history");
        }
    };

    const handleSend = async () => {
        if ((!input.trim() && !attachment) || isLoading) return;

        const userContent = input;
        const currentAttachment = attachment;

        setInput("");
        setAttachment(null);
        setIsLoading(true);

        const tempId = `temp-${Date.now()}`;

        // Convert attachment to URL for optimistic preview
        let optimisticImages = [];
        if (currentAttachment) {
            optimisticImages = [URL.createObjectURL(currentAttachment)];
        }

        // Optimistic update
        const tempUserMsg = {
            id: tempId,
            role: "user",
            content: userContent,
            images: optimisticImages,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        setMessages(prev => [...prev, tempUserMsg]);

        try {
            // Pass attachment to sendMessage
            const response = await sendMessage(userContent, sessionId, currentAttachment);

            // Replace temp message with real ones
            setMessages(prev => {
                const filtered = prev.filter(m => m.id !== tempId);
                // Use ai_messages array if available, otherwise use single ai_message
                const aiMessages = response.ai_messages || [response.ai_message];
                return [...filtered, response.user_message, ...aiMessages];
            });
        } catch (error) {
            console.error("Failed to send message:", error);
            setMessages(prev => [...prev, {
                id: Date.now() + 1,
                role: "assistant",
                content: "I apologize, but I'm having trouble processing your request. Please try again.",
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleAttachment = () => {
        fileInputRef.current?.click();
    };

    const handleFileSelect = (e) => {
        const file = e.target.files?.[0];
        if (file) {
            setAttachment(file);
        }
        // Format input value so changes trigger even if same file
        e.target.value = '';
    };

    // Drag and Drop Handlers
    const onDragOver = (e) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const onDragLeave = (e) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const onDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        const files = e.dataTransfer.files;
        if (files && files[0]) {
            if (files[0].type.startsWith("image/")) {
                setAttachment(files[0]);
            } else {
                alert("Only images are supported for direct chat attachment currently.");
            }
        }
    };

    // Paste Handler
    const handlePaste = (e) => {
        const items = e.clipboardData.items;
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf("image") !== -1) {
                const blob = items[i].getAsFile();
                setAttachment(blob);
                e.preventDefault(); // Prevent standard paste if it was an image
                break;
            }
        }
    };

    const handleMicClick = () => {
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            alert("Speech recognition is not supported in this browser.");
            return;
        }

        if (isListening) {
            setIsListening(false);
            return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onstart = () => setIsListening(true);
        recognition.onend = () => setIsListening(false);
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            setInput(prev => prev + transcript);
        };
        recognition.onerror = () => setIsListening(false);

        recognition.start();
    };

    // Call duration timer
    useEffect(() => {
        let interval;
        if (isCallActive) {
            interval = setInterval(() => {
                setCallDuration(prev => prev + 1);
            }, 1000);
        }
        return () => clearInterval(interval);
    }, [isCallActive]);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
        }
    }, [messages]);

    const formatDuration = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    // Voice Call State
    const [callStatus, setCallStatus] = useState("idle"); // idle, listening, processing, speaking
    const [aiResponse, setAiResponse] = useState("");
    const recognitionRef = useRef(null);
    const isCallActiveRef = useRef(false); // Ref to avoid stale closure
    const callStatusRef = useRef("idle"); // Ref to avoid stale closure for callStatus
    const onAudioFinishedRef = useRef(null); // Callback when all audio done
    const pendingDecodesRef = useRef(0); // Track active decodes

    // Helper to update callStatus (both state and ref)
    const updateCallStatus = (status) => {
        setCallStatus(status);
        callStatusRef.current = status;
    };

    // Initialize Web Audio for playback
    const initAudioContext = () => {
        if (!audioContextRef.current) {
            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
        }
        return audioContextRef.current;
    };

    // Play audio from base64 WAV data
    const playAudioChunk = async (base64Audio) => {
        pendingDecodesRef.current += 1;
        try {
            const audioContext = initAudioContext();
            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Decode audio data
            const audioBuffer = await audioContext.decodeAudioData(bytes.buffer);

            // Queue for sequential playback
            audioQueueRef.current.push(audioBuffer);
        } catch (e) {
            console.error("Audio decode error:", e);
        } finally {
            pendingDecodesRef.current -= 1;
            // Try to play next
            playNextInQueue();
        }
    };

    // Play audio chunks sequentially
    const playNextInQueue = () => {
        if (isPlayingRef.current) return;

        if (audioQueueRef.current.length === 0) {
            // Only finish if no chunks are being decoded
            if (pendingDecodesRef.current === 0 && onAudioFinishedRef.current) {
                const callback = onAudioFinishedRef.current;
                onAudioFinishedRef.current = null;
                callback();
            }
            return;
        }

        isPlayingRef.current = true;
        const audioBuffer = audioQueueRef.current.shift();
        const audioContext = audioContextRef.current;

        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.onended = () => {
            isPlayingRef.current = false;
            playNextInQueue();
        };
        source.start(0);
    };

    // Handle voice call start/stop
    const handleCallToggle = async () => {
        if (isCallActive) {
            // End call
            setIsCallActive(false);
            isCallActiveRef.current = false;
            setCallDuration(0);
            updateCallStatus("idle");
            setAiResponse("");
            if (recognitionRef.current) {
                recognitionRef.current.stop();
            }
            audioQueueRef.current = [];
            onAudioFinishedRef.current = null;
        } else {
            // Start call - warmup models in background
            warmupModels(); // Fire and forget - preload Gemini + XTTS
            setIsCallActive(true);
            isCallActiveRef.current = true;
            updateCallStatus("listening");
            setAiResponse("");
            startListening();
        }
    };

    // Start speech recognition
    const startListening = () => {
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            alert("Speech recognition is not supported in this browser.");
            setCallStatus("idle");
            return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SpeechRecognition();
        recognitionRef.current = recognition;

        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        recognition.onstart = () => {
            updateCallStatus("listening");
        };

        recognition.onresult = async (event) => {
            const transcript = event.results[0][0].transcript;
            console.log("User said:", transcript);
            updateCallStatus("processing");

            // Stream voice response
            await handleVoiceResponse(transcript);
        };

        recognition.onerror = (event) => {
            console.error("Speech recognition error:", event.error);
            if (isCallActiveRef.current && event.error !== 'aborted') {
                // Restart listening on error
                setTimeout(() => startListening(), 500);
            }
        };

        recognition.onend = () => {
            // Restart if call is still active and we're not processing
            console.log("Recognition ended, callStatus:", callStatusRef.current);
            if (isCallActiveRef.current && callStatusRef.current === "listening") {
                setTimeout(() => startListening(), 100);
            }
        };

        recognition.start();
    };

    // Handle streaming voice response
    const handleVoiceResponse = async (userMessage) => {
        setAiResponse("");
        audioQueueRef.current = [];

        await streamVoiceCall(userMessage, sessionId, {
            onText: (text) => {
                setAiResponse(prev => prev + text);
            },
            onAudio: (base64Audio, index) => {
                updateCallStatus("speaking");
                playAudioChunk(base64Audio);
            },
            onStatus: (status) => {
                console.log("Call status:", status);
            },
            onDone: (fullText) => {
                console.log("Response complete:", fullText);
                // Set callback to resume listening after all audio finishes
                onAudioFinishedRef.current = () => {
                    if (isCallActiveRef.current) {
                        console.log("Audio finished, resuming listening...");
                        updateCallStatus("listening");
                        startListening();
                    }
                };
                // Trigger check in case audio queue is already empty
                setTimeout(() => playNextInQueue(), 100);
            },
            onError: (error) => {
                console.error("Voice call error:", error);
                updateCallStatus("listening");
                if (isCallActiveRef.current) {
                    startListening();
                }
            }
        });
    };

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (recognitionRef.current) {
                recognitionRef.current.stop();
            }
            if (audioContextRef.current) {
                audioContextRef.current.close();
            }
        };
    }, []);

    return (
        <div
            className="flex-1 flex flex-col h-full bg-background relative overflow-hidden"
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
        >
            {/* Drag Overlay */}
            <AnimatePresence>
                {isDragging && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 z-50 bg-primary/20 backdrop-blur-sm border-2 border-dashed border-primary flex items-center justify-center pointer-events-none"
                    >
                        <div className="flex flex-col items-center text-primary font-display animate-bounce">
                            <ImageIcon size={48} className="mb-4" />
                            <h3 className="text-2xl font-bold">Drop image to attach</h3>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Hidden file input */}
            <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileSelect}
                className="hidden"
                accept="image/*"
            />

            {/* Background Ambience */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_120%,rgba(120,58,237,0.1),transparent_50%)] pointer-events-none" />

            {/* Header */}
            <div className="h-14 sm:h-16 border-b border-white/5 flex items-center justify-between px-3 sm:px-6 bg-background/50 backdrop-blur-sm z-10">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                    <div className={cn(
                        "w-2 h-2 rounded-full shadow-[0_0_8px_rgba(34,197,94,0.5)] animate-pulse flex-shrink-0",
                        isCallActive && mode === "call" ? "bg-red-500" : "bg-green-500"
                    )} />
                    <div className="flex flex-col min-w-0">
                        <span className="font-display font-medium text-white text-sm sm:text-base truncate">{sessionName}</span>
                        <span className="text-[10px] sm:text-xs text-muted-foreground truncate">
                            {isCallActive && mode === "call" ? `Call • ${formatDuration(callDuration)}` : "Online • v2.4"}
                        </span>
                    </div>
                </div>

                {/* Clear Chat & Mode Toggle */}
                <div className="flex items-center gap-2 flex-shrink-0">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleClearChat}
                        title="Clear Chat History"
                        className="h-8 w-8 sm:h-10 sm:w-10 rounded-full bg-white/5 border border-white/10 text-muted-foreground hover:text-red-400 hover:bg-white/10"
                    >
                        <Trash2 size={16} className="sm:size-[18px]" />
                    </Button>

                    <div className="flex items-center gap-1 sm:gap-2 bg-white/5 border border-white/10 rounded-full p-1">
                        <button
                            onClick={() => {
                                setMode("text");
                                setIsCallActive(false);
                                setCallDuration(0);
                            }}
                            className={cn(
                                "px-2 sm:px-4 py-1 rounded-full text-xs sm:text-sm font-medium transition-all duration-200 whitespace-nowrap",
                                mode === "text"
                                    ? "bg-primary text-white shadow-lg shadow-primary/20"
                                    : "text-muted-foreground hover:text-white"
                            )}
                        >
                            Text
                        </button>
                        <button
                            onClick={() => setMode("call")}
                            className={cn(
                                "px-2 sm:px-4 py-1 rounded-full text-xs sm:text-sm font-medium transition-all duration-200 whitespace-nowrap",
                                mode === "call"
                                    ? "bg-primary text-white shadow-lg shadow-primary/20"
                                    : "text-muted-foreground hover:text-white"
                            )}
                        >
                            Call
                        </button>
                    </div>
                </div>
            </div>

            {/* Content Area */}
            <AnimatePresence mode="wait">
                {mode === "text" ? (
                    <motion.div
                        key="text-mode"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="flex-1 flex flex-col min-h-0 overflow-hidden"
                    >
                        {/* Chat Area */}
                        <ScrollArea className="flex-1 px-3 sm:px-6 py-4 sm:py-6 overflow-y-auto" ref={scrollRef}>
                            <div className="space-y-4 sm:space-y-6 max-w-2xl sm:max-w-3xl mx-auto pb-4">
                                {messages.length === 0 && !isLoading && (
                                    <div className="flex flex-col items-center justify-center py-12 text-center">
                                        <div className="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center mb-4">
                                            <CpuIcon size={32} className="text-primary" />
                                        </div>
                                        <h3 className="text-lg font-medium text-white mb-2">Start a conversation</h3>
                                        <p className="text-sm text-muted-foreground max-w-xs">
                                            Type a message below to begin chatting. Drag & drop images to share them with the persona.
                                        </p>
                                    </div>
                                )}
                                {messages.map((msg) => (
                                    <div
                                        key={msg.id}
                                        className={cn(
                                            "flex gap-2 sm:gap-4 max-w-[90%] sm:max-w-[80%]",
                                            msg.role === "user" ? "ml-auto flex-row-reverse" : ""
                                        )}
                                    >
                                        <div className={cn(
                                            "w-6 h-6 sm:w-8 sm:h-8 rounded-full flex items-center justify-center shrink-0 border border-white/10 text-xs sm:text-base",
                                            msg.role === "assistant" ? "bg-primary/20 text-primary" : "bg-white/10 text-white"
                                        )}>
                                            {msg.role === "assistant" ? <CpuIcon size={14} /> : <User size={14} />}
                                        </div>

                                        <div className={cn(
                                            "p-3 sm:p-4 rounded-lg sm:rounded-2xl text-xs sm:text-sm leading-relaxed break-words overflow-hidden",
                                            msg.role === "assistant"
                                                ? "bg-white/5 border border-white/5 text-gray-200 rounded-tl-none"
                                                : "bg-primary text-white shadow-lg shadow-primary/20 rounded-tr-none"
                                        )}>
                                            {/* Render Images if present */}
                                            {msg.images && msg.images.length > 0 && (
                                                <div className="mb-2 space-y-2">
                                                    {msg.images.map((imgSrc, idx) => (
                                                        <img
                                                            key={idx}
                                                            src={imgSrc}
                                                            alt="attached content"
                                                            className="rounded-lg max-w-full max-h-[300px] object-cover border border-white/10"
                                                        />
                                                    ))}
                                                </div>
                                            )}

                                            <span className="whitespace-pre-wrap">{msg.content}</span>
                                            <div className={cn(
                                                "text-[8px] sm:text-[10px] mt-2 opacity-50",
                                                msg.role === "user" ? "text-right" : ""
                                            )}>
                                                {msg.timestamp}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                                {isLoading && (
                                    <div className="flex gap-2 sm:gap-4">
                                        <div className="w-6 h-6 sm:w-8 sm:h-8 rounded-full flex items-center justify-center shrink-0 border border-white/10 bg-primary/20 text-primary">
                                            <CpuIcon size={14} />
                                        </div>
                                        <div className="p-3 sm:p-4 rounded-lg sm:rounded-2xl bg-white/5 border border-white/5 text-gray-200 rounded-tl-none">
                                            <div className="flex gap-1">
                                                <span className="w-2 h-2 bg-primary/50 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                                                <span className="w-2 h-2 bg-primary/50 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                                                <span className="w-2 h-2 bg-primary/50 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </ScrollArea>

                        {/* Input Area */}
                        <div className="p-3 sm:p-6 pb-6 sm:pb-8">
                            <div className="max-w-2xl sm:max-w-3xl mx-auto relative group">
                                <div className="absolute -inset-0.5 bg-gradient-to-r from-primary/20 to-blue-500/20 rounded-lg sm:rounded-2xl blur opacity-20 group-hover:opacity-40 transition duration-500" />
                                <div className="relative bg-sidebar border border-white/10 rounded-lg sm:rounded-2xl shadow-2xl overflow-hidden">

                                    {/* Attachment Preview */}
                                    {attachment && (
                                        <div className="px-4 py-2 bg-white/5 border-b border-white/5 flex items-center justify-between">
                                            <div className="flex items-center gap-2 overflow-hidden">
                                                <ImageIcon size={16} className="text-primary shrink-0" />
                                                <span className="text-xs text-muted-foreground truncate max-w-[200px]">{attachment.name}</span>
                                            </div>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-6 w-6 text-muted-foreground hover:text-white"
                                                onClick={() => setAttachment(null)}
                                            >
                                                <X size={14} />
                                            </Button>
                                        </div>
                                    )}

                                    <div className="p-1.5 sm:p-2 flex items-center gap-1 sm:gap-2">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className={cn(
                                                "h-8 w-8 sm:h-10 sm:w-10 shrink-0 text-xs sm:text-base transition-colors",
                                                attachment ? "text-primary" : "text-muted-foreground hover:text-white"
                                            )}
                                            onClick={handleAttachment}
                                            title="Attach image"
                                        >
                                            <Paperclip size={16} className="sm:size-[20px]" />
                                        </Button>

                                        <Input
                                            value={input}
                                            onChange={(e) => setInput(e.target.value)}
                                            onKeyDown={(e) => e.key === "Enter" && handleSend()}
                                            onPaste={handlePaste}
                                            placeholder="Message... (Paste images supported)"
                                            className="flex-1 bg-transparent border-none focus-visible:ring-0 text-white placeholder:text-muted-foreground/50 h-10 sm:h-12 text-xs sm:text-base"
                                            disabled={isLoading}
                                        />

                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className={cn(
                                                "h-8 w-8 sm:h-10 sm:w-10 shrink-0 text-xs sm:text-base transition-colors",
                                                isListening ? "text-red-500 animate-pulse" : "text-muted-foreground hover:text-white"
                                            )}
                                            onClick={handleMicClick}
                                        >
                                            <Mic size={16} className="sm:size-[20px]" />
                                        </Button>

                                        <Button
                                            onClick={handleSend}
                                            size="icon"
                                            className="bg-primary hover:bg-primary/90 text-white rounded-lg sm:rounded-xl shrink-0 h-8 w-8 sm:h-10 sm:w-10 shadow-[0_0_15px_rgba(124,58,237,0.3)]"
                                            disabled={isLoading || (!input.trim() && !attachment)}
                                        >
                                            <Send size={14} className="sm:size-[18px]" />
                                        </Button>
                                    </div>
                                </div>
                                <div className="text-center mt-2 sm:mt-3 text-[8px] sm:text-xs text-muted-foreground/40 font-mono hidden sm:block">
                                    NULLTALE ENGINE ACTIVE // ENCRYPTION ENABLED
                                </div>
                            </div>
                        </div>
                    </motion.div>
                ) : (
                    <motion.div
                        key="call-mode"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="flex-1 flex flex-col items-center justify-center p-4 sm:p-6 relative"
                    >
                        {/* Call Interface */}
                        <div className="flex flex-col items-center gap-4 sm:gap-8 max-w-sm sm:max-w-md w-full">
                            {/* Avatar */}
                            <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                transition={{ delay: 0.2 }}
                                className="relative"
                            >
                                <div className="w-20 h-20 sm:w-32 sm:h-32 rounded-full bg-gradient-to-br from-primary/30 to-primary/10 border-2 border-primary/50 flex items-center justify-center shadow-2xl shadow-primary/20">
                                    <CpuIcon size={40} className="text-primary sm:size-[64px]" />
                                </div>
                                {isCallActive && (
                                    <>
                                        <motion.div
                                            animate={{ scale: [1, 1.2, 1] }}
                                            transition={{ duration: 2, repeat: Infinity }}
                                            className="absolute inset-0 rounded-full border-2 border-primary/50 opacity-0"
                                        />
                                        <div className="absolute top-0 right-0 w-3 h-3 sm:w-4 sm:h-4 bg-red-500 rounded-full border-2 border-background animate-pulse shadow-lg shadow-red-500/50" />
                                    </>
                                )}
                            </motion.div>

                            {/* Status */}
                            <motion.div
                                initial={{ y: 10, opacity: 0 }}
                                animate={{ y: 0, opacity: 1 }}
                                transition={{ delay: 0.3 }}
                                className="text-center"
                            >
                                <h2 className="text-2xl sm:text-3xl font-display font-bold text-white mb-1 sm:mb-2">{sessionName}</h2>
                                <p className="text-xs sm:text-base text-muted-foreground">
                                    {isCallActive ? (
                                        <span className="text-primary font-mono font-medium">
                                            {callStatus === "listening" && "Listening..."}
                                            {callStatus === "processing" && "Processing..."}
                                            {callStatus === "speaking" && "Speaking..."}
                                            {callStatus === "idle" && formatDuration(callDuration)}
                                        </span>
                                    ) : (
                                        "Ready for call"
                                    )}
                                </p>
                                {aiResponse && isCallActive && (
                                    <p className="text-xs text-muted-foreground mt-2 max-w-xs mx-auto truncate">
                                        "{aiResponse.slice(0, 50)}..."
                                    </p>
                                )}
                            </motion.div>

                            {/* Call Controls */}
                            <motion.div
                                initial={{ y: 20, opacity: 0 }}
                                animate={{ y: 0, opacity: 1 }}
                                transition={{ delay: 0.4 }}
                                className="flex items-center gap-3 sm:gap-6 mt-4 sm:mt-8"
                            >


                                <Button
                                    onClick={handleCallToggle}
                                    size="lg"
                                    className={cn(
                                        "h-12 w-12 sm:h-16 sm:w-16 rounded-full font-medium transition-all duration-300 p-0",
                                        isCallActive
                                            ? "bg-red-500 hover:bg-red-600 shadow-lg shadow-red-500/50 text-white"
                                            : "bg-green-500 hover:bg-green-600 shadow-lg shadow-green-500/50 text-white"
                                    )}
                                >
                                    {isCallActive ? (
                                        <PhoneOff size={22} className="sm:size-[28px]" />
                                    ) : (
                                        <Phone size={22} className="sm:size-[28px]" />
                                    )}
                                </Button>
                            </motion.div>

                            {/* Bottom Info */}
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ delay: 0.5 }}
                                className="text-center mt-6 sm:mt-8 text-[8px] sm:text-xs text-muted-foreground/40 font-mono max-w-xs hidden sm:block"
                            >
                                {isCallActive ? (
                                    "ENCRYPTED P2P CONNECTION // VOICE SYNTHESIS ACTIVE"
                                ) : (
                                    "READY TO CONNECT // PRESS CALL TO BEGIN"
                                )}
                            </motion.div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

function CpuIcon({ size, className }) {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width={size}
            height={size}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={className}
        >
            <rect x="4" y="4" width="16" height="16" rx="2" />
            <rect x="9" y="9" width="6" height="6" />
            <path d="M9 1V4" />
            <path d="M15 1V4" />
            <path d="M9 20V23" />
            <path d="M15 20V23" />
            <path d="M20 9H23" />
            <path d="M20 14H23" />
            <path d="M1 9H4" />
            <path d="M1 14H4" />
        </svg>
    );
}
