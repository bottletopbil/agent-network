// CAN Swarm Investor Demo - Application Logic

const API_BASE = 'http://localhost:8080/api';
const UPDATE_INTERVAL = 2000; // 2 seconds

let updateInterval;
let currentThreadId = null;

// DOM Elements
const elements = {
    systemStatus: document.getElementById('systemStatus'),
    workflowContainer: document.getElementById('workflowContainer'),
    threadInfo: document.getElementById('threadInfo'),
    agentsGrid: document.getElementById('agentsGrid'),
    metricTotalTasks: document.getElementById('metricTotalTasks'),
    metricCompleted: document.getElementById('metricCompleted'),
    metricSuccessRate: document.getElementById('metricSuccessRate'),
    metricOperations: document.getElementById('metricOperations'),
    auditLog: document.getElementById('auditLog'),
    auditCount: document.getElementById('auditCount'),
    auditThreadFilter: document.getElementById('auditThreadFilter'),
    btnStartDemo: document.getElementById('btnStartDemo'),
    btnRefresh: document.getElementById('btnRefresh'),
    btnViewDocs: document.getElementById('btnViewDocs'),
    demoStatus: document.getElementById('demoStatus')
};

// API Functions
async function fetchAPI(endpoint) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        return null;
    }
}

async function fetchSystemStatus() {
    const data = await fetchAPI('/status');
    if (!data) return;

    // Update status indicator
    const indicator = elements.systemStatus.querySelector('.status-indicator');
    const statusText = elements.systemStatus.querySelector('span');

    const isOnline = data.status === 'online' &&
        data.infrastructure.nats === 'running' &&
        data.infrastructure.redis === 'running';

    if (isOnline) {
        indicator.style.background = 'var(--status-active)';
        statusText.textContent = 'System Online';
    } else {
        indicator.style.background = 'var(--status-error)';
        statusText.textContent = 'System Offline';
    }

    return data;
}

async function fetchThreads() {
    const data = await fetchAPI('/threads');
    if (!data || !data.threads) return;

    // Update thread selector
    const currentValue = elements.auditThreadFilter.value;
    elements.auditThreadFilter.innerHTML = '<option value="">All Threads</option>';

    data.threads.forEach(thread => {
        const option = document.createElement('option');
        option.value = thread.thread_id;
        option.textContent = `${thread.thread_id.substring(0, 8)}... (${thread.event_count} events)`;
        elements.auditThreadFilter.appendChild(option);
    });

    // Restore selection or set to latest
    if (data.threads.length > 0) {
        elements.auditThreadFilter.value = currentValue || data.threads[0].thread_id;
        if (!currentThreadId && data.threads.length > 0) {
            currentThreadId = data.threads[0].thread_id;
        }
    }

    return data.threads;
}

async function fetchWorkflow(threadId) {
    if (!threadId) return;

    const data = await fetchAPI(`/workflow/${threadId}`);
    if (!data || data.error) return;

    // Update workflow visualization
    const stages = ['need', 'propose', 'claim', 'commit', 'attest', 'finalize'];
    const stateToStage = {
        'DRAFT': 0,
        'DECIDED': 2,
        'VERIFIED': 4,
        'FINAL': 5
    };

    const currentStageIndex = stateToStage[data.current_state] || 0;

    stages.forEach((stage, index) => {
        const stageEl = elements.workflowContainer.querySelector(`[data-stage="${stage}"]`);
        if (!stageEl) return;

        stageEl.classList.remove('active', 'completed');
        const statusEl = stageEl.querySelector('.stage-status');

        if (index < currentStageIndex) {
            stageEl.classList.add('completed');
            statusEl.textContent = 'Completed';
        } else if (index === currentStageIndex) {
            stageEl.classList.add('active');
            statusEl.textContent = 'Processing';
        } else {
            statusEl.textContent = 'Pending';
        }
    });

    // Update thread info
    elements.threadInfo.innerHTML = `
        <strong>Thread:</strong> ${threadId.substring(0, 16)}... | 
        <strong>Task:</strong> ${data.task_id ? data.task_id.substring(0, 8) + '...' : 'N/A'} | 
        <strong>State:</strong> ${data.current_state} | 
        <strong>Lamport:</strong> ${data.lamport}
    `;
}

async function fetchAgents() {
    const data = await fetchAPI('/agents');
    if (!data || !data.agents) return;

    elements.agentsGrid.innerHTML = '';

    data.agents.forEach(agent => {
        const card = document.createElement('div');
        card.className = 'agent-card';
        card.innerHTML = `
            <div class="agent-header">
                <div class="agent-icon">${getAgentIcon(agent.type)}</div>
                <div class="agent-pulse ${agent.status}"></div>
            </div>
            <h3>${agent.name}</h3>
            <div class="agent-stats">
                <div class="stat">
                    <span class="stat-label">Status</span>
                    <span class="stat-value">${agent.status}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Type</span>
                    <span class="stat-value">${agent.type}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Uptime</span>
                    <span class="stat-value">${agent.uptime}</span>
                </div>
            </div>
        `;
        elements.agentsGrid.appendChild(card);
    });
}

