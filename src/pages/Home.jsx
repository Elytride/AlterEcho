import { useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { ChatInterface } from "@/components/layout/ChatInterface";
import { FilesModal } from "@/components/modals/FilesModal";
import { SettingsModal } from "@/components/modals/SettingsModal";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Home() {
    const [filesOpen, setFilesOpen] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [currentSession, setCurrentSession] = useState({ id: "1", name: "Alan Turing" });

    const handleOpenFiles = () => {
        setFilesOpen(true);
        setSidebarOpen(false);
    };

    const handleOpenSettings = () => {
        setSettingsOpen(true);
        setSidebarOpen(false);
    };

    const handleSessionChange = (session) => {
        setCurrentSession(session);
        setSidebarOpen(false);
    };

    return (
        <div className="flex h-screen w-full bg-background overflow-hidden text-foreground">
            {/* Desktop Sidebar */}
            <div className="hidden lg:flex">
                <Sidebar
                    onOpenFiles={handleOpenFiles}
                    onOpenSettings={handleOpenSettings}
                    onSessionChange={handleSessionChange}
                />
            </div>

            {/* Mobile Sidebar Drawer */}
            <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
                <SheetContent side="left" className="w-80 p-0 border-white/5 bg-sidebar">
                    <Sidebar
                        onOpenFiles={handleOpenFiles}
                        onOpenSettings={handleOpenSettings}
                        onSessionChange={handleSessionChange}
                    />
                </SheetContent>
            </Sheet>

            {/* Chat Area */}
            <main className="flex-1 flex flex-col relative h-full w-full lg:w-auto">
                {/* Mobile Menu Button */}
                <div className="lg:hidden h-16 border-b border-white/5 flex items-center px-4 bg-background/50 backdrop-blur-sm">
                    <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
                        <SheetTrigger asChild>
                            <Button variant="ghost" size="icon" className="text-white">
                                <Menu size={24} />
                            </Button>
                        </SheetTrigger>
                    </Sheet>
                </div>

                <ChatInterface
                    sessionId={currentSession.id}
                    sessionName={currentSession.name}
                />
            </main>

            <FilesModal open={filesOpen} onOpenChange={setFilesOpen} />
            <SettingsModal open={settingsOpen} onOpenChange={setSettingsOpen} />
        </div>
    );
}
