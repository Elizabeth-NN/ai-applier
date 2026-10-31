const API_BASE_URL = "http://localhost:8000";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "PREPARE_APPLICATION") {
    return false;
  }

  handlePreparation(message.token)
    .then(sendResponse)
    .catch((error) => {
      sendResponse({
        success: false,
        error: error.message || "Application preparation failed.",
      });
    });

  return true;
});

async function handlePreparation(token) {
  if (typeof token !== "string" || token.trim().length < 32) {
    throw new Error("Please provide a valid handoff token.");
  }

  const response = await fetch(`${API_BASE_URL}/api/extension-handoffs/redeem`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      token: token.trim(),
    }),
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("Handoff token is invalid, expired, or already used.");
    }

    throw new Error("Could not redeem the handoff token.");
  }

  const application = await response.json();

  if (!Number.isInteger(application.execution_id)) {
    throw new Error("The backend returned an invalid application.");
  }

  const tabs = await chrome.tabs.query({
    active: true,
    currentWindow: true,
  });

  const activeTab = tabs[0];

  if (!activeTab?.id || !activeTab.url) {
    throw new Error("No active browser tab was found.");
  }

  const url = new URL(activeTab.url);

  if (
    url.protocol !== "https:" ||
    !(
      url.hostname === "boards.greenhouse.io" ||
      url.hostname === "job-boards.greenhouse.io"
    )
  ) {
    throw new Error("Open a supported Greenhouse application page first.");
  }

  await chrome.tabs.sendMessage(activeTab.id, {
    type: "FILL_APPLICATION",
    application,
  });

  return {
    success: true,
    message: "Application data sent to the active Greenhouse page.",
  };
}
