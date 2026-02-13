// ===== State Management =====
const state = {
    apiKey: '',
    adminKey: '',
    currentPanel: 'chat',
    selectedModel: '',
    messages: [],
    isStreaming: false,
    uploadedFiles: [],
    imageUrls: [],
    models: [],
    hasValidApiKey: false,
    hasValidAdminKey: false,
    costTrackingEnabled: false,  // Will be enabled if backend supports it
    uploadEndpointAvailable: false,  // Will be enabled if backend supports it
    pricingApiAvailable: false  // Will be enabled if backend supports it
};

// ===== Toast Notifications =====
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;
    container.appendChild(toast);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        }
    }, 5000);
}

// ===== API Helper =====
async function apiCall(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${window.location.origin}${endpoint}`;

    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };

    // Add auth header based on endpoint
    if (endpoint.startsWith('/admin') && state.adminKey) {
        headers['Authorization'] = `Bearer ${state.adminKey}`;
    } else if (state.apiKey && !endpoint.startsWith('/admin')) {
        headers['Authorization'] = `Bearer ${state.apiKey}`;
    }

    try {
        const response = await fetch(url, {
            ...options,
            headers
        });

        // Handle specific error codes
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));

            switch (response.status) {
                case 401:
                    if (endpoint.startsWith('/admin')) {
                        if (state.adminKey) {
                            showToast('Invalid admin key', 'error');
                        }
                        state.hasValidAdminKey = false;
                    } else {
                        showToast('Invalid API key', 'error');
                        state.hasValidApiKey = false;
                        disableChatInterface();
                    }
                    break;
                case 403:
                    showToast('Access forbidden', 'error');
                    break;
                case 404:
                    showToast(errorData.detail || 'Not found', 'error');
                    break;
                case 409:
                    showToast(errorData.detail || 'Conflict - resource already exists', 'error');
                    break;
                case 413:
                    showToast('File exceeds 10MB limit', 'error');
                    break;
                case 415:
                    showToast('Unsupported file type. Use JPEG, PNG, GIF, or WebP', 'error');
                    break;
                case 429:
                    let limitMsg = 'Rate limit exceeded';
                    if (errorData.detail && typeof errorData.detail === 'object') {
                        limitMsg = errorData.detail.message || limitMsg;
                        const msg = limitMsg.toLowerCase();
                        if (msg.includes('requests per minute')) {
                            limitMsg += '. Ask admin to raise your requests/minute limit';
                        } else if (msg.includes('tokens per minute')) {
                            limitMsg += '. Wait a moment or ask admin to raise your token limit';
                        } else if (msg.includes('total token limit')) {
                            limitMsg += '. Contact admin to increase your allocation';
                        } else if (msg.includes('requests per day')) {
                            limitMsg += '. Daily request limit reached — try again tomorrow';
                        } else if (msg.includes('tokens per day')) {
                            limitMsg += '. Daily token limit reached — try again tomorrow';
                        }
                    } else if (typeof errorData.detail === 'string') {
                        limitMsg = errorData.detail;
                    }
                    showToast(limitMsg, 'error');
                    disableSendButtonTemporarily();
                    break;
                case 502:
                case 503:
                    showToast('Backend unavailable — is Ollama running?', 'error');
                    break;
                default:
                    showToast(errorData.detail || 'An error occurred', 'error');
            }

            throw new Error(errorData.detail || response.statusText);
        }

        return await response.json();
    } catch (error) {
        if (error.message.includes('fetch')) {
            showToast('Network error — check your connection', 'error');
        }
        throw error;
    }
}

// ===== API Key Validation =====
function resetAdminPanel() {
    state.hasValidAdminKey = false;
    state.adminKey = '';
    state.pricingApiAvailable = false;
    document.getElementById('admin-key').value = '';
    const adminContent = document.getElementById('admin-content');
    const emptyState = document.getElementById('admin-panel').querySelector('.empty-state');
    if (adminContent) adminContent.style.display = 'none';
    if (emptyState) emptyState.style.display = 'flex';
    // Also hide pricing sections
    const pricingMgmt = document.getElementById('pricing-management-section');
    if (pricingMgmt) pricingMgmt.style.display = 'none';
    const pricingHistory = document.getElementById('pricing-history-section');
    if (pricingHistory) pricingHistory.style.display = 'none';
}

async function validateApiKey() {
    if (!state.apiKey) {
        state.hasValidApiKey = false;
        return false;
    }

    resetAdminPanel();

    try {
        await apiCall('/v1/usage');
        state.hasValidApiKey = true;
        enableChatInterface();
        loadModels();
        return true;
    } catch (error) {
        state.hasValidApiKey = false;
        disableChatInterface();
        return false;
    }
}

// ===== UI State Management =====
function enableChatInterface() {
    document.getElementById('chat-input').disabled = false;
    document.getElementById('send-btn').disabled = false;
    document.getElementById('model-select').disabled = false;
    document.getElementById('refresh-usage-btn').disabled = false;

    // Enable upload controls (hidden file input always enabled; visible buttons depend on model)
    document.getElementById('image-upload').disabled = false;
    const urlInput = document.getElementById('image-url-input');
    if (urlInput) urlInput.disabled = false;
    const addUrlBtn = document.getElementById('add-image-url-btn');
    if (addUrlBtn) addUrlBtn.disabled = false;

    // Hide empty state in chat panel
    const chatMessages = document.getElementById('chat-messages');
    const emptyState = chatMessages.querySelector('.empty-state');
    if (emptyState) {
        emptyState.style.display = 'none';
    }

    // Show usage content
    const usageContent = document.getElementById('usage-content');
    const usageEmptyState = document.getElementById('usage-panel').querySelector('.empty-state');
    if (usageContent && usageEmptyState) {
        usageEmptyState.style.display = 'none';
        usageContent.style.display = 'block';
    }

    // Enable/disable upload buttons based on selected model
    updateUploadButtonState();
}

function updateUploadButtonState() {
    const isVisionModel = state.selectedModel && state.selectedModel.startsWith('moondream');
    const uploadBtn = document.getElementById('upload-btn');
    const imageUrlBtn = document.getElementById('image-url-btn');

    if (uploadBtn) uploadBtn.disabled = !isVisionModel || !state.hasValidApiKey;
    if (imageUrlBtn) imageUrlBtn.disabled = !isVisionModel || !state.hasValidApiKey;
}

function disableChatInterface() {
    document.getElementById('chat-input').disabled = true;
    document.getElementById('send-btn').disabled = true;
    document.getElementById('model-select').disabled = true;
    document.getElementById('upload-btn').disabled = true;
    document.getElementById('image-upload').disabled = true;
    const disUrlBtn = document.getElementById('image-url-btn');
    if (disUrlBtn) disUrlBtn.disabled = true;
    const disUrlInput = document.getElementById('image-url-input');
    if (disUrlInput) disUrlInput.disabled = true;
    const disAddUrlBtn = document.getElementById('add-image-url-btn');
    if (disAddUrlBtn) disAddUrlBtn.disabled = true;

    // Show empty state
    const chatMessages = document.getElementById('chat-messages');
    const emptyState = chatMessages.querySelector('.empty-state');
    if (emptyState) {
        emptyState.style.display = 'flex';
    }

    // Reset usage header
    const usageHeader = document.querySelector('#usage-panel .panel-header h2');
    if (usageHeader) usageHeader.textContent = 'Usage Statistics';
}

function disableSendButtonTemporarily() {
    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = true;
    let countdown = 5;
    const originalText = sendBtn.textContent;

    const interval = setInterval(() => {
        sendBtn.textContent = `Wait ${countdown}s`;
        countdown--;

        if (countdown < 0) {
            clearInterval(interval);
            sendBtn.textContent = originalText;
            sendBtn.disabled = false;
        }
    }, 1000);
}

// ===== Models Management =====
const ALLOWED_MODELS = ['llama3.2:1b', 'moondream'];

async function loadModels() {
    try {
        const response = await apiCall('/v1/models');
        const allModels = (response.data || []).map(m => ({
            ...m,
            id: m.id.endsWith(':latest') ? m.id.slice(0, -7) : m.id
        }));

        // Filter to allowed models; fall back to all if none match
        const filtered = allModels.filter(m => ALLOWED_MODELS.includes(m.id));
        state.models = filtered.length > 0 ? filtered : allModels;

        const select = document.getElementById('model-select');
        select.innerHTML = state.models.length > 0
            ? state.models.map(m => `<option value="${m.id}">${m.id}</option>`).join('')
            : '<option value="">No models available</option>';

        if (state.models.length > 0) {
            state.selectedModel = state.models[0].id;
            select.value = state.selectedModel;
        }
        updateUploadButtonState();
    } catch (error) {
        console.error('Failed to load models:', error);
        document.getElementById('model-select').innerHTML = '<option value="">Error loading models</option>';
    }
}

// ===== Chat Functions =====
function addMessage(role, content, isError = false) {
    const messagesContainer = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role}${isError ? ' message-error' : ''}`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = content;

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(bubble);
    messagesContainer.appendChild(messageDiv);

    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    return messageDiv;
}

