import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs";
import { HelpCircle, Database } from "lucide-react";

const FAQ_ITEMS = [
    {
        question: "How do I create a new Chat?",
        answer: "Click the 'New Chat' button at the top. Make sure you've uploaded training data and refreshed AI Memory first."
    },
    {
        question: "What data can I upload?",
        answer: "Text (chat logs, interviews), Video (vlogs, presentations), and Audio (voice recordings). The AI will analyze all to replicate personality."
    },
    {
        question: "How does the AI learn?",
        answer: "Upload source materials and click 'Refresh AI Memory'. The system reindexes neural patterns to incorporate new data."
    },
    {
        question: "Can I use Call mode on mobile?",
        answer: "Yes! Switch to Call mode anytime. Use your device's speaker for voice synthesis and audio input."
    },
    {
        question: "How do I export conversations?",
        answer: "Long-press on any chat session to access options for export, backup, or archive management."
    }
];

export function FAQModal({ open, onOpenChange }) {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl bg-zinc-950 border-white/10 text-white h-[600px] flex flex-col">
                <DialogHeader className="pb-4 border-b border-white/5 mx-6 pt-6">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="p-2 rounded-lg bg-primary/20 text-primary">
                            <HelpCircle size={20} />
                        </div>
                        <DialogTitle className="text-xl">Help & Guide</DialogTitle>
                    </div>
                    <DialogDescription className="text-zinc-400">
                        Everything you need to know about creating and managing personas.
                    </DialogDescription>
                </DialogHeader>

                <Tabs defaultValue="faq" className="flex-1 flex flex-col overflow-hidden">
                    <div className="px-6 py-2 border-b border-white/5 bg-zinc-950/50">
                        <TabsList className="grid w-full grid-cols-2 bg-zinc-900/50">
                            <TabsTrigger value="faq" className="hidden sm:inline-flex">Frequently Asked Questions</TabsTrigger>
                            <TabsTrigger value="faq" className="sm:hidden">FAQ</TabsTrigger>
                            <TabsTrigger value="data">How to Get Data</TabsTrigger>
                        </TabsList>
                    </div>

                    <div className="flex-1 overflow-y-auto px-6 py-4">
                        <TabsContent value="faq" className="mt-0 space-y-4 h-full">
                            <Accordion type="single" collapsible className="w-full">
                                {FAQ_ITEMS.map((item, idx) => (
                                    <AccordionItem key={idx} value={`item-${idx}`} className="border-white/10">
                                        <AccordionTrigger className="text-sm font-medium hover:text-primary transition-colors hover:no-underline text-left">
                                            {item.question}
                                        </AccordionTrigger>
                                        <AccordionContent className="text-zinc-400 text-sm leading-relaxed">
                                            {item.answer}
                                        </AccordionContent>
                                    </AccordionItem>
                                ))}
                            </Accordion>
                        </TabsContent>

                        <TabsContent value="data" className="mt-0 h-full">
                            <div className="space-y-6">
                                <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                                    <h3 className="flex items-center gap-2 text-sm font-medium text-white mb-2">
                                        <Database size={16} className="text-primary" />
                                        Data Collection Guide
                                    </h3>
                                    <p className="text-xs text-zinc-400 leading-relaxed">
                                        To create an accurate persona, you need high-quality source data. The AI uses this to learn speech patterns, vocabulary, and memories.
                                    </p>
                                </div>

                                <div className="space-y-4">
                                    <div>
                                        <h4 className="text-sm font-medium text-white mb-1">1. Message Logs</h4>
                                        <p className="text-sm text-zinc-400">Export chat histories from WhatsApp, Discord, or Telegram. Text files (.txt) work best.</p>
                                    </div>

                                    <div>
                                        <h4 className="text-sm font-medium text-white mb-1">2. Audio Recordings</h4>
                                        <p className="text-sm text-zinc-400">Upload clean voice memos or interview recordings (.mp3, .wav) to train the voice model.</p>
                                    </div>

                                    <div>
                                        <h4 className="text-sm font-medium text-white mb-1">3. Video Content</h4>
                                        <p className="text-sm text-zinc-400">Vlogs, interviews, or presentations. The system extracts both audio and transcriptions.</p>
                                    </div>
                                </div>
                            </div>
                        </TabsContent>
                    </div>
                </Tabs>
            </DialogContent>
        </Dialog>
    );
}