function getAgentIcon(type) {
    const icons = {
        'planning': '🧠',
        'execution': '⚙️',
        'verification': '✅'
    };
    return icons[type] || '🤖';
}

async function fetchMetrics() {
    const data = await fetchAPI('/metrics');
    if (!data) return;

    // Animate counter updates
    animateValue(elements.metricTotalTasks, data.total_tasks || 0);
    animateValue(elements.metricCompleted, data.completed_tasks || 0);
    animateValue(elements.metricOperations, data.total_ops || 0);
    elements.metricSuccessRate.textContent = `${data.success_rate || 0}%`;
}

function animateValue(element, endValue) {
    const startValue = parseInt(element.textContent) || 0;
    if (startValue === endValue) return;

    const duration = 500; // ms
    const startTime = Date.now();

    function update() {
        const now = Date.now();
        const progress = Math.min((now - startTime) / duration, 1);
        const currentValue = Math.floor(startValue + (endValue - startValue) * progress);
        element.textContent = currentValue;

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

async function fetchAuditLog(threadId = null) {
    const selectedThread = threadId || elements.auditThreadFilter.value;
    const endpoint = selectedThread ? `/audit?thread_id=${selectedThread}&limit=50` : '/audit?limit=50';

    const data = await fetchAPI(endpoint);
    if (!data || !data.entries) return;

    elements.auditCount.textContent = `${data.entries.length} entries`;

    if (data.entries.length === 0) {
        elements.auditLog.innerHTML = '<div class="audit-empty"><span>No audit entries found.</span></div>';
        return;
    }

    elements.auditLog.innerHTML = '';

    data.entries.forEach(entry => {
        const entryEl = document.createElement('div');
        entryEl.className = 'audit-entry';

        const timestamp = new Date(entry.timestamp * 1000).toLocaleTimeString();
        const signature = entry.has_signature ? '<span class="signature">✓ Signed</span>' : '<span style="color: var(--status-error)">✗ Unsigned</span>';

        entryEl.innerHTML = `
            <div class="timestamp">[${timestamp}]</div>
            <div class="kind">${entry.kind}</div>
            <div>${entry.subject}</div>
            <div>${signature}</div>
            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">${entry.payload_preview}</div>
        `;

        elements.auditLog.appendChild(entryEl);
    });
}

async function startDemo() {
    elements.btnStartDemo.disabled = true;
    elements.demoStatus.innerHTML = '<div style="color: #60a5fa;">🚀 Starting E2E demo...</div>';

    try {
        const response = await fetch(`${API_BASE}/demo/start`, { method: 'POST' });
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        elements.demoStatus.innerHTML = '<div style="color: var(--status-active);">✓ Demo started! Watch the workflow...</div>';

        // Poll for demo completion
        const pollInterval = setInterval(async () => {
            const status = await fetchAPI('/demo/status');
            if (status && !status.running) {
                clearInterval(pollInterval);
                elements.btnStartDemo.disabled = false;

                if (status.thread_id) {
                    currentThreadId = status.thread_id;
                    elements.demoStatus.innerHTML = `<div style="color: var(--status-active);">✓ Demo completed! Thread: ${status.thread_id.substring(0, 16)}...</div>`;
                    await updateDashboard();
                }
            }
        }, 2000);

    } catch (error) {
        elements.btnStartDemo.disabled = false;
        elements.demoStatus.innerHTML = `<div style="color: var(--status-error);">✗ Error: ${error.message}</div>`;
    }
}

async function updateDashboard() {
    await Promise.all([
        fetchSystemStatus(),
        fetchThreads(),
        fetchAgents(),
        fetchMetrics(),
        fetchAuditLog()
    ]);

    if (currentThreadId) {
        await fetchWorkflow(currentThreadId);
    }
}

// Event Listeners
elements.btnStartDemo.addEventListener('click', startDemo);
elements.btnRefresh.addEventListener('click', updateDashboard);
elements.btnViewDocs.addEventListener('click', () => {
    window.open('docs/DEMO.md', '_blank');
});
elements.auditThreadFilter.addEventListener('change', async (e) => {
    currentThreadId = e.target.value || null;
    await fetchAuditLog(currentThreadId);
    if (currentThreadId) {
        await fetchWorkflow(currentThreadId);
    }
});

// Initialize
async function init() {
    console.log('🐝 CAN Swarm Investor Demo - Initializing...');

    // Initial load
    await updateDashboard();

    // Start auto-refresh
    updateInterval = setInterval(updateDashboard, UPDATE_INTERVAL);

    console.log('✓ Dashboard initialized. Auto-refresh every', UPDATE_INTERVAL / 1000, 'seconds');
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
});

// Start the app
init();