function updateLastMessage(content) {
    const messagesContainer = document.getElementById('chat-messages');
    const lastMessage = messagesContainer.lastElementChild;
    if (lastMessage && lastMessage.classList.contains('message-assistant')) {
        const bubble = lastMessage.querySelector('.message-bubble');
        bubble.textContent = content;

        // Only auto-scroll if user is near the bottom (within 50px)
        const isNearBottom = (messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight) < 50;
        if (isNearBottom) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }
}

function markMessageAsIncomplete() {
    const messagesContainer = document.getElementById('chat-messages');
    const lastMessage = messagesContainer.lastElementChild;
    if (lastMessage && lastMessage.classList.contains('message-assistant')) {
        lastMessage.classList.add('message-error');
        const bubble = lastMessage.querySelector('.message-bubble');
        bubble.textContent += '\n[Incomplete - stream interrupted]';
    }
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message || !state.selectedModel) return;
    if (state.isStreaming) return;

    // Add user message to UI
    addMessage('user', message);
    state.messages.push({ role: 'user', content: message });

    // Clear input
    input.value = '';

    // Disable send while processing
    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = true;
    state.isStreaming = true;

    try {
        if (hasAttachments()) {
            await sendUploadMessage();
            clearAttachments();
        } else {
            const shouldStream = document.getElementById('stream-toggle').checked;
            if (shouldStream) {
                await sendStreamingMessage();
            } else {
                await sendNonStreamingMessage();
            }
        }
    } catch (error) {
        console.error('Error sending message:', error);
        addMessage('assistant', 'Error: ' + error.message, true);
    } finally {
        sendBtn.disabled = false;
        state.isStreaming = false;
    }
}

