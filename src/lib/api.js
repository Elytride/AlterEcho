/**
 * API Service Layer for NullTale
 * Handles all communication with the Python backend
 */

const API_BASE = '/api';

// --- Chat ---
export async function sendMessage(content, sessionId = '1') {
    const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, session_id: sessionId }),
    });
    if (!response.ok) throw new Error('Failed to send message');
    return response.json();
}

export async function getMessages(sessionId) {
    const response = await fetch(`${API_BASE}/messages/${sessionId}`);
    if (!response.ok) throw new Error('Failed to fetch messages');
    return response.json();
}

// --- Sessions ---
export async function getSessions() {
    const response = await fetch(`${API_BASE}/sessions`);
    if (!response.ok) throw new Error('Failed to fetch sessions');
    return response.json();
}

export async function createSession(name) {
    const response = await fetch(`${API_BASE}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    });
    if (!response.ok) throw new Error('Failed to create session');
    return response.json();
}

export async function deleteSession(sessionId) {
    const response = await fetch(`${API_BASE}/sessions/${sessionId}`, {
        method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete session');
    return response.json();
}

// --- Files ---
export async function uploadFile(files, fileType) {
    const formData = new FormData();

    // Support both single file and FileList
    if (files instanceof FileList || Array.isArray(files)) {
        for (const file of files) {
            formData.append('file', file);
        }
    } else {
        formData.append('file', files);
    }

    const response = await fetch(`${API_BASE}/files/${fileType}`, {
        method: 'POST',
        body: formData,
    });
    if (!response.ok) throw new Error('Failed to upload file');
    return response.json();
}

export async function listFiles(fileType) {
    const response = await fetch(`${API_BASE}/files/${fileType}`);
    if (!response.ok) throw new Error('Failed to list files');
    return response.json();
}

export async function getParticipants(fileType, fileId) {
    const response = await fetch(`${API_BASE}/files/${fileType}/${fileId}/participants`);
    if (!response.ok) throw new Error('Failed to get participants');
    return response.json();
}

export async function setSubject(fileType, fileId, subject) {
    const response = await fetch(`${API_BASE}/files/${fileType}/${fileId}/subject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject }),
    });
    if (!response.ok) throw new Error('Failed to set subject');
    return response.json();
}

export async function deleteUploadedFile(fileType, fileId) {
    const response = await fetch(`${API_BASE}/files/${fileType}/${fileId}`, {
        method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete file');
    return response.json();
}

// --- ZIP Handling ---
export async function selectZipConversations(zipId, conversations) {
    const response = await fetch(`${API_BASE}/files/text/zip/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zip_id: zipId, conversations }),
    });
    if (!response.ok) throw new Error('Failed to select ZIP conversations');
    return response.json();
}

// --- AI Refresh ---
export async function checkRefreshReady() {
    const response = await fetch(`${API_BASE}/refresh/ready`);
    if (!response.ok) throw new Error('Failed to check refresh status');
    return response.json();
}

export async function refreshAIMemory({ sessionId, onProgress, onComplete, onError }) {
    try {
        const response = await fetch(`${API_BASE}/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
        });

        if (!response.ok) {
            throw new Error('Failed to start processing');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE messages
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6).trim());

                        if (data.step === 'complete' && onComplete) {
                            onComplete(data);
                        } else if (data.step === 'error' && onError) {
                            onError(data.message);
                        } else if (data.step === 'progress' && onProgress) {
                            onProgress(data);
                        }
                    } catch (e) {
                        console.warn('Failed to parse SSE data:', line, e);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Refresh AI memory error:', error);
        if (onError) onError(error.message);
    }
}

// --- Settings ---
export async function getSettings() {
    const response = await fetch(`${API_BASE}/settings`);
    if (!response.ok) throw new Error('Failed to fetch settings');
    return response.json();
}

export async function updateSettings(settings) {
    const response = await fetch(`${API_BASE}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
    });
    if (!response.ok) throw new Error('Failed to update settings');
    return response.json();
}

// --- Voice Call Streaming ---
/**
 * Stream a voice call response with both text and audio chunks.
 * @param {string} content - The user's message
 * @param {string} sessionId - The session ID
 * @param {function} onText - Callback for text chunks
 * @param {function} onAudio - Callback for audio chunks (base64)
 * @param {function} onStatus - Callback for status updates
 * @param {function} onDone - Callback when complete
 * @param {function} onError - Callback for errors
 */
export async function streamVoiceCall(content, sessionId, { onText, onAudio, onStatus, onDone, onError }) {
    try {
        const response = await fetch(`${API_BASE}/call/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, session_id: sessionId }),
        });

        if (!response.ok) {
            throw new Error('Failed to start voice call stream');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE messages
            const lines = buffer.split('\n');
            buffer = lines.pop() || ''; // Keep incomplete line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        // Parse the JSON data
                        const dataStr = line.slice(6).trim();
                        const data = JSON.parse(dataStr);

                        if (data.type === 'text' && onText) {
                            onText(data.content);
                        } else if (data.type === 'audio' && onAudio) {
                            onAudio(data.content, data.index);
                        } else if (data.type === 'status' && onStatus) {
                            onStatus(data.content);
                        } else if (data.type === 'done' && onDone) {
                            onDone(data.full_text);
                        } else if (data.type === 'error' && onError) {
                            onError(data.content);
                        }
                    } catch (e) {
                        console.warn('Failed to parse SSE data:', line, e);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Voice call stream error:', error);
        if (onError) onError(error.message);
    }
}

// --- List Voices ---
export async function listVoices() {
    const response = await fetch(`${API_BASE}/voices`);
    if (!response.ok) throw new Error('Failed to list voices');
    return response.json();
}

// --- Warmup Models ---
export async function warmupModels() {
    try {
        const response = await fetch(`${API_BASE}/warmup`, { method: 'POST' });
        if (!response.ok) throw new Error('Failed to warmup');
        return response.json();
    } catch (e) {
        console.warn('Warmup failed:', e);
        return { status: 'error' };
    }
}

// --- Voice Cloning (WaveSpeed) ---
export async function cloneVoice(sessionId, audioFile) {
    const formData = new FormData();
    formData.append('file', audioFile);

    const response = await fetch(`${API_BASE}/voice/clone/${sessionId}`, {
        method: 'POST',
        body: formData,
    });
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Clone failed' }));
        throw new Error(error.detail || 'Failed to clone voice');
    }
    return response.json();
}

export async function getVoiceStatus(sessionId) {
    const response = await fetch(`${API_BASE}/voice/status/${sessionId}`);
    if (!response.ok) throw new Error('Failed to get voice status');
    return response.json();
}
