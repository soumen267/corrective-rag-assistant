const API_BASE_URL = "http://127.0.0.1:8000";


let sessionId = null;
let isSending = false;


// --------------------------------------------------
// Elements
// --------------------------------------------------

const chatForm = document.getElementById("chatForm");
const questionInput = document.getElementById("questionInput");
const sendButton = document.getElementById("sendButton");

const chatMessages = document.getElementById("chatMessages");

const clearChatButton = document.getElementById(
    "clearChatButton"
);

const documentList = document.getElementById(
    "documentList"
);

const refreshDocumentsButton = document.getElementById(
    "refreshDocuments"
);

const uploadButton = document.getElementById(
    "uploadButton"
);

const fileInput = document.getElementById(
    "fileInput"
);

const errorMessage = document.getElementById(
    "errorMessage"
);

const healthText = document.getElementById(
    "healthText"
);

const statusDot = document.querySelector(
    ".status-dot"
);


// --------------------------------------------------
// API helper
// --------------------------------------------------

async function apiRequest(
    endpoint,
    options = {}
) {
    const response = await fetch(
        `${API_BASE_URL}${endpoint}`,
        options
    );

    if (!response.ok) {
        let message = "Request failed.";

        try {
            const error = await response.json();

            message =
                error.detail ||
                message;
        } catch {
            // Ignore JSON parsing failure.
        }

        throw new Error(message);
    }

    return response.json();
}


// --------------------------------------------------
// Health
// --------------------------------------------------

async function checkHealth() {
    try {
        await apiRequest("/health");

        healthText.textContent = "Online";

        statusDot.classList.remove(
            "offline"
        );

        statusDot.classList.add(
            "online"
        );

    } catch {
        healthText.textContent = "Offline";

        statusDot.classList.remove(
            "online"
        );

        statusDot.classList.add(
            "offline"
        );
    }
}


// --------------------------------------------------
// Documents
// --------------------------------------------------

async function loadDocuments() {
    documentList.innerHTML = `
        <p class="muted">
            Loading documents...
        </p>
    `;

    try {
        const data = await apiRequest(
            "/documents"
        );

        renderDocuments(
            data.documents
        );

    } catch (error) {
        documentList.innerHTML = `
            <p class="muted">
                Unable to load documents.
            </p>
        `;

        showError(error.message);
    }
}


function renderDocuments(documents) {
    documentList.innerHTML = "";

    if (!documents.length) {
        documentList.innerHTML = `
            <p class="muted">
                No documents indexed.
            </p>
        `;

        return;
    }

    documents.forEach((source) => {

        const item = document.createElement(
            "div"
        );

        item.className = "document-item";


        const info = document.createElement(
            "div"
        );

        info.className = "document-info";


        const name = document.createElement(
            "span"
        );

        name.className = "document-name";

        name.textContent =
            getFileName(source);


        const path = document.createElement(
            "span"
        );

        path.className = "document-path";

        path.textContent = source;


        const deleteButton =
            document.createElement(
                "button"
            );

        deleteButton.className =
            "delete-document";

        deleteButton.textContent = "×";

        deleteButton.title =
            "Delete document";

        deleteButton.addEventListener(
            "click",
            () => deleteDocument(source)
        );


        info.appendChild(name);
        info.appendChild(path);

        item.appendChild(info);
        item.appendChild(deleteButton);

        documentList.appendChild(item);
    });
}


function getFileName(source) {
    return source
        .replaceAll("\\", "/")
        .split("/")
        .pop();
}


// --------------------------------------------------
// Upload
// --------------------------------------------------

uploadButton.addEventListener(
    "click",
    () => {
        fileInput.click();
    }
);


fileInput.addEventListener(
    "change",
    async () => {

        const file =
            fileInput.files[0];

        if (!file) {
            return;
        }

        const formData =
            new FormData();

        formData.append(
            "file",
            file
        );

        uploadButton.disabled = true;
        uploadButton.textContent =
            "Uploading...";

        hideError();

        try {
            await apiRequest(
                "/documents",
                {
                    method: "POST",
                    body: formData,
                }
            );

            await loadDocuments();

        } catch (error) {
            showError(error.message);

        } finally {
            uploadButton.disabled = false;

            uploadButton.textContent =
                "+ Upload Document";

            fileInput.value = "";
        }
    }
);


// --------------------------------------------------
// Delete document
// --------------------------------------------------

async function deleteDocument(source) {
    const confirmed = window.confirm(
        `Delete ${getFileName(source)}?`
    );

    if (!confirmed) {
        return;
    }

    try {
        const query =
            new URLSearchParams({
                source: source,
            });

        await apiRequest(
            `/documents?${query}`,
            {
                method: "DELETE",
            }
        );

        await loadDocuments();

    } catch (error) {
        showError(error.message);
    }
}


// --------------------------------------------------
// Chat
// --------------------------------------------------

chatForm.addEventListener(
    "submit",
    async (event) => {

        event.preventDefault();

        if (isSending) {
            return;
        }

        const question =
            questionInput.value.trim();

        if (!question) {
            return;
        }

        hideWelcome();
        hideError();

        addMessage(
            "user",
            question
        );

        questionInput.value = "";

        setSending(true);

        const loadingElement =
            addLoadingMessage();

        try {

            const payload = {
                question: question,
            };

            if (sessionId) {
                payload.session_id =
                    sessionId;
            }

            const data = await apiRequest(
                "/chat",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json",
                    },

                    body: JSON.stringify(
                        payload
                    ),
                }
            );

            sessionId =
                data.session_id;

            loadingElement.remove();

            addAssistantMessage(
                data.answer,
                data.sources
            );

        } catch (error) {

            loadingElement.remove();

            showError(
                error.message
            );

        } finally {

            setSending(false);

            questionInput.focus();
        }
    }
);