async function sendNonStreamingMessage() {
    const response = await apiCall('/v1/chat/completions', {
        method: 'POST',
        body: JSON.stringify({
            model: state.selectedModel,
            messages: state.messages,
            stream: false
        })
    });

    const content = response.choices[0]?.message?.content || '';
    addMessage('assistant', content);
    state.messages.push({ role: 'assistant', content });
}

async function sendStreamingMessage() {
    const url = `${window.location.origin}/v1/chat/completions`;
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${state.apiKey}`
    };

    const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({
            model: state.selectedModel,
            messages: state.messages,
            stream: true
        })
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        let errorMsg = error.detail;
        if (errorMsg && typeof errorMsg === 'object') {
            errorMsg = errorMsg.message || 'Unknown error';
        }
        throw new Error(errorMsg);
    }

    // Add empty assistant message
    const messageDiv = addMessage('assistant', '');
    let fullContent = '';

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);

                    if (data === '[DONE]') {
                        continue;
                    }

                    try {
                        const parsed = JSON.parse(data);

                        // Check for error in stream
                        if (parsed.error) {
                            markMessageAsIncomplete();
                            showToast(parsed.error.message || 'Stream error', 'error');
                            break;
                        }

                        const content = parsed.choices?.[0]?.delta?.content;
                        if (content) {
                            fullContent += content;
                            updateLastMessage(fullContent);
                        }
                    } catch (e) {
                        // Ignore JSON parse errors for incomplete chunks
                    }
                }
            }
        }
    } catch (error) {
        markMessageAsIncomplete();
        showToast('Stream interrupted', 'error');
        throw error;
    }

    state.messages.push({ role: 'assistant', content: fullContent });
}

// ===== File Upload & Image URL =====
function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    state.uploadedFiles = files;
    renderAttachmentPreview();
}

function removeFile(index) {
    state.uploadedFiles.splice(index, 1);
    const input = document.getElementById('image-upload');

    // Update file input
    const dt = new DataTransfer();
    state.uploadedFiles.forEach(file => dt.items.add(file));
    input.files = dt.files;

    renderAttachmentPreview();
}

function addImageUrl() {
    const input = document.getElementById('image-url-input');
    const url = input.value.trim();
    if (!url) return;

    state.imageUrls = state.imageUrls || [];
    state.imageUrls.push(url);
    input.value = '';
    document.getElementById('image-url-row').style.display = 'none';
    renderAttachmentPreview();
}

function removeImageUrl(index) {
    state.imageUrls.splice(index, 1);
    renderAttachmentPreview();
}

function renderAttachmentPreview() {
    const preview = document.getElementById('file-preview');
    preview.innerHTML = '';

    const hasFiles = state.uploadedFiles.length > 0;
    const urls = state.imageUrls || [];
    const hasUrls = urls.length > 0;

    if (!hasFiles && !hasUrls) {
        preview.style.display = 'none';
        return;
    }

    preview.style.display = 'flex';

    state.uploadedFiles.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'file-preview-item';
        item.innerHTML = `
            <span>${file.name}</span>
            <button class="remove-file-btn" onclick="removeFile(${index})">×</button>
        `;
        preview.appendChild(item);
    });

    urls.forEach((url, index) => {
        const item = document.createElement('div');
        item.className = 'file-preview-item';
        const shortUrl = url.length > 40 ? url.substring(0, 37) + '...' : url;
        item.innerHTML = `
            <span title="${url}">🔗 ${shortUrl}</span>
            <button class="remove-file-btn" onclick="removeImageUrl(${index})">×</button>
        `;
        preview.appendChild(item);
    });
}

function hasAttachments() {
    return state.uploadedFiles.length > 0 || (state.imageUrls && state.imageUrls.length > 0);
}

function clearAttachments() {
    state.uploadedFiles = [];
    state.imageUrls = [];
    document.getElementById('image-upload').value = '';
    renderAttachmentPreview();
}

async function sendUploadMessage() {
    const formData = new FormData();
    formData.append('model', state.selectedModel);
    formData.append('messages', JSON.stringify(state.messages));
    formData.append('stream', document.getElementById('stream-toggle').checked);

    // Add uploaded files
    state.uploadedFiles.forEach(file => {
        formData.append('files', file);
    });

    // For image URLs, inject them into the last user message as content parts
    const urls = state.imageUrls || [];
    if (urls.length > 0) {
        // Modify the messages to include image URLs in the last user message
        const msgs = JSON.parse(JSON.stringify(state.messages));
        const lastUserMsg = msgs.findLast(m => m.role === 'user');
        if (lastUserMsg) {
            const textContent = typeof lastUserMsg.content === 'string'
                ? lastUserMsg.content
                : lastUserMsg.content.filter(p => p.type === 'text').map(p => p.text).join(' ');

            lastUserMsg.content = [
                { type: 'text', text: textContent },
                ...urls.map(u => ({ type: 'image_url', image_url: { url: u } }))
            ];
        }
        formData.set('messages', JSON.stringify(msgs));
    }

    const shouldStream = document.getElementById('stream-toggle').checked;

    if (shouldStream) {
        // Streaming upload
        const url = `${window.location.origin}/v1/chat/completions/upload`;
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${state.apiKey}` },
            body: formData
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
            let errorMsg = error.detail;
            if (errorMsg && typeof errorMsg === 'object') errorMsg = errorMsg.message || 'Upload failed';
            throw new Error(errorMsg);
        }

        const messageDiv = addMessage('assistant', '');
        let fullContent = '';
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data === '[DONE]') continue;

                        try {
                            const parsed = JSON.parse(data);
                            if (parsed.error) {
                                markMessageAsIncomplete();
                                showToast(parsed.error.message || 'Stream error', 'error');
                                break;
                            }
                            const content = parsed.choices?.[0]?.delta?.content;
                            if (content) {
                                fullContent += content;
                                updateLastMessage(fullContent);
                            }
                        } catch (e) { /* ignore incomplete chunks */ }
                    }
                }
            }
        } catch (error) {
            markMessageAsIncomplete();
            showToast('Stream interrupted', 'error');
            throw error;
        }

        state.messages.push({ role: 'assistant', content: fullContent });
    } else {
        // Non-streaming upload
        const url = `${window.location.origin}/v1/chat/completions/upload`;
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${state.apiKey}` },
            body: formData
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
            let errorMsg = error.detail;
            if (errorMsg && typeof errorMsg === 'object') errorMsg = errorMsg.message || 'Upload failed';
            throw new Error(errorMsg);
        }

        const result = await response.json();
        const content = result.choices[0]?.message?.content || '';
        addMessage('assistant', content);
        state.messages.push({ role: 'assistant', content });
    }
}

// ===== Usage Panel =====
async function loadUsageStats() {
    try {
        const stats = await apiCall('/v1/usage');

        // Update usage header with user name
        const usageHeader = document.querySelector('#usage-panel .panel-header h2');
        if (usageHeader && stats.user_id) {
            usageHeader.textContent = `Usage Statistics - ${stats.user_id}`;
        }

        // Update summary cards
        document.getElementById('total-requests').textContent = stats.request_count || 0;
        document.getElementById('total-tokens').textContent = stats.total_tokens || 0;
        document.getElementById('prompt-tokens').textContent = stats.prompt_tokens || 0;
        document.getElementById('completion-tokens').textContent = stats.completion_tokens || 0;

        // Show cost if available (Phase 2)
        if (stats.total_cost !== undefined && stats.total_cost > 0) {
            state.costTrackingEnabled = true;
            document.getElementById('cost-card').style.display = 'block';
            document.getElementById('total-cost').textContent = `$${stats.total_cost.toFixed(4)}`;

            // Show cost column in table
            document.querySelectorAll('.cost-column').forEach(el => el.style.display = 'table-cell');
        }

        // Update per-model table
        const tbody = document.querySelector('#usage-table tbody');
        tbody.innerHTML = '';

        const byModel = stats.by_model || {};
        Object.entries(byModel).forEach(([model, data]) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${model}</td>
                <td>${data.request_count || 0}</td>
                <td>${data.prompt_tokens || 0}</td>
                <td>${data.completion_tokens || 0}</td>
                <td>${data.total_tokens || 0}</td>
                ${state.costTrackingEnabled ? `<td class="cost-column">$${(data.total_cost || 0).toFixed(4)}</td>` : ''}
            `;
            tbody.appendChild(row);
        });

        // Ensure all allowed models appear even with 0 usage
        ALLOWED_MODELS.forEach(model => {
            if (!byModel[model]) {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${model}</td>
                    <td>0</td>
                    <td>0</td>
                    <td>0</td>
                    <td>0</td>
                    ${state.costTrackingEnabled ? '<td class="cost-column">$0.0000</td>' : ''}
                `;
                tbody.appendChild(row);
            }
        });

        // Load user-facing pricing
        loadUserPricing();
    } catch (error) {
        console.error('Failed to load usage stats:', error);
    }
}

async function loadUserPricing() {
    try {
        const response = await apiCall('/v1/pricing');
        const pricing = response.pricing || [];
        const section = document.getElementById('user-pricing-section');
        const tbody = document.querySelector('#user-pricing-table tbody');
        if (!section || !tbody) return;

        section.style.display = '';
        tbody.innerHTML = '';

        // Build lookup from API response
        const pricingMap = {};
        pricing.forEach(p => { pricingMap[p.model] = p; });

        // Always show all allowed models
        ALLOWED_MODELS.forEach(model => {
            const p = pricingMap[model];
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${model}</td>
                <td>$${p ? p.input_cost_per_million.toFixed(2) : '0.00'}</td>
                <td>$${p ? p.output_cost_per_million.toFixed(2) : '0.00'}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        // On error, still show models with $0.00
        const section = document.getElementById('user-pricing-section');
        const tbody = document.querySelector('#user-pricing-table tbody');
        if (section && tbody) {
            section.style.display = '';
            tbody.innerHTML = '';
            ALLOWED_MODELS.forEach(model => {
                const row = document.createElement('tr');
                row.innerHTML = `<td>${model}</td><td>$0.00</td><td>$0.00</td>`;
                tbody.appendChild(row);
            });
        }
    }
}

// ===== Admin Panel =====
async function loadUsers() {
    const apiKeyDisplay = document.getElementById('new-api-key-display');
    if (apiKeyDisplay) apiKeyDisplay.style.display = 'none';

    try {
        const response = await apiCall('/admin/users');
        const users = response.users || [];

        const tbody = document.querySelector('#users-table tbody');
        tbody.innerHTML = '';

        const limitSelect = document.getElementById('limit-user-select');
        limitSelect.innerHTML = '<option value="">Select a user...</option>';

        users.forEach(user => {
            // Table row
            const row = document.createElement('tr');
            const createdDate = new Date(user.created_at).toLocaleString();
            row.innerHTML = `
                <td>${user.user_id}</td>
                <td><code class="api-key-display">${user.api_key}</code></td>
                <td>${createdDate}</td>
                <td>
                    <button class="btn-small btn-danger" onclick="deleteUser('${user.user_id}')">Delete</button>
                </td>
            `;
            tbody.appendChild(row);

            // Add to limit select
            const option = document.createElement('option');
            option.value = user.user_id;
            option.textContent = user.user_id;
            limitSelect.appendChild(option);
        });

        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">No users yet</td></tr>';
        }

        state.hasValidAdminKey = true;
        showAdminContent();
    } catch (error) {
        console.error('Failed to load users:', error);
        state.hasValidAdminKey = false;
    }
}

function showAdminContent() {
    const adminContent = document.getElementById('admin-content');
    const emptyState = document.getElementById('admin-panel').querySelector('.empty-state');
    if (adminContent && emptyState) {
        emptyState.style.display = 'none';
        adminContent.style.display = 'block';
    }
}

async function createUser(event) {
    event.preventDefault();

    const userIdInput = document.getElementById('new-user-id');
    const userId = userIdInput.value.trim();

    if (!userId) return;

    try {
        const response = await apiCall('/admin/users', {
            method: 'POST',
            body: JSON.stringify({ user_id: userId })
        });

        // Show the new API key
        document.getElementById('new-api-key-value').textContent = response.api_key;
        document.getElementById('new-api-key-display').style.display = 'block';

        showToast(`User created: ${userId}`, 'success');

        // Clear form
        userIdInput.value = '';

        // Reload users list
        loadUsers();
    } catch (error) {
        console.error('Failed to create user:', error);
    }
}

async function deleteUser(userId) {
    if (!confirm(`Delete user "${userId}"? This cannot be undone.`)) {
        return;
    }

    try {
        await apiCall(`/admin/users/${userId}`, { method: 'DELETE' });
        showToast(`User deleted: ${userId}`, 'success');
        loadUsers();
    } catch (error) {
        console.error('Failed to delete user:', error);
    }
}

async function updateRateLimits(event) {
    event.preventDefault();

    const userId = document.getElementById('limit-user-select').value;
    if (!userId) {
        showToast('Please select a user', 'warning');
        return;
    }

    const limits = {
        requests_per_minute: parseInt(document.getElementById('requests-per-minute').value) || null,
        requests_per_day: parseInt(document.getElementById('requests-per-day').value) || null,
        tokens_per_minute: parseInt(document.getElementById('tokens-per-minute').value) || null,
        tokens_per_day: parseInt(document.getElementById('tokens-per-day').value) || null,
        total_token_limit: parseInt(document.getElementById('total-token-limit').value) || null
    };

    // Remove null values
    Object.keys(limits).forEach(key => {
        if (limits[key] === null) delete limits[key];
    });

    if (Object.keys(limits).length === 0) {
        showToast('Please enter at least one limit value', 'warning');
        return;
    }

    try {
        await apiCall(`/admin/users/${userId}/limits`, {
            method: 'PUT',
            body: JSON.stringify(limits)
        });

        showToast(`Rate limits updated for ${userId}`, 'success');

        // Clear form
        document.getElementById('rate-limits-form').reset();
    } catch (error) {
        console.error('Failed to update rate limits:', error);
    }
}

async function loadUserLimits() {
    const userId = document.getElementById('limit-user-select').value;
    if (!userId) return;

    try {
        const limits = await apiCall(`/admin/users/${userId}/limits`);

        document.getElementById('requests-per-minute').value = limits.requests_per_minute || '';
        document.getElementById('requests-per-day').value = limits.requests_per_day || '';
        document.getElementById('tokens-per-minute').value = limits.tokens_per_minute || '';
        document.getElementById('tokens-per-day').value = limits.tokens_per_day || '';
        document.getElementById('total-token-limit').value = limits.total_token_limit || '';
    } catch (error) {
        console.error('Failed to load user limits:', error);
    }
}

// ===== Pricing Management (Phase 2) =====
async function checkPricingApiAvailability() {
    try {
        await apiCall('/admin/pricing');
        state.pricingApiAvailable = true;
        document.getElementById('pricing-management-section').style.display = 'block';
        document.getElementById('pricing-history-section').style.display = 'block';
    } catch (error) {
        // Pricing API not available yet
        state.pricingApiAvailable = false;
    }
}

async function loadPricing() {
    if (!state.pricingApiAvailable) return;

    try {
        const response = await apiCall('/admin/pricing');
        const pricing = response.pricing || [];

        const tbody = document.querySelector('#pricing-table tbody');
        tbody.innerHTML = '';

        // Build lookup
        const pricingMap = {};
        pricing.forEach(p => { pricingMap[p.model] = p; });

        // Always show all allowed models
        ALLOWED_MODELS.forEach(model => {
            const p = pricingMap[model];
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${model}</td>
                <td>$${p ? p.input_cost_per_million.toFixed(2) : '0.00'}</td>
                <td>$${p ? p.output_cost_per_million.toFixed(2) : '0.00'}</td>
                <td>
                    <button class="btn-small btn-danger" onclick="deletePricing('${model}')">Delete</button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Failed to load pricing:', error);
    }
}

async function setPricing(event) {
    event.preventDefault();

    const model = document.getElementById('pricing-model').value.trim();
    const inputCost = parseFloat(document.getElementById('input-cost').value) || 0;
    const outputCost = parseFloat(document.getElementById('output-cost').value) || 0;

    if (!model) return;

    try {
        await apiCall('/admin/pricing', {
            method: 'POST',
            body: JSON.stringify({
                model,
                input_cost_per_million: inputCost,
                output_cost_per_million: outputCost
            })
        });

        showToast(`Pricing updated for ${model}`, 'success');

        // Clear form
        document.getElementById('pricing-form').reset();

        // Reload pricing
        loadPricing();
        loadPricingHistory();
    } catch (error) {
        console.error('Failed to set pricing:', error);
    }
}

async function deletePricing(model) {
    if (!confirm(`Delete pricing for "${model}"?`)) return;

    try {
        await apiCall(`/admin/pricing/${model}`, { method: 'DELETE' });
        showToast(`Pricing deleted for ${model}`, 'success');
        loadPricing();
    } catch (error) {
        console.error('Failed to delete pricing:', error);
    }
}

async function loadPricingHistory() {
    if (!state.pricingApiAvailable) return;

    try {
        const response = await apiCall('/admin/pricing/history/all');
        const history = response.history || [];

        const tbody = document.querySelector('#pricing-history-table tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (history.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">No pricing changes yet</td></tr>';
            return;
        }

        history.slice(0, 10).forEach(entry => {
            const row = document.createElement('tr');
            const date = new Date(entry.changed_at).toLocaleString();
            row.innerHTML = `
                <td>${entry.model}</td>
                <td>$${entry.input_cost_per_million.toFixed(2)}</td>
                <td>$${entry.output_cost_per_million.toFixed(2)}</td>
                <td>${date}</td>
                <td>${entry.changed_by || 'admin'}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Failed to load pricing history:', error);
    }
}

// ===== Panel Switching =====
function switchPanel(panelName) {
    // Update navigation
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.panel === panelName);
    });

    // Update panels
    document.querySelectorAll('.panel').forEach(panel => {
        panel.classList.toggle('active', panel.id === `${panelName}-panel`);
    });

    state.currentPanel = panelName;

    // Hide the generated API key box on every panel switch
    const apiKeyDisplay = document.getElementById('new-api-key-display');
    if (apiKeyDisplay) {
        apiKeyDisplay.style.display = 'none';
    }

    // Load data for the panel
    if (panelName === 'usage' && state.hasValidApiKey) {
        loadUsageStats();
    } else if (panelName === 'admin' && state.adminKey) {
        loadUsers();
        if (state.pricingApiAvailable) {
            loadPricing();
            loadPricingHistory();
        }
    }
}

