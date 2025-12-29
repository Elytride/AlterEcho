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
export async function uploadFile(file, fileType) {
    const formData = new FormData();
    formData.append('file', file);

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

// --- AI Refresh ---
export async function refreshAIMemory() {
    const response = await fetch(`${API_BASE}/refresh`, {
        method: 'POST',
    });
    if (!response.ok) throw new Error('Failed to refresh AI memory');
    return response.json();
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
