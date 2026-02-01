import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Plus,
    Settings,
    Database,
    Trash2,
    MoreVertical,
    Cpu,
    HelpCircle,
    ChevronDown,
    AlertTriangle
} from "lucide-react";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { FAQModal } from "@/components/modals/FAQModal";



export function Sidebar({
    sessions,
    currentSession,
    onSessionChange,
    onNewChat,
    onManageSession,
    onDeleteSession,
    onOpenSettings
}) {
    const [faqOpen, setFaqOpen] = useState(false);

    // activeSession is now derived from currentSession prop
    const activeSessionId = currentSession?.id;

    const handleSessionClick = (session) => {
        onSessionChange?.(session);
    };

    return (
        <div className="w-80 h-full bg-sidebar border-r border-white/5 flex flex-col font-sans">
            <div className="p-6">
                <div className="flex items-center gap-2 mb-8">
                    <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center border border-primary/20 text-primary">
                        <Cpu size={18} />
                    </div>
                    <h1 className="text-xl font-display font-bold tracking-tight text-white">Nulltale</h1>
                </div>

                <Button
                    className="w-full justify-start gap-2 bg-white/5 hover:bg-white/10 text-white border-white/5 mb-6"
                    variant="outline"
                    onClick={onNewChat}
                >
                    <Plus size={16} />
                    New Chat
                </Button>

                <div className="text-xs font-medium text-muted-foreground mb-4 uppercase tracking-wider">
                    Memory Banks
                </div>
            </div>

            <ScrollArea className="flex-1 px-4">
                <div className="space-y-2">
                    {!sessions ? (
                        <div className="text-muted-foreground text-sm text-center py-4">Loading...</div>
                    ) : (
                        sessions.map((session) => (
                            <div
                                key={session.id}
                                className={cn(
                                    "group flex items-center justify-between p-3 rounded-xl transition-all duration-200 cursor-pointer border",
                                    activeSessionId === session.id
                                        ? "bg-primary/10 border-primary/20"
                                        : "hover:bg-white/5 border-transparent hover:border-white/5"
                                )}
                                onClick={() => handleSessionClick(session)}
                            >
                                <div className="flex items-center gap-3 overflow-hidden">
                                    <div className={cn(
                                        "w-2 h-2 rounded-full",
                                        activeSessionId === session.id ? "bg-primary shadow-[0_0_8px_rgba(124,58,237,0.5)]" : "bg-muted-foreground/30"
                                    )} />
                                    <div className="flex flex-col overflow-hidden">
                                        <div className="flex items-center gap-1.5">
                                            <span className={cn(
                                                "text-sm font-medium truncate",
                                                activeSessionId === session.id ? "text-white" : "text-muted-foreground group-hover:text-white"
                                            )}>
                                                {session.name}
                                            </span>
                                            {session.voice_status === "expired" && (
                                                <AlertTriangle size={12} className="text-red-400 flex-shrink-0" title="Voice expired - please re-upload" />
                                            )}
                                            {session.voice_status === "warning" && (
                                                <AlertTriangle size={12} className="text-orange-400 flex-shrink-0" title={`Voice expires in ${session.days_until_expiry} day(s)`} />
                                            )}
                                        </div>
                                        <span className="text-xs text-muted-foreground truncate opacity-60">
                                            {session.preview}
                                        </span>
                                    </div>
                                </div>

                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                        <Button variant="ghost" size="icon" className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <MoreVertical size={14} className="text-muted-foreground" />
                                        </Button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-40 bg-sidebar border-white/10">
                                        <DropdownMenuItem
                                            className="cursor-pointer"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onManageSession(session);
                                            }}
                                        >
                                            <Database size={14} className="mr-2" />
                                            Manage
                                        </DropdownMenuItem>
                                        <DropdownMenuItem
                                            className="text-destructive focus:text-destructive focus:bg-destructive/10 cursor-pointer"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onDeleteSession(session.id);
                                            }}
                                        >
                                            <Trash2 size={14} className="mr-2" />
                                            Delete
                                        </DropdownMenuItem>
                                    </DropdownMenuContent>
                                </DropdownMenu>
                            </div>
                        ))
                    )}
                </div>


            </ScrollArea>

            <div className="p-4 border-t border-white/5 space-y-2">
                <Button
                    variant="ghost"
                    className="w-full justify-start gap-3 text-muted-foreground hover:text-white hover:bg-white/5"
                    onClick={() => setFaqOpen(true)}
                >
                    <HelpCircle size={18} />
                    Help & Guide
                </Button>

                <Button
                    variant="ghost"
                    className="w-full justify-start gap-3 text-muted-foreground hover:text-white hover:bg-white/5"
                    onClick={onOpenSettings}
                >
                    <Settings size={18} />
                    Settings
                </Button>

                <FAQModal open={faqOpen} onOpenChange={setFaqOpen} />
            </div>
        </div>
    );
}