// ===== Initialization =====
function initializeEventListeners() {
    // API Key "Go" button — validate and activate
    document.getElementById('toggle-api-key').addEventListener('click', async () => {
        const input = document.getElementById('api-key');
        state.apiKey = input.value.trim();
        if (state.apiKey) {
            await validateApiKey();
            if (state.hasValidApiKey) {
                showToast('API key validated', 'success');
                if (state.currentPanel === 'usage') {
                    loadUsageStats();
                }
            }
        } else {
            showToast('Please enter an API key', 'warning');
        }
    });

    // Admin Key "Go" button — validate and load admin data
    document.getElementById('toggle-admin-key').addEventListener('click', async () => {
        const input = document.getElementById('admin-key');
        state.adminKey = input.value.trim();
        if (state.adminKey) {
            await loadUsers();
            if (state.hasValidAdminKey) {
                showToast('Admin key validated', 'success');
                try { await checkPricingApiAvailability(); } catch (e) { /* pricing not available */ }
            }
        } else {
            showToast('Please enter an admin key', 'warning');
        }
    });

    // Navigation
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => switchPanel(btn.dataset.panel));
    });

    // Model selection
    document.getElementById('model-select').addEventListener('change', (e) => {
        state.selectedModel = e.target.value;
        updateUploadButtonState();
    });

    // Chat
    document.getElementById('send-btn').addEventListener('click', sendMessage);
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // File upload
    document.getElementById('upload-btn').addEventListener('click', () => {
        document.getElementById('image-upload').click();
    });
    document.getElementById('image-upload').addEventListener('change', handleFileSelect);

    // Image URL
    const imageUrlBtn = document.getElementById('image-url-btn');
    if (imageUrlBtn) {
        imageUrlBtn.addEventListener('click', () => {
            const row = document.getElementById('image-url-row');
            row.style.display = row.style.display === 'none' ? 'flex' : 'none';
            if (row.style.display === 'flex') {
                document.getElementById('image-url-input').focus();
            }
        });
    }
    const addImageUrlBtn = document.getElementById('add-image-url-btn');
    if (addImageUrlBtn) {
        addImageUrlBtn.addEventListener('click', addImageUrl);
    }
    const cancelImageUrlBtn = document.getElementById('cancel-image-url-btn');
    if (cancelImageUrlBtn) {
        cancelImageUrlBtn.addEventListener('click', () => {
            document.getElementById('image-url-input').value = '';
            document.getElementById('image-url-row').style.display = 'none';
        });
    }
    const imageUrlInput = document.getElementById('image-url-input');
    if (imageUrlInput) {
        imageUrlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addImageUrl();
            }
        });
    }

    // Usage
    document.getElementById('refresh-usage-btn').addEventListener('click', loadUsageStats);

    // Admin forms
    document.getElementById('create-user-form').addEventListener('submit', createUser);
    document.getElementById('rate-limits-form').addEventListener('submit', updateRateLimits);
    document.getElementById('limit-user-select').addEventListener('change', loadUserLimits);

    // Copy API key button
    document.getElementById('copy-api-key-btn').addEventListener('click', () => {
        const apiKey = document.getElementById('new-api-key-value').textContent;
        navigator.clipboard.writeText(apiKey);
        showToast('API key copied to clipboard', 'success');
    });

    // Pricing form (if available)
    const pricingForm = document.getElementById('pricing-form');
    if (pricingForm) {
        pricingForm.addEventListener('submit', setPricing);
    }

    // Refresh pricing button
    const refreshPricingBtn = document.getElementById('refresh-pricing-btn');
    if (refreshPricingBtn) {
        refreshPricingBtn.addEventListener('click', () => {
            loadPricing();
            loadPricingHistory();
        });
    }
}

// ===== On Load =====
document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
});