// --------------------------------------------------
// Messages
// --------------------------------------------------

function addMessage(
    role,
    content
) {
    const wrapper =
        document.createElement("div");

    wrapper.className =
        `message ${role}-message`;


    const label =
        document.createElement("div");

    label.className =
        "message-label";

    label.textContent =
        role === "user"
            ? "You"
            : "Assistant";


    const messageContent =
        document.createElement("div");

    messageContent.className =
        "message-content";

    messageContent.textContent =
        content;


    wrapper.appendChild(label);
    wrapper.appendChild(
        messageContent
    );

    chatMessages.appendChild(
        wrapper
    );

    scrollChatToBottom();

    return wrapper;
}


function addAssistantMessage(
    answer,
    sources
) {
    const wrapper =
        addMessage(
            "assistant",
            answer
        );

    if (
        !sources ||
        !sources.length
    ) {
        return;
    }

    const sourcesContainer =
        document.createElement("div");

    sourcesContainer.className =
        "sources";


    sources.forEach(
        (source, index) => {

            const card =
                createSourceCard(
                    source,
                    index + 1
                );

            sourcesContainer.appendChild(
                card
            );
        }
    );


    wrapper.appendChild(
        sourcesContainer
    );

    scrollChatToBottom();
}


function createSourceCard(
    source,
    number
) {
    const card =
        document.createElement("div");

    card.className =
        "source-card";


    const header =
        document.createElement(
            "button"
        );

    header.className =
        "source-header";


    const title =
        document.createElement(
            "span"
        );

    title.className =
        "source-title";

    title.textContent =
        `[Source ${number}] ${source.file_name}`;


    const score =
        document.createElement(
            "span"
        );

    score.className =
        "source-score";

    score.textContent =
        Number(
            source.relevance_score
        ).toFixed(3);


    const details =
        document.createElement(
            "div"
        );

    details.className =
        "source-details";


    const meta =
        document.createElement(
            "div"
        );

    meta.className =
        "source-meta";

    let pageText = "";

    if (
        source.page !== null &&
        source.page !== undefined
    ) {
        pageText =
            ` | Page ${source.page + 1}`;
    }

    meta.textContent =
        `${source.source}${pageText}`;


    const excerpt =
        document.createElement(
            "div"
        );

    excerpt.textContent =
        source.excerpt;


    details.appendChild(meta);
    details.appendChild(excerpt);

    header.appendChild(title);
    header.appendChild(score);

    header.addEventListener(
        "click",
        () => {
            details.classList.toggle(
                "open"
            );
        }
    );

    card.appendChild(header);
    card.appendChild(details);

    return card;
}


function addLoadingMessage() {
    const wrapper =
        document.createElement(
            "div"
        );

    wrapper.className =
        "message assistant-message";


    const label =
        document.createElement(
            "div"
        );

    label.className =
        "message-label";

    label.textContent =
        "Assistant";


    const content =
        document.createElement(
            "div"
        );

    content.className =
        "message-content typing";

    content.textContent =
        "Searching knowledge base...";


    wrapper.appendChild(label);
    wrapper.appendChild(content);

    chatMessages.appendChild(
        wrapper
    );

    scrollChatToBottom();

    return wrapper;
}


// --------------------------------------------------
// Clear conversation
// --------------------------------------------------

clearChatButton.addEventListener(
    "click",
    async () => {

        hideError();

        if (sessionId) {
            try {
                await apiRequest(
                    `/sessions/${sessionId}`,
                    {
                        method: "DELETE",
                    }
                );

            } catch (error) {
                showError(
                    error.message
                );

                return;
            }
        }

        sessionId = null;

        chatMessages.innerHTML = `
            <div class="welcome">
                <h2>
                    Ask your knowledge base
                </h2>

                <p>
                    Answers are generated from your
                    indexed documents using hybrid
                    retrieval and local AI.
                </p>
            </div>
        `;
    }
);


// --------------------------------------------------
// Helpers
// --------------------------------------------------

function setSending(sending) {
    isSending = sending;

    sendButton.disabled =
        sending;

    questionInput.disabled =
        sending;

    sendButton.textContent =
        sending
            ? "Thinking..."
            : "Send";
}


function hideWelcome() {
    const welcome =
        document.querySelector(
            ".welcome"
        );

    if (welcome) {
        welcome.remove();
    }
}


function scrollChatToBottom() {
    chatMessages.scrollTop =
        chatMessages.scrollHeight;
}


function showError(message) {
    errorMessage.textContent =
        message;

    errorMessage.classList.remove(
        "hidden"
    );
}


function hideError() {
    errorMessage.classList.add(
        "hidden"
    );
}


// Enter sends.
// Shift + Enter creates a new line.

questionInput.addEventListener(
    "keydown",
    (event) => {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {
            event.preventDefault();

            chatForm.requestSubmit();
        }
    }
);


// Auto-resize textarea

questionInput.addEventListener(
    "input",
    () => {

        questionInput.style.height =
            "auto";

        questionInput.style.height =
            `${questionInput.scrollHeight}px`;
    }
);


// --------------------------------------------------
// Initialization
// --------------------------------------------------

async function initialize() {
    await checkHealth();
    await loadDocuments();

    questionInput.focus();
}


initialize();