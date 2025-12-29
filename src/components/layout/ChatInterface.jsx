import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Send, Paperclip, Mic, User, Phone, PhoneOff, Volume2, Eye } from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { sendMessage, getMessages } from "@/lib/api";

export function ChatInterface({ sessionId = "1", sessionName = "Alan Turing" }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [mode, setMode] = useState("text");
    const [isCallActive, setIsCallActive] = useState(false);
    const [callDuration, setCallDuration] = useState(0);
    const [isLoading, setIsLoading] = useState(false);
    const [isListening, setIsListening] = useState(false);
    const scrollRef = useRef(null);
    const fileInputRef = useRef(null);

    // Fetch messages on mount or session change
    useEffect(() => {
        async function fetchMessages() {
            try {
                const data = await getMessages(sessionId);
                setMessages(data.messages || []);
            } catch (error) {
                console.error("Failed to fetch messages:", error);
                // Fallback to default message
                setMessages([{
                    id: 1,
                    role: "assistant",
                    content: `Hello. I am initialized with the cognitive patterns of ${sessionName}. How may I assist in your computations today?`,
                    timestamp: "10:23 AM"
                }]);
            }
        }
        fetchMessages();
    }, [sessionId, sessionName]);

    const handleSend = async () => {
        if (!input.trim() || isLoading) return;

        const userContent = input;
        setInput("");
        setIsLoading(true);

        // Optimistic update - add user message immediately
        const tempUserMsg = {
            id: `temp-${Date.now()}`,
            role: "user",
            content: userContent,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        setMessages(prev => [...prev, tempUserMsg]);

        try {
            const response = await sendMessage(userContent, sessionId);
            // Replace temp message with real ones
            setMessages(prev => {
                const filtered = prev.filter(m => m.id !== tempUserMsg.id);
                return [...filtered, response.user_message, response.ai_message];
            });
        } catch (error) {
            console.error("Failed to send message:", error);
            // Keep the temp message but show error
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

    const handleFileSelect = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        // Add a message about the attached file
        setMessages(prev => [...prev, {
            id: Date.now(),
            role: "user",
            content: `📎 Attached: ${file.name}`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }]);

        // Reset input
        e.target.value = '';
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

    return (
        <div className="flex-1 flex flex-col h-full bg-background relative overflow-hidden">
            {/* Hidden file input */}
            <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileSelect}
                className="hidden"
                accept=".txt,.pdf,.json,.doc,.docx"
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

                {/* Mode Toggle */}
                <div className="flex items-center gap-1 sm:gap-2 bg-white/5 border border-white/10 rounded-full p-1 flex-shrink-0">
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

            {/* Content Area */}
            <AnimatePresence mode="wait">
                {mode === "text" ? (
                    <motion.div
                        key="text-mode"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="flex-1 flex flex-col"
                    >
                        {/* Chat Area */}
                        <ScrollArea className="flex-1 px-3 sm:px-6 py-4 sm:py-6" ref={scrollRef}>
                            <div className="space-y-4 sm:space-y-6 max-w-2xl sm:max-w-3xl mx-auto">
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
                                            "p-3 sm:p-4 rounded-lg sm:rounded-2xl text-xs sm:text-sm leading-relaxed",
                                            msg.role === "assistant"
                                                ? "bg-white/5 border border-white/5 text-gray-200 rounded-tl-none"
                                                : "bg-primary text-white shadow-lg shadow-primary/20 rounded-tr-none"
                                        )}>
                                            {msg.content}
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
                                <div className="relative bg-sidebar border border-white/10 rounded-lg sm:rounded-2xl p-1.5 sm:p-2 flex items-center gap-1 sm:gap-2 shadow-2xl">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 sm:h-10 sm:w-10 text-muted-foreground hover:text-white shrink-0 text-xs sm:text-base"
                                        onClick={handleAttachment}
                                    >
                                        <Paperclip size={16} className="sm:size-[20px]" />
                                    </Button>

                                    <Input
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyDown={(e) => e.key === "Enter" && handleSend()}
                                        placeholder="Message..."
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
                                        disabled={isLoading || !input.trim()}
                                    >
                                        <Send size={14} className="sm:size-[18px]" />
                                    </Button>
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
                                        <span className="text-primary font-mono font-medium">{formatDuration(callDuration)}</span>
                                    ) : (
                                        "Ready for call"
                                    )}
                                </p>
                            </motion.div>

                            {/* Call Controls */}
                            <motion.div
                                initial={{ y: 20, opacity: 0 }}
                                animate={{ y: 0, opacity: 1 }}
                                transition={{ delay: 0.4 }}
                                className="flex items-center gap-3 sm:gap-6 mt-4 sm:mt-8"
                            >
                                <Button
                                    size="lg"
                                    className="h-10 w-10 sm:h-14 sm:w-14 rounded-full bg-white/10 hover:bg-white/20 border border-white/20 text-white p-0"
                                    title="Toggle Audio"
                                >
                                    <Volume2 size={18} className="sm:size-[24px]" />
                                </Button>

                                <Button
                                    size="lg"
                                    className="h-10 w-10 sm:h-14 sm:w-14 rounded-full bg-white/10 hover:bg-white/20 border border-white/20 text-white p-0"
                                    title="Toggle Video"
                                >
                                    <Eye size={18} className="sm:size-[24px]" />
                                </Button>

                                <Button
                                    onClick={() => setIsCallActive(!isCallActive)}
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
